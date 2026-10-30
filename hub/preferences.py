"""Small, explicit user preferences shared by the desktop and game companion."""
from . import library
from copy import deepcopy

LANES = ('top', 'jungle', 'mid', 'adc', 'support')

DEFAULTS = {
    'auto_ban_enabled': False,
    'auto_ban_priority': [],
    'auto_pick_enabled': False,
    'lane_automation': False,
    'lane_profiles': {lane: {'pick': [], 'ban': []} for lane in LANES},
    'mobalytics_enabled': False,
    'mobalytics_auto_show': True,
    'mobalytics_hotkey': 'Ctrl+Shift+B',
    'mobalytics_position': 'right',
    'mobalytics_size': 'normal',
    'theme': 'dark',
    'compact_cards': False,
    'reduce_motion': False,
    'start_minimized': False,
    'data_saver': True,
    'mod_view': 'grid',
}
OPTIONS = {
    'mobalytics_hotkey': ('Ctrl+Shift+B', 'Ctrl+Shift+M', 'Alt+B'),
    'mobalytics_position': ('right', 'left'),
    'mobalytics_size': ('compact', 'normal', 'wide'),
    'theme': ('dark', 'light', 'system'),
    'mod_view': ('grid', 'list'),
}


def valid(key, value):
    if key == 'lane_profiles':
        return (isinstance(value, dict) and set(value) == set(LANES)
                and all(isinstance(profile, dict) and set(profile) == {'pick', 'ban'}
                        and all(valid('auto_ban_priority', ids) for ids in profile.values())
                        for profile in value.values()))
    if key == 'auto_ban_priority':
        from .guides import champions
        return (isinstance(value, list) and len(value) <= 10
                and all(type(c) is int and c in champions() for c in value)
                and len(set(value)) == len(value))
    return (key in DEFAULTS and
            (value in OPTIONS[key] if key in OPTIONS and isinstance(value, str)
             else type(value) is bool if type(DEFAULTS[key]) is bool else False))


def get():
    stored = library._settings_data()
    return {key: deepcopy(stored[key] if key in stored and valid(key, stored[key]) else default)
            for key, default in DEFAULTS.items()}


def update(changes):
    if not isinstance(changes, dict) or not changes or not all(valid(key, value) for key, value in changes.items()):
        raise ValueError('Bu tercih kaydedilemedi. Geçerli bir seçenek seç.')
    with library._lock, library.settings_lock(library.root() / 'settings.json'):
        stored = library._settings_data(strict=True)
        for key, default in DEFAULTS.items():
            if key in stored and not valid(key, stored[key]):
                stored[key] = deepcopy(default)
        stored.update(changes)
        profiles = stored.get('lane_profiles', DEFAULTS['lane_profiles'])
        lane_mode = stored.get('lane_automation', False)
        if stored.get('auto_ban_enabled') and not (any(p['ban'] for p in profiles.values()) if lane_mode else stored.get('auto_ban_priority')):
            if changes.get('auto_ban_enabled'):
                raise ValueError('Otomatik ban için önce şampiyon ekle.')
            stored['auto_ban_enabled'] = False
        if stored.get('auto_pick_enabled') and not any(p['pick'] for p in profiles.values()):
            if changes.get('auto_pick_enabled'):
                raise ValueError('Otomatik seçim için önce bir koridora şampiyon ekle.')
            stored['auto_pick_enabled'] = False
        library.write_json(library.root() / 'settings.json', stored)
    return get()
