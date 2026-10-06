"""Small, explicit user preferences shared by the desktop and game companion."""
from . import library

DEFAULTS = {
    'mobalytics_enabled': False,
    'mobalytics_auto_show': True,
    'mobalytics_hotkey': 'Ctrl+Shift+B',
    'mobalytics_position': 'right',
    'mobalytics_size': 'normal',
    'theme': 'dark',
    'compact_cards': False,
    'reduce_motion': False,
    'start_minimized': False,
}
OPTIONS = {
    'mobalytics_hotkey': ('Ctrl+Shift+B', 'Ctrl+Shift+M', 'Alt+B'),
    'mobalytics_position': ('right', 'left'),
    'mobalytics_size': ('compact', 'normal', 'wide'),
    'theme': ('dark', 'light', 'system'),
}


def valid(key, value):
    return (key in DEFAULTS and
            (value in OPTIONS[key] if key in OPTIONS and isinstance(value, str)
             else type(value) is bool if type(DEFAULTS[key]) is bool else False))


def get():
    stored = library._settings_data()
    return {key: stored[key] if key in stored and valid(key, stored[key]) else default
            for key, default in DEFAULTS.items()}


def update(changes):
    if not isinstance(changes, dict) or not changes or not all(valid(key, value) for key, value in changes.items()):
        raise ValueError('Bu tercih kaydedilemedi. Geçerli bir seçenek seç.')
    with library._lock, library.settings_lock(library.root() / 'settings.json'):
        stored = library._settings_data(strict=True)
        stored.update(changes)
        library.write_json(library.root() / 'settings.json', stored)
    return get()
