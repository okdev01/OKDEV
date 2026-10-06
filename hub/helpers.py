import threading
import time
from .library import settings


class AutoAccept:
    def __init__(self):
        self.attempted = False

    def tick(self, lcu, enabled, phase=None):
        if not enabled:
            self.attempted = False
            return False
        if (lcu.phase if phase is None else phase) != 'ReadyCheck':
            self.attempted = False
            return False
        ready = lcu.get('/lol-matchmaking/v1/ready-check')
        if not isinstance(ready, dict) or ready.get('state') != 'InProgress' or ready.get('playerResponse') != 'None':
            return False
        if self.attempted:
            return False
        response = lcu.s.post(lcu.base + '/lol-matchmaking/v1/ready-check/accept', json={}, timeout=3)
        if response.ok:
            self.attempted = True
            return True
        return False


def tick_helpers(lcu, accept, tracker, log):
    """A failed optional guide must never prevent the independent ready check."""
    from . import companion, preferences
    try:
        lcu.refresh_if_needed()
        connected = lcu.ok
        phase = lcu.phase if connected else None
    except Exception as exc:
        connected, phase = False, None
        log.debug('OKDEV client unavailable: %s', type(exc).__name__)
    try:
        accept.tick(lcu, settings()['auto_accept'], phase=phase or '')
    except Exception as exc:
        log.debug('OKDEV ready check unavailable: %s', type(exc).__name__)
    try:
        prefs = preferences.get()
        session = None
        if phase == 'ChampSelect':
            try:
                session = lcu.session
            except Exception:
                pass  # Tracker tolerates brief missing sessions, then clears stale picks.
        data, actions = tracker.update(phase, session, connected=connected, prefs=prefs)
        if prefs['mobalytics_enabled'] and not companion.ensure_running():
            tracker.shown_key = None  # Retry a locked pick after startup cooldown.
        for action in actions:
            if action != 'disable':
                companion.command(action, data.get('pick'))
    except Exception as exc:
        tracker.shown_key = None
        log.debug('OKDEV guide unavailable: %s', type(exc).__name__)


def start_helpers(state):
    def worker():
        from lcu import LCU
        from utils.core.logging import get_logger
        lcu = LCU()
        accept = AutoAccept()
        from .guides import GuideTracker
        from . import companion
        tracker = GuideTracker()
        while not state.stop:
            tick_helpers(lcu, accept, tracker, get_logger())
            time.sleep(2)
        companion.command('quit')
    threading.Thread(target=worker, daemon=True, name='okdev-assistants').start()
