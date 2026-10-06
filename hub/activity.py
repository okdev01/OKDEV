"""Bounded local activity, separate from diagnostic logs and never transmitted."""
import time
import uuid

from . import library

KINDS = {'import', 'update', 'remove', 'restore', 'selection', 'undo', 'profile_save', 'profile_import', 'recovery'}
LIMIT = 200


def read():
    path = library.root() / 'activity.json'
    if not path.exists():
        return {'events': [], 'warning': ''}
    try:
        if path.stat().st_size > 256 * 1024:
            raise ValueError()
        events = library.load_json(path, 256 * 1024)
        if not isinstance(events, list) or len(events) > LIMIT:
            raise ValueError()
        for event in events:
            if (not isinstance(event, dict) or event.get('kind') not in KINDS
                    or not library.valid_id(event.get('id')) or type(event.get('at')) is not int
                    or not 0 <= event['at'] <= 253402300799
                    or not isinstance(event.get('name'), str) or len(event['name']) > 100
                    or type(event.get('count')) is not int or not 0 <= event['count'] <= 2000):
                raise ValueError()
        return {'events': [{key: event[key] for key in ('id', 'kind', 'name', 'count', 'at')}
                           for event in events], 'warning': ''}
    except (OSError, ValueError, TypeError):
        return {'events': [], 'warning': 'İşlem geçmişi okunamadı. Mevcut kayıt dosyası korunuyor.'}


def record(kind, name='', count=1):
    if kind not in KINDS or not isinstance(name, str) or type(count) is not int or not 0 <= count <= 2000:
        return
    # The operation has already committed. An optional history write must not
    # turn a successful install into an apparent failure and duplicate retry.
    try:
        with library.mutation_lock():
            state = read()
            if state['warning']:
                return
            event = {'id': uuid.uuid4().hex, 'kind': kind, 'name': name[:100],
                     'count': count, 'at': int(time.time())}
            library.write_json(library.root() / 'activity.json', [event, *state['events']][:LIMIT])
    except (OSError, ValueError):
        pass
