"""Reuse an approved, hashed download; apply once the client reaches a safe phase."""
import hashlib
import json
from pathlib import Path
import re
import sys
import threading
import time

from config import APP_VERSION, get_config_file_path
from utils.core.atomic_file import atomic_write


def location():
    return get_config_file_path().parent/'updates/pending-update.json'


def updater_running():
    import psutil
    return any((p.info.get('name') or '').lower() == 'okdev-updater.exe'
               for p in psutil.process_iter(['name']))


def remember(version, digest, install):
    path = location()
    with atomic_write(path) as stream:
        json.dump({'version': version.lstrip('v'), 'sha256': digest, 'install': str(Path(install).resolve())}, stream)


def approved(version, digest, install):
    try:
        info = json.loads(location().read_text(encoding='utf-8'))
        return info == {'version': version.lstrip('v'), 'sha256': digest, 'install': str(Path(install).resolve())}
    except (OSError, ValueError):
        return False


def launch_pending(status=lambda text: None):
    from .update_installer import UpdateInstaller
    from .update_sequence import _parse_semver_like
    from okdev_client_update import safe_to_update
    path = location()
    try:
        info = json.loads(path.read_text(encoding='utf-8'))
        version = info['version']
        if not re.fullmatch(r'\d+\.\d+\.\d+', version) or not re.fullmatch('[0-9a-f]{64}', info['sha256']):
            raise ValueError('Invalid pending update')
        install = Path(sys.executable).resolve().parent
        if Path(info['install']).resolve() != install:
            return False
        if _parse_semver_like(version) <= _parse_semver_like(APP_VERSION):
            path.unlink(missing_ok=True)
            return False
        if updater_running() or not safe_to_update():
            return False
        root = path.parent/version
        archive = root/f'OKDEV_Update_{version}.zip'
        with archive.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != info['sha256']:
                raise ValueError('Bekleyen güncellemenin SHA-256 değeri uyuşmuyor.')
        installer = UpdateInstaller()
        staging = installer.extract_update(archive, root/'staging', lambda _: None, status)
        if staging is None:
            return False
        manifest = json.loads((staging/'okdev-update.json').read_text(encoding='utf-8'))
        if manifest.get('version') != version:
            raise ValueError('Bekleyen paket sürümü uyuşmuyor.')
        # A queue may start while extracting a large package.
        if not safe_to_update():
            return False
        params = installer.prepare_updater_launch(staging, install, root, archive, staging, status)
        if not params:
            return False
        params['restart_client'] = True
        return installer.launch_updater(params, install, root, archive, staging, status)
    except FileNotFoundError:
        return False


def start_watcher(state):
    if not getattr(sys, 'frozen', False):
        return
    def worker():
        from main.core.state import get_app_state
        from utils.core.logging import get_logger
        log = get_logger()
        # Wait for normal application startup and its single-instance guard.
        while not state.stop:
            time.sleep(10)
            if state.stop:
                return
            try:
                app = get_app_state()
                if location().exists() and launch_pending(log.info):
                    app.updating = True
                    state.stop = True  # Normal cleanup; helper owns the UX pause/resume.
                    return
            except Exception as exc:
                log.warning('Bekleyen güncelleme ertelendi: %s', type(exc).__name__)
    threading.Thread(target=worker, name='OKDEV-PendingUpdate', daemon=True).start()
