"""Named sets of installed mod selections; files are never copied into profiles."""
import json
import time
import uuid

from . import library


def list_profiles(strict=False):
    path = library.root() / 'profiles.json'
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or len(data) > 100:
            raise ValueError()
        for key, profile in data.items():
            if (not library.valid_id(key) or not isinstance(profile, dict)
                    or not isinstance(profile.get('name'), str) or not 1 <= len(profile['name']) <= 50
                    or not isinstance(profile.get('mods'), list) or len(profile['mods']) > 2000
                    or not all(library.valid_id(v) for v in profile['mods'])):
                raise ValueError()
        return data
    except (OSError, ValueError):
        if strict:
            raise ValueError('Profil kayıtları okunamadı. Özgün dosya korunuyor.') from None
        return {}


def save(name):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 50:
        raise ValueError('Profil adı 1–50 karakter olmalı.')
    name = name.strip()
    with library.mutation_lock():
        profiles = list_profiles(strict=True)
        if len(profiles) >= 100:
            raise ValueError('En fazla 100 profil kaydedilebilir.')
        if any(p['name'].casefold() == name.casefold() for p in profiles.values()):
            raise ValueError('Bu isimde bir profil var. Yeni bir ad seçin.')
        data = library.installed(strict=True)
        profile_id = uuid.uuid4().hex
        profiles[profile_id] = {'name': name, 'mods': [m['id'] for m in data.values() if m['enabled']],
                                'created_at': int(time.time())}
        library.write_json(library.root() / 'profiles.json', profiles)
        from .activity import record
        record('profile_save', name, len(profiles[profile_id]['mods']))
        return profile_id


def apply(profile_id):
    with library.mutation_lock():
        profile = list_profiles(strict=True).get(profile_id)
        if not profile:
            raise ValueError('Profil bulunamadı.')
        data = library.installed(strict=True)
        missing = [mod_id for mod_id in profile['mods'] if mod_id not in data or not library.mod_folder(data[mod_id]).is_dir()]
        if missing:
            raise ValueError('Profildeki bazı modlar eksik. Önce geri yükleyin veya yeniden ekleyin: ' + ', '.join(missing))
        selected = set(profile['mods'])
        groups = set()
        for mod_id in selected:
            item = data[mod_id]
            category = item.get('category', 'skins')
            group = (category, item.get('champion_id') if category == 'skins' else None)
            if group in groups:
                raise ValueError('Profil aynı şampiyon veya kategori için birden fazla mod içeriyor.')
            groups.add(group)
        from . import selections
        return selections.apply(profile['mods'], 'replace')


def remove(profile_id):
    with library.mutation_lock():
        data = list_profiles(strict=True)
        if profile_id not in data:
            raise ValueError('Profil bulunamadı.')
        data.pop(profile_id)
        library.write_json(library.root() / 'profiles.json', data)


def rename(profile_id, name):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 50:
        raise ValueError('Profil adı 1–50 karakter olmalı.')
    name = name.strip()
    with library.mutation_lock():
        data = list_profiles(strict=True)
        if profile_id not in data:
            raise ValueError('Profil bulunamadı.')
        if any(key != profile_id and p['name'].casefold() == name.casefold() for key, p in data.items()):
            raise ValueError('Bu isimde bir profil var. Farklı bir ad seç.')
        data[profile_id]['name'] = name
        library.write_json(library.root() / 'profiles.json', data)


def update(profile_id):
    """Replace only the selected profile's choices with the current enabled set."""
    with library.mutation_lock():
        data = list_profiles(strict=True)
        if profile_id not in data:
            raise ValueError('Profil bulunamadı.')
        installed = library.installed(strict=True)
        data[profile_id]['mods'] = [m['id'] for m in installed.values() if m['enabled']]
        data[profile_id]['updated_at'] = int(time.time())
        library.write_json(library.root() / 'profiles.json', data)


def export_profile(profile_id):
    """Portable references only: no packages, filesystem paths or credentials."""
    with library.mutation_lock():
        profile = list_profiles(strict=True).get(profile_id)
        if profile is None:
            raise ValueError('Profil bulunamadı.')
        installed = library.installed(strict=True)
        mods = []
        for mod_id in profile['mods']:
            item = installed.get(mod_id, {})
            mods.append({'id': mod_id, 'name': item.get('name', mod_id),
                         'version': item.get('version', '')})
        return {'type': 'okdev-profile', 'schema': 1, 'name': profile['name'], 'mods': mods}


def inspect_portable(document):
    if (not isinstance(document, dict) or document.get('type') != 'okdev-profile'
            or type(document.get('schema')) is not int or document['schema'] != 1
            or not isinstance(document.get('name'), str) or not 1 <= len(document['name'].strip()) <= 50
            or not isinstance(document.get('mods'), list) or len(document['mods']) > 2000):
        raise ValueError('Bu dosya desteklenen bir OKDEV profili değil.')
    seen, mods = set(), []
    installed = library.installed(strict=True)
    for item in document['mods']:
        if (not isinstance(item, dict) or not library.valid_id(item.get('id'))
                or item['id'] in seen or not isinstance(item.get('name'), str)
                or not 1 <= len(item['name']) <= 100 or not isinstance(item.get('version'), str)
                or len(item['version']) > 48):
            raise ValueError('Profildeki mod listesi geçersiz.')
        seen.add(item['id'])
        local = installed.get(item['id'])
        mods.append({'id': item['id'], 'name': item['name'], 'version': item['version'],
                     'available': bool(local and library.mod_folder(local).is_dir()),
                     'version_differs': bool(local and item['version'] and local['version'] != item['version'])})
    return {'name': document['name'].strip(), 'mods': mods,
            'missing': sum(not m['available'] for m in mods),
            'different_versions': sum(m['version_differs'] for m in mods)}


def import_profile(document):
    with library.mutation_lock():
        preview = inspect_portable(document)
        profiles = list_profiles(strict=True)
        if len(profiles) >= 100:
            raise ValueError('En fazla 100 profil kaydedilebilir.')
        name = preview['name']
        taken = {p['name'].casefold() for p in profiles.values()}
        number = 2
        while name.casefold() in taken:
            suffix = f' ({number})'
            name = preview['name'][:50-len(suffix)] + suffix
            number += 1
        profile_id = uuid.uuid4().hex
        profiles[profile_id] = {'name': name, 'mods': [m['id'] for m in preview['mods']],
                                'created_at': int(time.time())}
        library.write_json(library.root() / 'profiles.json', profiles)
        from .activity import record
        record('profile_import', name, len(preview['mods']))
        return {'id': profile_id, 'name': name, 'missing': preview['missing']}
