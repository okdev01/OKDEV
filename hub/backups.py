"""Inspect and export local recovery copies without modifying their contents."""
import json
import os
import stat
import zipfile
from pathlib import Path

from . import library
from .transactions import _backup
from utils.core.atomic_file import atomic_write


def _read(backup_id):
    folder = _backup(backup_id)
    try:
        metadata = folder / 'metadata.json'
        if metadata.is_symlink() or metadata.stat().st_size > 128 * 1024:
            raise ValueError()
        record = library.load_json(metadata, library.MAX_METADATA_BYTES)
        item = record['item']
        library.validate_metadata(item)
        library.mod_folder(item)
        payload = folder / 'mod'
        if not payload.is_dir() or payload.resolve() != folder.resolve() / 'mod':
            raise ValueError()
        return folder, item
    except (OSError, ValueError, TypeError, KeyError):
        raise ValueError('Yedek okunamadı veya dosyaları bulunamadı. Özgün dosyalar korundu.') from None


def _files(folder):
    payload = folder / 'mod'
    files, total = [], 0
    for directory, names, filenames in os.walk(payload, followlinks=False):
        for name in names + filenames:
            path = Path(directory) / name
            info = path.lstat()
            if (path.is_symlink() or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
                    or not path.resolve().is_relative_to(payload.resolve())):
                raise ValueError('Yedekte bağlantılı dosya veya klasör var. Dışa aktarılmadı.')
        for name in filenames:
            path = Path(directory) / name
            total += path.stat().st_size
            files.append(path)
            if len(files) > 20000 or total > 2 * 1024 ** 3:
                raise ValueError('Yedek, mod paketi sınırını aşıyor. Veri klasöründen dosyalarını incele.')
    return sorted(files), total


def inspect(backup_id):
    with library.mutation_lock():
        folder, item = _read(backup_id)
        files, size = _files(folder)
        installed = item['id'] in library.installed(strict=True)
        occupied = library.mod_folder(item).exists()
        return {'restore_conflict': 'installed' if installed else 'folder' if occupied else '', 'id': backup_id, 'name': item['name'], 'version': item['version'],
                'bytes': size, 'files': len(files), 'installed': installed}


def export(backup_id, destination):
    """Write a re-importable package atomically; never include machine state."""
    destination = Path(destination)
    if destination.suffix.lower() not in ('.fantome', '.zip'):
        raise ValueError('Yedeği .fantome veya .zip uzantısıyla kaydet.')
    with library.mutation_lock():
        folder, item = _read(backup_id)
        files, _ = _files(folder)
        data_root = library.get_user_data_dir().resolve()
        if destination.resolve().is_relative_to(data_root):
            raise ValueError('Yedeği OKDEV veri klasörü dışında bir konuma kaydet.')
        # Preserve the exact game bytes and original package metadata. The
        # optional OKDEV note contains only public descriptive fields.
        with atomic_write(destination, 'w+b') as stream:
            with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
                for path in files:
                    relative = path.relative_to(folder / 'mod').as_posix()
                    if relative.lower() != 'meta/okdev-backup.json':
                        archive.write(path, relative)
                archive.writestr('META/okdev-backup.json', json.dumps({key: item[key] for key in
                    ('id', 'name', 'version', 'category', 'champion', 'champion_id', 'description', 'author', 'license')
                    if key in item}, ensure_ascii=False))
            if stream.tell() > library.MAX_DOWNLOAD:
                raise ValueError('Dışa aktarılan paket 512 MB sınırını aşıyor. Özgün yedek korundu.')
            # Backups can have been edited outside OKDEV since installation.
            # Validate the finished archive before committing the destination.
            stream.flush()
            stream.seek(0)
            with zipfile.ZipFile(stream, 'r') as archive:
                library._validate_zip(archive)
        return {'saved': True, 'name': item['name']}
