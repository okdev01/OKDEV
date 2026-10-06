import hashlib
import json
import re
import stat
import threading
import time
import zipfile
import tempfile
from contextlib import contextmanager, closing
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlparse

import requests
from .locking import settings_lock
from utils.core.atomic_file import atomic_write
from utils.core.paths import get_user_data_dir

CATALOG_URL = 'https://raw.githubusercontent.com/okdev01/OKDEV/main/mods/catalog.json'
MAX_DOWNLOAD = 512 * 1024 * 1024
MAX_INDEX_BYTES = 32 * 1024 * 1024
MAX_CATALOG_BYTES = 4 * 1024 * 1024
MAX_SETTINGS_BYTES = 1024 * 1024
MAX_METADATA_BYTES = 128 * 1024
CATEGORIES = {'skins': 'Şampiyon', 'ui': 'HUD / Arayüz', 'maps': 'Harita',
              'fonts': 'Yazı tipi', 'announcers': 'Spiker'}
_lock = threading.RLock()
_mutation_local = threading.local()


@contextmanager
def mutation_lock():
    """Serialize library/profile writes across the UI and background workers."""
    with _lock:
        if getattr(_mutation_local, 'active', False):
            yield
            return
        with settings_lock(root() / 'library-state.json'):
            _mutation_local.active = True
            try:
                from .transactions import recover_pending
                recovered = recover_pending()
                if recovered:
                    from .activity import record
                    record('recovery', count=recovered)
                yield
            finally:
                _mutation_local.active = False


def root():
    folder = get_user_data_dir() / 'hub'
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def load_json(path, limit=MAX_CATALOG_BYTES):
    """Read bounded local state; malformed input never escapes as recursion errors.

    Limit the actual read, not just stat(), because another process can replace
    or grow a file between those operations. Callers decide whether to display
    defaults or refuse a mutation, preserving the original file in either case.
    """
    if path.stat().st_size > limit:
        raise ValueError('Kayıt dosyası boyut sınırını aşıyor.')
    with path.open('rb') as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError('Kayıt dosyası boyut sınırını aşıyor.')
    try:
        return json.loads(content.decode('utf-8'))
    except RecursionError:
        raise ValueError('Kayıt dosyasının yapısı geçersiz.') from None


def read_json(path, default):
    try:
        value = load_json(path)
        return value if isinstance(value, type(default)) else default
    except (OSError, ValueError):
        return default


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_write(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _settings_data(strict=False):
    path = root() / 'settings.json'
    if not path.exists():
        return {}
    try:
        data = load_json(path, MAX_SETTINGS_BYTES)
        if (not isinstance(data, dict)
                or ('auto_accept' in data and type(data['auto_accept']) is not bool)
                or ('favorites' in data and (not isinstance(data['favorites'], list)
                    or not all(valid_id(value) for value in data['favorites'])))):
            raise ValueError()
        return data
    except (OSError, ValueError):
        if strict:
            raise ValueError('Tercihler okunamadı. Özgün ayar dosyası korunuyor; Tanılama ekranını kontrol edin.') from None
        return {}


def settings(strict=False):
    data = _settings_data(strict)
    favorites = data.get('favorites', [])
    return {'auto_accept': data.get('auto_accept') is True,
            'favorites': sorted({v for v in favorites if valid_id(v)}) if isinstance(favorites, list) else []}


def valid_id(value):
    return isinstance(value, str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', value) is not None


def set_auto_accept(enabled):
    if not isinstance(enabled, bool):
        raise ValueError('Geçersiz ayar')
    with _lock, settings_lock(root() / 'settings.json'):
        data = _settings_data(strict=True)
        data['auto_accept'] = enabled
        write_json(root() / 'settings.json', data)


def set_favorite(mod_id, favorite):
    if not valid_id(mod_id) or not isinstance(favorite, bool):
        raise ValueError('Geçersiz favori seçimi')
    with _lock, settings_lock(root() / 'settings.json'):
        data = _settings_data(strict=True)
        favorites = set(settings()['favorites'])
        if favorite:
            favorites.add(mod_id)
        else:
            favorites.discard(mod_id)
        data['favorites'] = sorted(favorites)
        write_json(root() / 'settings.json', data)


def validate_catalog(data):
    if not isinstance(data, dict) or type(data.get('schema')) is not int or data['schema'] != 1 or not isinstance(data.get('mods'), list):
        raise ValueError('Mod kataloğu biçimi geçersiz')
    if len(data['mods']) > 2000:
        raise ValueError('Katalog çok büyük')
    seen = set()
    for item in data['mods']:
        if not isinstance(item, dict) or not valid_id(item.get('id')):
            raise ValueError('Mod kimliği geçersiz')
        if item['id'] in seen:
            raise ValueError('Yinelenen mod kimliği')
        seen.add(item['id'])
        category = item.get('category', 'skins')
        if not isinstance(category, str) or category not in CATEGORIES:
            raise ValueError('Mod kategorisi geçersiz')
        if category == 'skins' and (type(item.get('champion_id')) is not int or not 0 < item['champion_id'] < 100000):
            raise ValueError('Şampiyon kimliği geçersiz')
        if category != 'skins' and item.get('champion_id') is not None:
            raise ValueError('Bu mod kategorisi şampiyon seçimi gerektirmez')
        if not isinstance(item.get('version'), str) or len(item['version']) > 48 or not re.fullmatch(r'[0-9]+(?:\.[0-9]+){2,4}', item['version']):
            raise ValueError('Mod sürümü geçersiz')
        if not isinstance(item.get('sha256'), str) or not re.fullmatch(r'[a-f0-9]{64}', item['sha256']):
            raise ValueError('Mod doğrulama bilgisi eksik')
        if not isinstance(item.get('url'), str):
            raise ValueError('Mod indirme kaynağı geçersiz')
        parsed = urlparse(item['url'])
        if parsed.scheme != 'https' or parsed.netloc != 'github.com' or not parsed.path.startswith('/okdev01/OKDEV/releases/download/'):
            raise ValueError('Mod indirme kaynağı geçersiz')
        if item.get('image_url'):
            if not isinstance(item['image_url'], str):
                raise ValueError('Mod görseli kaynağı geçersiz')
            image = urlparse(item['image_url'])
            from .sources import valid_preview
            github_image = image.scheme == 'https' and image.netloc == 'github.com' and image.path.startswith('/okdev01/OKDEV/releases/download/')
            if not github_image and not valid_preview(item['image_url']):
                raise ValueError('Mod görseli kaynağı geçersiz')
        for field, limit in [('name', 100), ('description', 2000), ('champion', 80)]:
            if not isinstance(item.get(field), str) or len(item[field]) > limit:
                raise ValueError('Mod açıklaması geçersiz')
    return data


def catalog(refresh=False, allow_network=True):
    path = root() / 'catalog.json'
    error = ''
    try:
        data = validate_catalog(load_json(path, MAX_CATALOG_BYTES))
        stale = time.time() - path.stat().st_mtime > 300
    except (OSError, ValueError, TypeError):
        data, stale = {'schema': 1, 'mods': []}, True
    if not allow_network:
        return data, ''
    if refresh or stale:
        try:
            with closing(requests.get(CATALOG_URL, timeout=(10, 15), stream=True)) as response:
                if response.status_code == 404:
                    write_json(path, data)
                    return validate_catalog(data), 'Kütüphane henüz yayımlanmadı. Yerel mod içe aktarabilirsiniz.'
                response.raise_for_status()
                limit = MAX_CATALOG_BYTES
                length = response.headers.get('Content-Length', '')
                if isinstance(length, str) and length.isdigit() and int(length) > limit:
                    raise ValueError('Katalog çok büyük')
                content = bytearray()
                for chunk in response.iter_content(64 * 1024):
                    if len(content) + len(chunk) > limit:
                        raise ValueError('Katalog çok büyük')
                    content.extend(chunk)
                fresh = validate_catalog(json.loads(content))
            write_json(path, fresh)
            data = fresh
        except (requests.RequestException, ValueError, OSError, RecursionError):
            error = 'Kataloğa ulaşılamadı. Kaydedilen kütüphane gösteriliyor.'
    return validate_catalog(data), error


def installed(strict=False):
    path = root() / 'installed.json'
    if not path.exists():
        return {}
    try:
        data = load_json(path, MAX_INDEX_BYTES)
        if not isinstance(data, dict):
            raise ValueError('Invalid index')
        valid, folders = {}, set()
        for key, item in data.items():
            try:
                if not isinstance(item, dict) or item.get('id') != key or not valid_id(key):
                    raise ValueError('Invalid entry')
                validate_metadata(item)
                folder = mod_folder(item)
                if folder in folders:
                    raise ValueError('Two mod records share one folder')
                if not isinstance(item.get('folder_name'), str) or type(item.get('enabled')) is not bool:
                    raise ValueError('Invalid entry')
                valid[key] = item
                folders.add(folder)
            except (ValueError, OSError):
                if strict:
                    raise ValueError('Mod kayıtlarında sorun var. Tanılama ekranını kontrol edin; kayıt dosyası korunuyor.')
        return valid
    except (OSError, ValueError):
        if strict:
            raise ValueError('Mod kayıtları okunamadı. Tanılama ekranını kontrol edin; kayıt dosyası korunuyor.') from None
        return {}


def validate_metadata(item):
    # Apply the same metadata contract to local imports and downloaded entries.
    validate_catalog({'schema': 1, 'mods': [dict(item, sha256='0' * 64,
        url='https://github.com/okdev01/OKDEV/releases/download/local/local.fantome')]})


def validate_archive(path):
    if path.stat().st_size > MAX_DOWNLOAD:
        raise ValueError('Mod en fazla 512 MB olabilir')
    with zipfile.ZipFile(path) as z:
        _validate_zip(z)


def _validate_zip(z):
    entries = z.infolist()
    if len(entries) > 20000 or sum(e.file_size for e in entries) > 2 * 1024**3:
        raise ValueError('Mod arşivi çok büyük')
    _validate_windows_members(entries)
    has_wad = False
    members = {e.filename.lower(): e for e in entries}
    for entry in entries:
        name = PurePosixPath(entry.filename)
        if name.is_absolute() or '..' in name.parts or '\\' in entry.filename or ':' in entry.filename:
            raise ValueError('Mod arşivinde geçersiz dosya yolu')
        if stat.S_ISLNK(entry.external_attr >> 16):
            raise ValueError('Mod arşivi bağlantı içeremez')
        ritobin = name.suffix.lower() == '.py' and _is_ritobin_source(z, entry, members)
        if name.suffix.lower() in {'.exe', '.dll', '.ps1', '.bat', '.cmd', '.js', '.py', '.vbs', '.lnk'} and not ritobin:
            raise ValueError('Mod yalnızca oyun verisi içerebilir')
        if entry.filename.lower().startswith('wad/') and not entry.is_dir():
            has_wad = True
    if not has_wad:
        raise ValueError('Mod paketinde WAD oyun dosyaları bulunamadı')
    if z.testzip():
        raise ValueError('Mod arşivi bozuk')


def _validate_windows_members(entries):
    """Reject names ZIP extraction would silently rename or overwrite on Windows."""
    seen, directories = {}, set()
    for entry in entries:
        raw = entry.filename[:-1] if entry.is_dir() else entry.filename
        parts = raw.split('/')
        if (entry.orig_filename != entry.filename or not raw
                or any(part in ('', '.', '..') or part.endswith((' ', '.'))
                       or PureWindowsPath(part).is_reserved()
                       or any(ord(char) < 32 or char in '\\:<>"|?*' for char in part)
                       for part in parts)):
            raise ValueError('Mod arşivinde Windows ile uyumsuz dosya adı var. Paketi yeniden düzenleyip ekle.')
        if entry.flag_bits & 1:
            raise ValueError('Parolalı mod arşivleri desteklenmiyor. Parolasız .zip veya .fantome paketi seç.')
        if entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA):
            raise ValueError('Arşivin sıkıştırma yöntemi desteklenmiyor. Standart .zip paketi olarak kaydet.')
        key = '/'.join(parts).casefold()
        parents = ['/'.join(parts[:index]).casefold() for index in range(1, len(parts))]
        if (key in seen and (not entry.is_dir() or not seen[key])
                or not entry.is_dir() and key in directories
                or any(parent in seen and not seen[parent] for parent in parents)):
            raise ValueError('Mod arşivinde çakışan dosya adları var. Aynı Windows yoluna iki içerik yazılamaz.')
        seen[key] = entry.is_dir()
        directories.update(parents)


def _is_ritobin_source(archive, entry, members):
    # Ritobin's property text is conventionally shipped as .py beside .bin.
    # It is game data, not Python. See wiki.leaguetoolkit.dev/reference/file-formats/ritobin/.
    # CDTB exports may use .cdtb.py alongside an extensionless PROP/PTCH file.
    # Require WAD placement, a compiled sibling, the format's metadata, and
    # reject anything which could be compiled as a Python program. Never execute it.
    name = entry.filename.lower()
    cdtb = name.endswith('.cdtb.py')
    sibling = name[:-8] if cdtb else name[:-3] + '.bin'
    if not name.startswith('wad/') or sibling not in members or entry.file_size > 4 * 1024 * 1024:
        return False
    try:
        with archive.open(members[sibling]) as compiled:
            header = compiled.read(12)
            magic = header[:4]
        if magic not in (b'PROP', b'PTCH'):
            return False
        text = archive.read(entry).decode('utf-8-sig')
        # Some exporters omit an empty linked list. Accept that only when the
        # compiled PROP v2/v3 sibling explicitly declares zero dependencies.
        no_dependencies = (magic == b'PROP' and len(header) == 12
                           and int.from_bytes(header[4:8], 'little') in (2, 3)
                           and header[8:12] == b'\0\0\0\0')
        full = (re.match(r'#PROP_text\s+type:\s*string\s*=\s*"PROP"\s+version:\s*u32\s*=\s*[1-3]\b', text)
                and 'entries: map[' in text and ('linked: list[string]' in text or no_dependencies))
        patch = (cdtb and magic == b'PTCH'
                 and re.match(r'#PROP_text\s+patches:\s*map\[hash,embed\]\s*=\s*\{', text)
                 and 'path: string' in text and 'value:' in text)
        if not (full or patch):
            return False
        try:
            compile(text, '<ritobin-check>', 'exec')
        except SyntaxError:
            return True
    except (UnicodeError, ValueError, RuntimeError, RecursionError):
        pass
    return False


def import_revision(item):
    return hashlib.sha256(json.dumps(item or None, sort_keys=True, ensure_ascii=True).encode('utf-8')).hexdigest()


def import_archive(path, item, expected_revision=None):
    from injection.mods.storage import ModStorageService
    path = Path(path)
    validate_metadata(item)
    validate_archive(path)
    with mutation_lock():
        data = installed(strict=True)
        previous = data.get(item['id'], {})
        if expected_revision is not None and expected_revision != import_revision(previous):
            raise ValueError('Bu mod önizlemeden sonra değişti. Güncel sürümü kontrol edip yeniden ekle.')
        if previous and (previous.get('champion_id') != item.get('champion_id') or previous.get('category', 'skins') != item.get('category', 'skins')):
            raise ValueError('Bu mod kimliği başka bir şampiyona ait. Farklı bir mod kimliği seçin.')
        service = ModStorageService()
        category = item.get('category', 'skins')
        if category == 'skins':
            folder, _, name = service.import_mod_file(item['champion_id'], path, [item['champion_id'] * 1000])
        else:
            folder, name = service.import_category_mod_file(category, path)
        item = dict(item, relative_path=folder.relative_to(service.mods_root).as_posix(),
                    folder_name=name, enabled=previous.get('enabled', False), installed_at=int(time.time()))
        import uuid
        from .covers import save_from_archive
        cover_key = uuid.uuid4().hex
        item['cover_key'] = cover_key if save_from_archive(path, cover_key) else None
        backup = None
        if previous:
            backup = _stage_backup(previous, 'update', move=False)
        from . import transactions
        transaction = transactions.begin('import', previous, item, backup)
        data[item['id']] = item
        try:
            if backup:
                mod_folder(previous).rename(backup / 'mod')
            if previous:
                _clear_history(previous)
            write_json(root() / 'installed.json', data)
        except Exception:
            if backup and (backup / 'mod').exists() and not mod_folder(previous).exists():
                (backup / 'mod').rename(mod_folder(previous))
            # Preserve the newly extracted content, too. It may be recovered
            # manually if the index write failed because the disk is full.
            raise
        from .activity import record
        transactions.finish(transaction)
        record('update' if previous else 'import', item['name'])
        return item


def download(mod_id, progress=None, cancelled=None):
    data, _ = catalog()
    item = next((m for m in data['mods'] if m['id'] == mod_id), None)
    if not item:
        raise ValueError('Mod katalogda bulunamadı')
    return _download_archive(item, item['url'], progress, cancelled)


def download_source(source_id, progress=None, cancelled=None):
    from .sources import entries
    item = next((m for m in entries() if m['id'] == source_id), None)
    if not item or not item.get('download_url'):
        raise ValueError('Bu paket kaynak sayfasından indirilebilir.')
    return _download_archive(item, item['download_url'], progress, cancelled, redirects=False)


def _download_archive(item, url, progress=None, cancelled=None, redirects=True):
    validate_metadata(item)
    def check_cancelled():
        if cancelled and cancelled():
            raise ValueError('İndirme iptal edildi.')

    # Network I/O must never hold the library mutation lock. A unique private
    # workspace also prevents simultaneous attempts from deleting each other.
    with tempfile.TemporaryDirectory(prefix='download-', dir=root()) as temporary:
        check_cancelled()
        path = Path(temporary) / f"{item['id']}-{item['version']}.fantome"
        partial = path.with_suffix('.partial')
        try:
            with requests.get(url, stream=True, timeout=(10, 45), allow_redirects=redirects) as response:
                response.raise_for_status()
                if not redirects and response.status_code != 200:
                    raise ValueError('Kaynak adresi değişmiş olabilir. Özgün sayfadan indirip dosyayı ekle.')
                length = response.headers.get('Content-Length', '')
                expected = int(length) if isinstance(length, str) and length.isdigit() else 0
                if expected > MAX_DOWNLOAD:
                    raise ValueError('Mod indirme sınırını aşıyor')
                digest, total = hashlib.sha256(), 0
                with partial.open('wb') as stream:
                    # Small chunks keep progress and cooperative cancellation
                    # responsive even on slow connections.
                    for chunk in response.iter_content(16 * 1024):
                        check_cancelled()
                        total += len(chunk)
                        if total > MAX_DOWNLOAD:
                            raise ValueError('Mod indirme sınırını aşıyor')
                        digest.update(chunk)
                        stream.write(chunk)
                        if progress:
                            progress({'stage': 'downloading', 'received': total, 'total': expected})
            check_cancelled()
            if digest.hexdigest() != item['sha256']:
                raise ValueError('Mod doğrulanamadı; dosya yüklenmedi. Kaynaktaki dosya değişmiş olabilir.')
            if progress:
                progress({'stage': 'installing', 'received': total, 'total': expected})
            partial.replace(path)
            return import_archive(path, item)
        finally:
            partial.unlink(missing_ok=True)
            path.unlink(missing_ok=True)


def enable(mod_id, enabled):
    with mutation_lock():
        data = installed(strict=True)
        if mod_id not in data or not isinstance(enabled, bool):
            raise ValueError('Mod bulunamadı')
        selected = data[mod_id]
        category = selected.get('category', 'skins')
        if enabled:
            if not mod_folder(data[mod_id]).is_dir():
                raise ValueError('Mod dosyaları bulunamadı. Modu yeniden içe aktarın veya indirin.')
            for item in data.values():
                if item.get('category', 'skins') == category and (category != 'skins' or item['champion_id'] == selected['champion_id']):
                    if item['enabled'] and item['id'] != mod_id:
                        _clear_history(item)
                    item['enabled'] = False
        data[mod_id]['enabled'] = enabled
        if not enabled:
            _clear_history(data[mod_id])
        write_json(root() / 'installed.json', data)


def mod_folder(item):
    base = (get_user_data_dir() / 'mods').resolve()
    relative = item.get('relative_path')
    if not isinstance(relative, str) or not relative:
        raise ValueError('Geçersiz mod yolu')
    parts = PurePosixPath(relative.replace('\\', '/')).parts
    category = item.get('category', 'skins')
    expected_parent = ('skins', str(item.get('champion_id', 0) * 1000)) if category == 'skins' else (category,)
    if (len(parts) != len(expected_parent) + 1 or tuple(parts[:-1]) != expected_parent
            or any(part in {'.', '..'} for part in parts)
            or parts[-1] != item.get('folder_name')):
        raise ValueError('Geçersiz mod yolu')
    lexical = base.joinpath(*parts)
    path = lexical.resolve()
    if not path.is_relative_to(base) or path == base or path != lexical:
        raise ValueError('Geçersiz mod yolu')
    return path


def _clear_history(item):
    if item.get('category', 'skins') != 'skins':
        from utils.core.mod_historic import get_historic_mod, write_historic_mod, clear_historic_mod
        key = {'maps': 'map', 'fonts': 'font', 'announcers': 'announcer'}.get(item['category'], item['category'])
        current = get_historic_mod(key)
        if isinstance(current, list):
            write_historic_mod(key, [p for p in current if p != item['relative_path']])
        elif current == item['relative_path']:
            clear_historic_mod(key)
        return
    from utils.core.historic import get_historic_skin_for_champion, clear_historic_entry
    if get_historic_skin_for_champion(item['champion_id']) == 'path:' + item['relative_path']:
        clear_historic_entry(item['champion_id'])


def _stage_backup(item, reason='removed', move=True):
    import uuid
    folder = mod_folder(item)
    if not folder.exists():
        return None
    from .transactions import _backup
    trash = _backup(uuid.uuid4().hex)
    trash.mkdir(parents=True)
    write_json(trash / 'metadata.json', {'item': item, 'removed_at': int(time.time()), 'reason': reason})
    if move:
        folder.rename(trash / 'mod')
    return trash


def remove(mod_id):
    with mutation_lock():
        data = installed(strict=True)
        item = data.get(mod_id)
        if not item:
            raise ValueError('Mod bulunamadı')
        folder = mod_folder(item)
        trash = _stage_backup(item, move=False)
        from . import transactions
        transaction = transactions.begin('remove', item, None, trash)
        try:
            if trash:
                folder.rename(trash / 'mod')
            _clear_history(item)
            data.pop(mod_id)
            write_json(root() / 'installed.json', data)
        except Exception:
            if trash and (trash / 'mod').exists():
                (trash / 'mod').rename(folder)
            raise
        from .activity import record
        transactions.finish(transaction)
        record('remove', item['name'])


def removed():
    result = []
    for path in (root() / 'removed').glob('*/metadata.json'):
        try:
            record = load_json(path, MAX_METADATA_BYTES)
            item = record['item']
            validate_metadata(item)
            mod_folder(item)
            if type(record.get('removed_at')) is not int:
                continue
            if not (path.parent / 'mod').is_dir() or not re.fullmatch('[a-f0-9]{32}', path.parent.name):
                continue
            result.append({'backup_id': path.parent.name, 'mod_id': item['id'], 'name': item['name'],
                           'category': item.get('category', 'skins'), 'removed_at': record['removed_at'],
                           'version': item['version'], 'reason': record.get('reason', 'removed')})
        except (OSError, ValueError, TypeError, KeyError):
            continue
    return sorted(result, key=lambda r: r['removed_at'], reverse=True)


def restore(backup_id):
    if not isinstance(backup_id, str) or not re.fullmatch('[a-f0-9]{32}', backup_id):
        raise ValueError('Geçersiz yedek')
    with mutation_lock():
        data = installed(strict=True)
        backup = root() / 'removed' / backup_id
        try:
            record = load_json(backup / 'metadata.json', MAX_METADATA_BYTES)
            item = record['item']
            validate_metadata(item)
            folder = mod_folder(item)
        except (OSError, ValueError, TypeError, KeyError):
            raise ValueError('Yedek kaydı okunamadı') from None
        if item['id'] in data:
            raise ValueError('Bu mod zaten mevcut. Önce mevcut sürümü kaldırarak yedekle; sonra istediğin yedeği geri yükle.')
        if folder.exists():
            raise ValueError('Önceki klasör başka dosyalar içeriyor. Yedeği incele → Paket olarak kaydet ile dışa aktarıp yeniden içe aktar. Mevcut dosyalar korundu.')
        source = (backup / 'mod').resolve()
        if not source.is_relative_to((root() / 'removed').resolve()) or not source.is_dir():
            raise ValueError('Yedek dosyaları bulunamadı')
        folder.parent.mkdir(parents=True, exist_ok=True)
        item = dict(item, enabled=False)
        from . import transactions
        transaction = transactions.begin('restore', None, item, backup)
        data[item['id']] = item
        try:
            source.rename(folder)
            write_json(root() / 'installed.json', data)
        except Exception:
            if folder.exists() and not source.exists():
                folder.rename(source)
            raise
        from .activity import record
        transactions.finish(transaction)
        record('restore', item['name'])
        return item


def active_mod(champion_id):
    if not champion_id:
        return None
    for item in installed().values():
        if item.get('category', 'skins') == 'skins' and item.get('enabled') and item.get('champion_id') == champion_id:
            base = (get_user_data_dir() / 'mods').resolve()
            path = (base / item['relative_path']).resolve()
            if path.is_relative_to(base) and path != base and path.is_dir():
                return {'_hub': True, 'champion_id': champion_id, 'skin_id': champion_id * 1000,
                        'storage_skin_id': champion_id * 1000, 'target_skin_ids': [champion_id * 1000],
                        'mod_name': item['folder_name'], 'display_name': item['name'],
                        'mod_path': str(path), 'mod_folder_name': item['folder_name'],
                        'relative_path': item['relative_path']}
    return None
