"""Recover folder/index mutations after a crash without deleting mod payloads.

The atomic installed.json entry is the commit point. Before it changes, recovery
restores the old placement; after it changes, recovery completes the placement.
New imports whose index never committed are retained as recoverable backups.
"""
import json
import re
import time
import uuid
from pathlib import Path

from . import library


def _folder():
    path = library.root() / 'pending'
    if path.resolve() != library.root().resolve() / 'pending':
        raise ValueError('İşlem kayıtları için güvenli klasör bulunamadı.')
    return path


def _backup(backup_id):
    if not isinstance(backup_id, str) or not re.fullmatch('[a-f0-9]{32}', backup_id):
        raise ValueError('İşlem yedeği geçersiz.')
    path = library.root() / 'removed' / backup_id
    if path.resolve() != library.root().resolve() / 'removed' / backup_id:
        raise ValueError('İşlem yedeğinin yolu geçersiz.')
    return path


def _validate(record):
    if (not isinstance(record, dict) or type(record.get('schema')) is not int or record['schema'] != 1
            or record.get('kind') not in ('import', 'remove', 'restore')):
        raise ValueError('İşlem kaydı okunamadı.')
    if not library.valid_id(record.get('mod_id')):
        raise ValueError('İşlem kimliği geçersiz.')
    for key in ('before', 'after'):
        item = record.get(key)
        if item is not None:
            if not isinstance(item, dict) or item.get('id') != record['mod_id'] or type(item.get('enabled')) is not bool:
                raise ValueError('İşlemdeki mod bilgisi geçersiz.')
            library.validate_metadata(item)
            library.mod_folder(item)
    if record['before'] is None and record['after'] is None:
        raise ValueError('Boş işlem kaydı.')
    if record['kind'] == 'remove' and (record['before'] is None or record['after'] is not None):
        raise ValueError('Kaldırma kaydı geçersiz.')
    if record['kind'] == 'restore' and (record['before'] is not None or record['after'] is None):
        raise ValueError('Geri yükleme kaydı geçersiz.')
    if record['kind'] == 'import' and record['after'] is None:
        raise ValueError('İçe aktarma kaydı geçersiz.')
    if record.get('backup_id') is not None:
        _backup(record['backup_id'])
    if record['kind'] == 'restore' and record.get('backup_id') is None:
        raise ValueError('Geri yükleme yedeği eksik.')
    return record


def begin(kind, before, after, backup=None):
    record = {'schema': 1, 'kind': kind, 'mod_id': (after or before)['id'],
              'before': before or None, 'after': after or None,
              'backup_id': Path(backup).name if backup is not None else None,
              'created_at': int(time.time())}
    _validate(record)
    path = _folder() / (uuid.uuid4().hex + '.json')
    library.write_json(path, record)
    return path


def finish(path):
    try:
        path.unlink(missing_ok=True)
    except OSError:
        # A committed journal is safe to revisit. Failure to remove this small
        # file must not report a successful mod operation as failed.
        pass


def _move_if_needed(source, target):
    if any(path.is_symlink() or getattr(path, 'is_junction', lambda: False)() for path in (source, target)):
        raise ValueError('Bağlantılı klasörler otomatik taşınamaz; dosyalar korunuyor.')
    if source.exists() and target.exists():
        raise ValueError('Kaynak ve hedef dosyalar birlikte mevcut; hiçbirinin üzerine yazılmadı.')
    if source.is_dir() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)
    elif not target.is_dir():
        raise ValueError('İşleme ait mod dosyaları bulunamadı; kayıt korundu.')


def _retain_uncommitted(item):
    source = library.mod_folder(item)
    if not source.is_dir():
        return
    backup = _backup(uuid.uuid4().hex)
    backup.mkdir(parents=True)
    library.write_json(backup / 'metadata.json', {'item': dict(item, enabled=False),
        'removed_at': int(time.time()), 'reason': 'interrupted'})
    source.rename(backup / 'mod')


def recover_pending():
    """Caller owns library.mutation_lock. Conflicts stop further writes."""
    folder = _folder()
    if not folder.exists():
        return 0
    paths = sorted(folder.glob('*.json'))
    if len(paths) > 100:
        raise ValueError('Çok fazla yarım işlem kaydı var. Veri klasörünü yedekleyip destek alın.')
    recovered = 0
    for path in paths:
        try:
            if not re.fullmatch(r'[a-f0-9]{32}\.json', path.name) or path.stat().st_size > 128 * 1024:
                raise ValueError('İşlem kaydı geçersiz.')
            if path.is_symlink() or path.resolve().parent != folder.resolve():
                raise ValueError('İşlem dosyasının yolu geçersiz.')
            record = _validate(json.loads(path.read_text(encoding='utf-8')))
            data = library.installed(strict=True)
            current = data.get(record['mod_id'])
            before, after = record['before'], record['after']
            for item in (before, after):
                if item and any(other_id != record['mod_id'] and other.get('relative_path') == item['relative_path']
                                for other_id, other in data.items()):
                    raise ValueError('İşlemdeki klasör başka bir mod tarafından kullanılıyor.')
            backup = _backup(record['backup_id']) if record.get('backup_id') else None
            if current == before:
                # The index never committed: restore the original placement.
                if record['kind'] in ('import', 'remove') and before and backup:
                    original = library.mod_folder(before)
                    if (backup / 'mod').is_dir() or not original.is_dir():
                        _move_if_needed(backup / 'mod', original)
                elif record['kind'] == 'restore':
                    original = library.mod_folder(after)
                    if original.is_dir() or not (backup / 'mod').is_dir():
                        _move_if_needed(original, backup / 'mod')
                if record['kind'] == 'import':
                    _retain_uncommitted(after)
            elif current == after:
                # The index committed: ensure the corresponding placement.
                if record['kind'] in ('import', 'remove') and before and backup:
                    _move_if_needed(library.mod_folder(before), backup / 'mod')
                elif record['kind'] == 'restore':
                    _move_if_needed(backup / 'mod', library.mod_folder(after))
                if after and not library.mod_folder(after).is_dir():
                    raise ValueError('Kaydedilen modun dosyaları bulunamadı.')
            else:
                raise ValueError('Mod kaydı yarım işlemden sonra değişmiş; dosyalar korunuyor.')
            path.unlink()
            recovered += 1
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise ValueError('Yarım kalan mod işlemi otomatik kurtarılamadı. Veri klasörünü yedekleyip Sistem durumu bölümünü kontrol et. ' + (str(exc) if isinstance(exc, ValueError) else 'Dosyalar kullanımda veya disk erişimi kısıtlı.')) from None
    return recovered


def status():
    try:
        count = len(list(_folder().glob('*.json')))
        return {'pending': count}
    except (OSError, ValueError):
        return {'pending': -1}
