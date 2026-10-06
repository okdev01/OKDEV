"""Reconcile desktop category selections immediately before an overlay is built."""
from . import library


def apply_category_selections(state):
    items = [m for m in library.installed().values() if m.get('category', 'skins') != 'skins']
    owned = {m['relative_path'] for m in items}
    selected = {}
    for item in items:
        path = library.mod_folder(item)
        if item['enabled'] and path.is_dir():
            selected[item['category']] = {
                '_hub': True, 'mod_name': item['folder_name'], 'display_name': item['name'],
                'mod_path': str(path), 'mod_folder_name': item['folder_name'],
                'relative_path': item['relative_path'],
            }
    for category, attr in [('maps', 'selected_map_mod'), ('fonts', 'selected_font_mod'),
                           ('announcers', 'selected_announcer_mod')]:
        current = getattr(state, attr, None)
        if category in selected:
            setattr(state, attr, selected[category])
        elif current and (current.get('_hub') or current.get('relative_path') in owned):
            setattr(state, attr, None)
    current = getattr(state, 'selected_other_mods', None) or []
    if not current and getattr(state, 'selected_other_mod', None):
        current = [state.selected_other_mod]
    remaining = [m for m in current if not m.get('_hub') and m.get('relative_path') not in owned]
    if 'ui' in selected:
        remaining.append(selected['ui'])
    state.selected_other_mods = remaining
    state.selected_other_mod = remaining[0] if remaining else None
