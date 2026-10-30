"""Named sets of installed mod selections; files are never copied into profiles."""
import time
import uuid
import copy
import json

from . import library

MAX_PROFILE_BYTES = 4 * 1024 * 1024


def list_profiles(strict=False, *, resolve=False):
    path = library.root() / 'profiles.json'
    if not path.exists():
        return {}
    try:
        data = library.load_json(path, library.MAX_INDEX_BYTES)
        if not isinstance(data, dict) or len(data) > 100:
            raise ValueError()
        for key, profile in data.items():
            if (not library.valid_id(key) or not isinstance(profile, dict)
                    or not isinstance(profile.get('name'), str) or not 1 <= len(profile['name']) <= 50
                    or not isinstance(profile.get('mods'), list) or len(profile['mods']) > 2000
                    or not all(library.valid_id(v) for v in profile['mods'])):
                raise ValueError()
            targets = profile.get('targets', {})
            if (not isinstance(targets, dict) or targets.keys() - set(profile['mods']) or
                    any(type(v) is not int or v <= 0 for v in targets.values())):
                raise ValueError()
        if resolve:
            context = {}
            for profile in data.values():
                if 'references' in profile:
                    preview = inspect_portable({'type': 'okdev-profile', 'schema': 2,
                                                'name': profile['name'], 'mods': profile['references']}, _context=context)
                    profile['mods'] = [m['id'] for m in preview['mods']]
                    profile['targets'] = {m['id']: m['target_skin_id'] for m in preview['mods'] if 'target_skin_id' in m}
                    profile['missing'] = preview['missing']
                    profile['missing_names'] = [m['name'] for m in preview['mods'] if not m['available']]
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
        from .selections import skin_targets
        selected = [m['id'] for m in data.values() if m['enabled']]
        profiles[profile_id] = {'name': name, 'mods': [m['id'] for m in data.values() if m['enabled']],
                                'targets': skin_targets(data, selected), 'created_at': int(time.time())}
        library.write_json(library.root() / 'profiles.json', profiles)
        from .activity import record
        record('profile_save', name, len(profiles[profile_id]['mods']))
        return profile_id


def apply(profile_id):
    with library.mutation_lock():
        profile = list_profiles(strict=True, resolve=True).get(profile_id)
        if not profile:
            raise ValueError('Profil bulunamadı.')
        if profile.get('missing'):
            raise ValueError('Profildeki paketler eksik veya içerikleri farklı: ' + ', '.join(profile['missing_names']))
        data = library.installed(strict=True)
        missing = [mod_id for mod_id in profile['mods'] if mod_id not in data or not library.mod_available(data[mod_id])]
        if missing:
            raise ValueError('Profildeki bazı modlar eksik. Önce geri yükleyin veya yeniden ekleyin: ' + ', '.join(missing))
        selected = set(profile['mods'])
        groups = set()
        for mod_id in selected:
            item = data[mod_id]
            category = item.get('category', 'skins')
            from .selections import _group
            group = _group(item)
            if group in groups:
                raise ValueError('Profil aynı şampiyon veya kategori için birden fazla mod içeriyor.')
            groups.add(group)
        from . import selections
        return selections.apply(profile['mods'], 'replace', targets=profile.get('targets'))


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
        data[profile_id].pop('references', None)
        from .selections import skin_targets
        data[profile_id]['targets'] = skin_targets(installed, data[profile_id]['mods'])
        data[profile_id]['updated_at'] = int(time.time())
        library.write_json(library.root() / 'profiles.json', data)


def export_profile(profile_id):
    """Portable references only: no packages, filesystem paths or credentials."""
    with library.mutation_lock():
        profile = list_profiles(strict=True).get(profile_id)
        if profile is None:
            raise ValueError('Profil bulunamadı.')
        if 'references' in profile:
            return {'type': 'okdev-profile', 'schema': 2, 'name': profile['name'],
                    'mods': copy.deepcopy(profile['references'])}
        installed = library.installed(strict=True)
        mods = []
        for mod_id in profile['mods']:
            item = installed.get(mod_id, {})
            mods.append({'id': mod_id, 'name': item.get('name', mod_id),
                         'version': item.get('version', '')})
            if item.get('package_sha256'):
                mods[-1].update(package_sha256=item['package_sha256'], category=item.get('category', 'skins'), champion_id=item.get('champion_id'))
            elif item and library.mod_available(item):
                # Older installations never recorded the original archive hash.
                # Fingerprint their extracted bytes when explicitly exporting.
                mods[-1].update(content_sha256=_content_identity(item), category=item.get('category', 'skins'), champion_id=item.get('champion_id'))
            if mod_id in profile.get('targets', {}):
                mods[-1]['target_skin_id'] = profile['targets'][mod_id]
        document = {'type': 'okdev-profile', 'schema': 2, 'name': profile['name'], 'mods': mods}
        if len(json.dumps(document, ensure_ascii=False, indent=2).encode('utf-8')) > MAX_PROFILE_BYTES:
            raise ValueError('Profil çok büyük. Daha az modla kaydet.')
        return document


def _content_identity(item):
    """Portable identity for legacy installations without the original package."""
    import hashlib
    import os
    import tempfile
    from pathlib import Path
    from contextlib import ExitStack
    from utils.core.junction import archive_digest, is_junction
    with ExitStack() as stack:
        folder = library.mod_folder(item)
        if folder.is_file():
            source = folder
            folder = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            from utils.core.safe_extract import extract_mod_archive
            extract_mod_archive(source, folder)
        files = []
        for directory, names, filenames in os.walk(folder, followlinks=False):
            for name in names + filenames:
                path = Path(directory) / name
                if path.is_symlink() or is_junction(path):
                    raise ValueError('Bağlantılı mod dosyası için taşınabilir kimlik üretilemiyor.')
            files.extend(Path(directory) / name for name in filenames)
        digest = hashlib.sha256()
        for path in sorted(files, key=lambda p: p.relative_to(folder).as_posix().casefold()):
            relative = path.relative_to(folder).as_posix().casefold().encode('utf-8')
            digest.update(len(relative).to_bytes(4, 'little'))
            digest.update(relative)
            digest.update(bytes.fromhex(archive_digest(path)))
        return digest.hexdigest()


def inspect_portable(document, *, _context=None):
    if (not isinstance(document, dict) or document.get('type') != 'okdev-profile'
            or type(document.get('schema')) is not int or document['schema'] not in (1, 2)
            or not isinstance(document.get('name'), str) or not 1 <= len(document['name'].strip()) <= 50
            or not isinstance(document.get('mods'), list) or len(document['mods']) > 2000):
        raise ValueError('Bu dosya desteklenen bir OKDEV profili değil.')
    seen, resolved_seen, mods = set(), set(), []
    context = {} if _context is None else _context
    if 'installed' not in context:
        context['installed'] = library.installed(strict=True)
    installed = context['installed']
    # Build candidates once. A full 2,000-entry profile must not perform four
    # million filesystem probes when packages are missing.
    available = context.setdefault('available', {})
    identities = context.setdefault('identities', {})
    if 'groups' not in context:
        context['groups'] = {}
        for candidate in installed.values():
            context['groups'].setdefault((candidate.get('category', 'skins'), candidate.get('champion_id')), []).append(candidate)
    groups = context['groups']
    def is_available(candidate):
        key = candidate['id']
        if key not in available:
            available[key] = library.mod_available(candidate)
        return available[key]
    def identity(candidate, kind):
        key = (candidate['id'], kind)
        if key not in identities:
            identities[key] = candidate.get(kind) if kind == 'package_sha256' else _content_identity(candidate)
        return identities[key]
    identity_indexes = context.setdefault('indexes', {})
    for item in document['mods']:
        if (not isinstance(item, dict) or not library.valid_id(item.get('id'))
                or item['id'] in seen or not isinstance(item.get('name'), str)
                or not 1 <= len(item['name']) <= 100 or not isinstance(item.get('version'), str)
                or len(item['version']) > 48):
            raise ValueError('Profildeki mod listesi geçersiz.')
        seen.add(item['id'])
        local = installed.get(item['id'])
        if 'package_sha256' in item or 'content_sha256' in item:
            import re
            identity_key = 'package_sha256' if 'package_sha256' in item else 'content_sha256'
            if ('package_sha256' in item and 'content_sha256' in item
                    or not isinstance(item[identity_key], str) or not re.fullmatch('[a-f0-9]{64}', item[identity_key])
                    or not isinstance(item.get('category'), str) or item['category'] not in library.CATEGORIES
                    or (item['category'] != 'skins' and item.get('champion_id') is not None)
                    or (item['category'] == 'skins' and (type(item.get('champion_id')) is not int or item['champion_id'] <= 0))):
                raise ValueError('Profilin paket kimliği geçersiz.')
            def matches_identity(candidate):
                return (candidate.get('category', 'skins') == item['category']
                        and candidate.get('champion_id') == item.get('champion_id')
                        and is_available(candidate)
                        and identity(candidate, identity_key) == item[identity_key])
            # A path-derived legacy ID is not proof of content identity.
            if local is not None and not matches_identity(local):
                local = None
            if local is None:
                group = (item['category'], item.get('champion_id'))
                key = (group, identity_key)
                if key not in identity_indexes:
                    index = {}
                    for candidate in groups.get(group, []):
                        if is_available(candidate):
                            index.setdefault(identity(candidate, identity_key), []).append(candidate)
                    identity_indexes[key] = index
                matches = identity_indexes[key].get(item[identity_key], [])
                if len(matches) == 1:
                    local = matches[0]
        target = item.get('target_skin_id')
        if target is not None and (type(target) is not int or target <= 0):
            raise ValueError('Profilin kostüm hedefi geçersiz.')
        target_available = (target is None or local is not None and local.get('category', 'skins') == 'skins'
                            and target in (local.get('target_skin_ids') or [local['champion_id'] * 1000]))
        resolved_id = local['id'] if local else item['id']
        if resolved_id in resolved_seen:
            raise ValueError('Profilde aynı yerel moda eşleşen birden fazla kayıt var.')
        resolved_seen.add(resolved_id)
        mods.append({'id': resolved_id, 'name': item['name'], 'version': item['version'],
                     'available': bool(local and is_available(local) and target_available),
                     'version_differs': bool(local and item['version'] and local['version'] != item['version'])})
        if target is not None:
            mods[-1]['target_skin_id'] = target
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
                                'targets': {m['id']: m['target_skin_id'] for m in preview['mods'] if 'target_skin_id' in m},
                                'references': [{key: copy.deepcopy(value) for key, value in m.items()
                                    if key in {'id', 'name', 'version', 'category', 'champion_id',
                                               'package_sha256', 'content_sha256', 'target_skin_id'}} for m in document['mods']],
                                'created_at': int(time.time())}
        library.write_json(library.root() / 'profiles.json', profiles)
        from .activity import record
        record('profile_import', name, len(preview['mods']))
        return {'id': profile_id, 'name': name, 'missing': preview['missing']}
