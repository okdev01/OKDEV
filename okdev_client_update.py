"""Pause only League's UX during an approved update; keep its backend/login alive."""
from pathlib import Path
import json
import time

import psutil

SAFE_PHASES = frozenset({'None', 'Lobby', 'EndOfGame'})
GAME_NAMES = frozenset({'league of legends.exe', 'league of legends (tm) client.exe'})
UX_NAMES = frozenset({'leagueclientux.exe', 'leagueclientuxrender.exe'})
CLIENT_NAMES = UX_NAMES | {'leagueclient.exe'}


def process_names():
    return {(p.info.get('name') or '').lower() for p in psutil.process_iter(['name'])}


def connection():
    from lcu.core.lcu_connection import LCUConnection
    return LCUConnection()


def safe_to_update():
    """An unknown phase fails closed; queues, ready checks and champ select wait."""
    try:
        names = process_names()
        if names & GAME_NAMES:
            return False
        if not names & CLIENT_NAMES:
            return True
        client = connection()
        try:
            if not client.ok:
                return False
            response = client.session.get(client.base+'/lol-gameflow/v1/gameflow-phase', timeout=3)
            return response.status_code == 200 and response.json() in SAFE_PHASES
        finally:
            client.session.close()
    except (psutil.Error, OSError, ValueError):
        return False
    except Exception:
        return False


class ClientPause:
    def __init__(self, resume_file):
        self.resume_file = Path(resume_file)
        self.client = None
        self.resume_needed = False

    def require_safe(self):
        if process_names() & GAME_NAMES:
            raise RuntimeError('Güncelleme maç bitince uygulanacak; oyun kapatılmadı.')
        if self.client is not None:
            response = self.client.session.get(self.client.base+'/lol-gameflow/v1/gameflow-phase', timeout=3)
            if response.status_code != 200 or response.json() not in SAFE_PHASES:
                raise RuntimeError('İstemci uygun durumda değil; güncelleme ertelendi.')

    def pause(self):
        from utils.core.atomic_file import atomic_write
        names = process_names()
        if not names & CLIENT_NAMES:
            self.require_safe()
            return
        self.client = connection()
        if not self.client.ok:
            raise RuntimeError('League durumuna ulaşılamadı; istemciye dokunulmadı.')
        self.require_safe()
        if not names & UX_NAMES:
            return
        # Persist before the request: a network timeout may still mean UX closed.
        with atomic_write(self.resume_file) as stream:
            json.dump({'resume_ux': True}, stream)
        self.resume_needed = True
        response = self.client.session.post(self.client.base+'/riotclient/kill-ux', timeout=5)
        if not 200 <= response.status_code < 300:
            raise RuntimeError('League arayüzü durdurulamadı; güncelleme uygulanmadı.')
        deadline = time.monotonic()+15
        while process_names() & UX_NAMES:
            if time.monotonic() >= deadline:
                raise RuntimeError('League arayüzü kapanmadı; dosyalar değiştirilmedi.')
            self.require_safe()
            time.sleep(.2)
        self.require_safe()

    def resume(self):
        try:
            if not self.resume_needed:
                return
            if process_names() & UX_NAMES:
                self.resume_file.unlink(missing_ok=True)
                return
            if self.client is None or not self.client.ok:
                self.client = connection()
            if not self.client.ok:
                raise RuntimeError('League arayüzü açılamadı. League istemcisini yeniden açın.')
            response = self.client.session.post(self.client.base+'/riotclient/launch-ux', timeout=5)
            if not 200 <= response.status_code < 300:
                raise RuntimeError('League arayüzünü açma isteği başarısız. League istemcisini yeniden açın.')
            deadline = time.monotonic()+20
            while not process_names() & UX_NAMES:
                if time.monotonic() >= deadline:
                    raise RuntimeError('League arayüzünün açılması doğrulanamadı. Sonraki açılışta yeniden denenecek.')
                time.sleep(.2)
            self.resume_file.unlink(missing_ok=True)
        finally:
            if self.client is not None:
                self.client.session.close()


def recover_client(resume_file):
    """Recover a helper interruption without storing LCU credentials on disk."""
    resume_file = Path(resume_file)
    if not resume_file.is_file():
        return
    names = process_names()
    if names & UX_NAMES or not names & CLIENT_NAMES:
        resume_file.unlink(missing_ok=True)
        return
    guard = ClientPause(resume_file)
    guard.resume_needed = True
    guard.resume()


def sync_runtime(install):
    """Refresh the unloaded runtime before UX can load its new core/plugins."""
    import shutil
    from utils.core.paths import get_user_data_dir
    from utils.integration.pengu_loader import _snapshot_plugin_enable_state, _restore_plugin_enable_state
    bundled = Path(install)/'_internal/Pengu Loader'
    if not bundled.is_dir():
        return
    runtime = get_user_data_dir()/'Pengu Loader'
    runtime.mkdir(parents=True, exist_ok=True)
    enabled, disabled = _snapshot_plugin_enable_state(runtime)
    shutil.copytree(bundled, runtime, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('datastore', 'config', '*.log', '*.log.old'))
    _restore_plugin_enable_state(runtime, enabled, disabled)
