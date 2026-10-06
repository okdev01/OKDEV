"""Read bounded, optional Fantome metadata without extracting game data."""
import json
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

MAX_INFO = 64 * 1024


def slug(value):
    value = unicodedata.normalize('NFKD', value.replace('ı', 'i')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', value).strip('-')[:64].rstrip('-')


def inspect(path):
    path = Path(path)
    from .library import MAX_DOWNLOAD
    if path.stat().st_size > MAX_DOWNLOAD:
        raise ValueError('Mod en fazla 512 MB olabilir')
    suggested, warning = {}, ''
    try:
        with zipfile.ZipFile(path) as archive:
            files = archive.infolist()
            info = next((f for f in files if f.filename.lower() in {'info/info.json', 'meta/info.json'}), None)
            if info is None:
                info = next((f for f in files if f.filename.lower() == 'meta/okdev-backup.json'), None)
            if info and info.file_size <= MAX_INFO:
                try:
                    raw = json.loads(archive.read(info))
                    if isinstance(raw, dict):
                        if info.filename.lower() == 'meta/okdev-backup.json':
                            from .library import CATEGORIES
                            if raw.get('category') in CATEGORIES:
                                suggested['category'] = raw['category']
                        for key, limit in [('name', 100), ('description', 2000), ('author', 100)]:
                            value = raw.get(key.title(), raw.get(key))
                            if isinstance(value, str) and value.strip():
                                suggested[key] = value.strip()[:limit]
                        version = raw.get('Version', raw.get('version'))
                        if isinstance(version, str) and len(version) <= 48 and re.fullmatch(r'[0-9]+(?:\.[0-9]+){2,4}', version):
                            suggested['version'] = version
                except (ValueError, RuntimeError):
                    warning = 'Paket bilgileri okunamadı. Alanları elle doldurabilirsin.'
            base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
            champions = json.loads((base / 'hub/web/champions.json').read_text(encoding='utf-8'))['champions']
            names = {slug(c['name']).replace('-', ''): c for c in champions}
            names['monkeyking'] = next(c for c in champions if c['id'] == 62)
            found = {}
            for member in files:
                match = re.fullmatch(r'wad/([^/]+)\.wad\.client(?:/.*)?', member.filename.lower())
                if match and match[1] in names:
                    champion = names[match[1]]
                    found[champion['id']] = champion
            if len(found) == 1:
                champion = next(iter(found.values()))
                suggested.update(champion=champion['name'], champion_id=champion['id'], category='skins')
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError):
        raise ValueError('Bu dosya okunabilir bir .fantome veya .zip paketi değil.') from None
    suggested.setdefault('name', path.stem[:100])
    suggested['id'] = slug(suggested['name']) or 'yerel-mod'
    return {'name': path.name, 'suggested': suggested, 'warning': warning}
