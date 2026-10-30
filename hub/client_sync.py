"""Bridge legacy client storage and selections to the shared Hub registry."""
import hashlib
import time

from . import library


def _record(storage, path, category, champion_id=None, targets=(), display_name=None):
    relative = path.relative_to(storage.mods_root).as_posix()
    return dict(id='local-' + hashlib.sha256(relative.encode()).hexdigest()[:32],
                name=(display_name or path.name)[:100], description='', version='1.0.0',
                category=category, champion_id=champion_id, champion=str(champion_id or ''),
                relative_path=relative, folder_name=path.name, target_skin_ids=list(targets),
                enabled=False, installed_at=int(time.time()))


def reconcile(storage=None, data=None):
    from injection.mods.storage import ModStorageService
    from utils.core.historic import load_historic_map, load_historic_target_map
    from utils.core.mod_historic import load_mod_historic
    storage = storage or ModStorageService()
    if storage.mods_root.resolve() != (library.get_user_data_dir() / 'mods').resolve():
        raise ValueError('Mod deposu ile kütüphane konumu uyuşmuyor.')
    with library.mutation_lock():
        data = library.installed(strict=True) if data is None else data
        known = {item['relative_path'] for item in data.values()}
        candidates = []
        for directory in storage.skins_dir.iterdir():
            if directory.is_dir() and directory.name.isdigit() and int(directory.name) % 1000 == 0:
                champion = int(directory.name) // 1000
                for entry in storage.list_mods_for_champion(champion):
                    candidates.append(_record(storage, entry.path, 'skins', champion, entry.target_skin_ids, entry.display_name))
        for category in storage.MOD_CATEGORIES:
            for entry in storage.list_mods_for_category(category):
                candidates.append(_record(storage, storage.mods_root / entry['path'], category, display_name=entry.get('displayName')))
        histories = load_mod_historic()
        targets = load_historic_target_map()
        selected = {v[5:] for v in load_historic_map().values() if isinstance(v, str) and v.startswith('path:')}
        for value in histories.values():
            selected.update(value if isinstance(value, list) else [value])
        added = 0
        from .selections import _group
        occupied, repaired = set(), 0
        # Repair conflicts left by older migrations before importing more legacy
        # choices. Prefer the most recently installed available entry.
        for item in sorted(data.values(), key=lambda m: (library.mod_available(m), m.get('installed_at', 0), m['id']), reverse=True):
            if not item['enabled']:
                continue
            group = _group(item)
            if group in occupied:
                item['enabled'] = False
                repaired += 1
            else:
                occupied.add(group)
        for item in candidates:
            if item['relative_path'] in known:
                continue
            try:
                library.validate_metadata(item)
                if not library.mod_available(item):
                    continue
            except ValueError:
                continue  # Legacy per-skin layouts remain readable by storage.
            group = _group(item)
            item['enabled'] = item['relative_path'] in selected and group not in occupied
            if item['enabled']:
                occupied.add(group)
            target = targets.get(str(item.get('champion_id')))
            if target in item['target_skin_ids']:
                item['selected_target_skin_id'] = target
            data[item['id']] = item
            known.add(item['relative_path'])
            added += 1
        if added or repaired:
            library.write_json(library.root() / 'installed.json', data)
        if repaired:
            from .activity import record
            record('recovery', 'Çakışan eski mod seçimleri düzeltildi', repaired)
        return added


def select(category, paths, *, champion_id=None, skin_id=None):
    """Commit a validated client selection before the next overlay is built."""
    with library.mutation_lock():
        data = library.installed(strict=True)
        wanted = {str(path).replace('\\', '/') for path in paths}
        if wanted - {item['relative_path'] for item in data.values()}:
            reconcile(data=data)
        changed = False
        for item in data.values():
            if item.get('category', 'skins') != category or (category == 'skins' and item['champion_id'] != champion_id):
                continue
            enabled = item['relative_path'] in wanted
            changed |= item['enabled'] != enabled
            item['enabled'] = enabled
            targets = (item.get('target_skin_ids') or [champion_id * 1000]) if champion_id else []
            if enabled and skin_id in targets:
                changed |= item.get('selected_target_skin_id') != skin_id
                item['selected_target_skin_id'] = skin_id
        if changed:
            library.write_json(library.root() / 'installed.json', data)


def select_other(relative_path=None, *, enabled=True):
    """Apply a single client action to the current registry, never a stale UI list."""
    categories = {'ui', 'voiceover', 'loading_screen', 'vfx', 'sfx', 'others'}
    from .selections import _group
    with library.mutation_lock():
        data = library.installed(strict=True)
        reconcile(data=data)
        item = None
        if relative_path is not None:
            relative = str(relative_path).replace('\\', '/').casefold()
            item = next((m for m in data.values() if m['relative_path'].casefold() == relative), None)
            if not item or item.get('category') not in categories:
                raise ValueError('Seçilen mod artık kütüphanede yok. Listeyi yenile.')
            if enabled and not library.mod_available(item):
                raise ValueError('Mod dosyaları bulunamadı. Modu yeniden ekle.')
        elif enabled:
            raise ValueError('Mod seçimi boş olamaz.')
        for current in data.values():
            if current.get('category') not in categories:
                continue
            if item is None:
                current['enabled'] = False
            elif current['id'] == item['id']:
                current['enabled'] = enabled
            elif enabled and _group(current) == _group(item):
                current['enabled'] = False
        library.write_json(library.root() / 'installed.json', data)


def select_category(category, relative_path=None):
    """Select one map/font/announcer using the same registry as the desktop."""
    if category not in ('maps', 'fonts', 'announcers'):
        raise ValueError('Geçersiz tekli mod kategorisi.')
    with library.mutation_lock():
        data = library.installed(strict=True)
        reconcile(data=data)
        if relative_path is None:
            select(category, [])
            return
        relative = str(relative_path).replace('\\', '/').casefold()
        item = next((m for m in data.values() if m.get('category') == category
                     and m['relative_path'].casefold() == relative), None)
        if item is None:
            raise ValueError('Mod kütüphanede bulunamadı. Listeyi yenile.')
        library.enable(item['id'], True)


def history_path_allowed(relative_path):
    """Legacy history may fill an unknown selection, never override a known one."""
    relative = str(relative_path).replace('\\', '/').casefold()
    for item in library.installed(strict=True).values():
        if item['relative_path'].casefold() == relative:
            return item['enabled']
    # A deleted record must not turn into an allowed legacy selection. Legacy
    # entries are accepted only while their original payload still exists.
    from pathlib import PurePosixPath
    path = PurePosixPath(str(relative_path).replace('\\', '/'))
    if path.is_absolute() or '..' in path.parts or not path.parts or ':' in str(path):
        return False
    root = (library.get_user_data_dir() / 'mods').resolve()
    candidate = (root / str(path)).resolve()
    return candidate.is_relative_to(root) and candidate != root and candidate.exists()


def category_history(mod_type):
    """Expose the committed selection to the client, falling back only for legacy entries."""
    from utils.core.mod_historic import get_historic_mod
    if mod_type == 'other':
        values = []
        for category in ('ui', 'voiceover', 'loading_screen', 'vfx', 'sfx', 'others'):
            current = category_history(category)
            values.extend(current if isinstance(current, list) else [current] if current else [])
        return values or None
    category = {'map': 'maps', 'font': 'fonts', 'announcer': 'announcers'}.get(mod_type, mod_type)
    items = [m for m in library.installed(strict=True).values() if m.get('category', 'skins') == category]
    if not items:
        return get_historic_mod(mod_type)
    selected = [m['relative_path'] for m in items if m['enabled'] and library.mod_available(m)]
    if category in ('maps', 'fonts', 'announcers'):
        return selected[-1] if selected else None
    return selected or None


def category_authoritative(category, history=None):
    """Known registry choices (including an empty choice) must never be replayed."""
    category = {'map': 'maps', 'font': 'fonts', 'announcer': 'announcers'}.get(category, category)
    return not history or any(m.get('category', 'skins') == category
                              for m in library.installed(strict=True).values())


def champion_history(champion_id):
    from utils.core.historic import get_historic_skin_for_champion
    active = library.active_mod(champion_id)
    if active:
        return 'path:' + active['relative_path']
    value = get_historic_skin_for_champion(champion_id)
    if isinstance(value, str) and value.startswith('path:') and not history_path_allowed(value[5:]):
        return None
    return value


def rename(storage, *, name, category='skins', champion_id=None, mod_name=None, relative_path=None):
    """Commit the client alias and the shared display name under one library lock."""
    with library.mutation_lock():
        reconcile(storage)
        data = library.installed(strict=True)
        base = storage.get_champion_dir(champion_id) if category == 'skins' else storage.mods_root / category
        path = storage._resolve_mod_path(base, relative_path) if relative_path else base / str(mod_name)
        path = path.resolve() if path is not None else None
        item = next((m for m in data.values() if library.mod_folder(m) == path), None)
        if item is None and not relative_path and mod_name:
            item = next((m for m in data.values() if library.mod_folder(m).parent == base.resolve()
                         and library.mod_folder(m).is_file() and library.mod_folder(m).stem == mod_name), None)
        manifest = base / (storage.TARGET_METADATA if category == 'skins' else storage.CATEGORY_METADATA)
        previous = manifest.read_bytes() if manifest.exists() else None
        try:
            if category == 'skins':
                display = storage.set_champion_mod_display_name(champion_id, name, mod_name=mod_name, relative_path=relative_path)
            else:
                display = storage.set_category_mod_display_name(category, mod_name, name)
            if item:
                item['name'] = display[:100]
                library.write_json(library.root() / 'installed.json', data)
            return display
        except Exception:
            if previous is not None:
                with library.atomic_write(manifest, 'wb') as stream:
                    stream.write(previous)
            raise
