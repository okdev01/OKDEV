"""Apply user-selected installation paths once, preserving existing settings."""
import json
import sys
from pathlib import Path


def apply_install_paths():
    if not getattr(sys, 'frozen', False):
        return
    path = Path(sys.executable).parent / 'okdev-install.json'
    if not path.is_file():
        return
    from config import get_config_file_path, edit_config_file
    data = json.loads(path.read_text(encoding='utf-8'))
    game = Path(data['game_dir'])
    if not (game / 'League of Legends.exe').is_file():
        return  # Let normal game discovery/settings handle a moved installation.
    config_path = get_config_file_path()
    with edit_config_file(config_path) as settings:
        if not settings.has_section('General'):
            settings.add_section('General')
        if settings.get('General', 'okdev_install_id', fallback='') == data['install_id']:
            return
        settings.set('General', 'leaguePath', str(game))
        settings.set('General', 'clientPath', str(game.parent))
        settings.set('General', 'okdev_install_id', data['install_id'])
