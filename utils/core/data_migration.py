"""Copy legacy user data once, without changing the original installation."""
import configparser
import json
import os
import shutil
import uuid
from pathlib import Path


def migrate_datastore(path: Path) -> None:
    """Alias old app-owned preference keys; keep all third-party values intact."""
    if not path.is_file():
        return
    key = b'A5dgY6lz9fpG9kGNiH1mZ'
    raw = path.read_bytes()
    decoded = bytes(value ^ key[i % len(key)] for i, value in enumerate(raw))
    try:
        data = json.loads(decoded.decode('utf-8'))
    except (ValueError, UnicodeError):
        return  # Unknown format: preserve the original bytes.
    if not isinstance(data, dict):
        return
    for old, value in list(data.items()):
        if old.startswith(('Rose-', 'ROSE-', 'rose-')):
            prefix = 'okdev' if old.startswith('rose') else 'OKDEV'
            data.setdefault(prefix + old[4:], value)
    encoded = json.dumps(data, ensure_ascii=False).encode('utf-8')
    path.write_bytes(bytes(value ^ key[i % len(key)] for i, value in enumerate(encoded)))


def migrate_legacy_data(destination: Path) -> None:
    legacy = destination.with_name('Rose')
    if destination.exists() or not legacy.is_dir():
        return
    staging = destination.with_name('.okdev-migration-' + uuid.uuid4().hex)
    staging.mkdir(parents=True)
    try:
        # Never carry over live locks, activation sessions, or pending updates.
        for name in ('config.ini', 'skins', 'classic', 'resources', 'mods',
                     'historic.json', 'party_keys.json', 'party_sessions.json', 'base_skin_samples.json'):
            source = legacy / name
            if source.is_symlink() or (hasattr(source, 'is_junction') and source.is_junction()):
                raise OSError(f'Cannot migrate linked user data: {source}')
            if source.is_dir():
                shutil.copytree(source, staging / name)
            elif source.is_file():
                shutil.copy2(source, staging / name)
        old_loader = legacy / 'Pengu Loader'
        new_loader = staging / 'Pengu Loader'
        if old_loader.is_dir():
            new_loader.mkdir()
            for name in ('datastore', 'config'):
                if (old_loader / name).is_file():
                    shutil.copy2(old_loader / name, new_loader / name)
            migrate_datastore(new_loader / 'datastore')
            if (old_loader / 'plugins').is_dir():
                shutil.copytree(old_loader / 'plugins', new_loader / 'plugins')
                for plugin in (new_loader / 'plugins').iterdir():
                    if plugin.name.startswith('ROSE-'):
                        plugin.rename(plugin.with_name(plugin.name.replace('ROSE-', 'OKDEV-', 1)))
        config_path = staging / 'config.ini'
        if config_path.exists():
            encoding = 'mbcs' if os.name == 'nt' else 'utf-8'
            data = config_path.read_bytes()
            try:
                text = data.decode('utf-16' if data.startswith(b'\xff\xfe') else 'utf-8-sig')
            except UnicodeDecodeError:
                text = data.decode(encoding)
            parser = configparser.ConfigParser(interpolation=None)
            parser.read_string(text)
            for key in ('installed_version', 'update_retry_count', 'loaderpath', 'disabled'):
                parser.remove_option('General', key)
            with config_path.open('w', encoding='utf-16' if os.name == 'nt' else 'utf-8') as stream:
                parser.write(stream)
        (staging / 'migration-from-rose.txt').write_text(
            'User data copied from ' + str(legacy) + '. Original data retained.\n', encoding='utf-8')
        staging.rename(destination)
    finally:
        if staging.exists() and staging.resolve().parent == destination.resolve().parent:
            shutil.rmtree(staging)
