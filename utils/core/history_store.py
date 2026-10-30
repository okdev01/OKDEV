"""Shared locking and lossless recovery for selection history files."""
import hashlib
import json
import threading
from contextlib import contextmanager

from hub.locking import settings_lock
from utils.core.atomic_file import atomic_write

_lock = threading.RLock()
_local = threading.local()


@contextmanager
def history_lock(directory):
    directory.mkdir(parents=True, exist_ok=True)
    key = str(directory.resolve()).casefold()
    with _lock:
        active = getattr(_local, 'active', set())
        if key in active:
            yield
            return
        with settings_lock(directory / 'history-state.json'):
            _local.active = active | {key}
            try:
                yield
            finally:
                _local.active = active


def read_mapping(path):
    """Retain invalid bytes before allowing a new history to replace them.

    I/O failures propagate: a caller must not overwrite an unreadable file or
    an invalid file that couldn't be backed up. Identical damage is saved once.
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {}
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError('Expected a history object')
        return value
    except (ValueError, UnicodeError, RecursionError):
        digest = hashlib.sha256(raw).hexdigest()
        backup = path.with_name(path.stem + '.corrupt-' + digest + '.json')
        if not backup.exists() or backup.read_bytes() != raw:
            with atomic_write(backup, 'wb') as stream:
                stream.write(raw)
        return {}
