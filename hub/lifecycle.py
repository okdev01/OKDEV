"""Short-lived, process-specific shutdown handoff from the tray application."""
import json
import os
import time

from . import library


def request_shutdown(pid):
    if type(pid) is not int or pid <= 0:
        raise ValueError('Geçersiz uygulama işlemi.')
    library.write_json(library.root() / 'shutdown.json', {'pid': pid, 'created_at': time.time()})


def consume_shutdown(started_at):
    path = library.root() / 'shutdown.json'
    try:
        if not path.exists() or path.stat().st_size > 1024 or path.is_symlink():
            return False
        value = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(value, dict) or type(value.get('pid')) is not int or value['pid'] != os.getpid()
                or type(value.get('created_at')) not in (int, float)
                or not started_at - 1 <= value['created_at'] <= time.time() + 1):
            return False
        path.unlink(missing_ok=True)
        return True
    except (OSError, ValueError, TypeError):
        return False
