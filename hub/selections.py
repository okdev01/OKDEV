"""Previewable mod selection changes with one-step, conflict-aware undo."""
import hashlib
import json
import time

from . import library


def _ids(values):
    if not isinstance(values, list) or len(values) > 2000 or not all(library.valid_id(v) for v in values):
        raise ValueError('Geçersiz mod seçimi.')
    return set(values)


def revision(data):
    fields = ('id', 'enabled', 'relative_path', 'version', 'sha256', 'category', 'champion_id')
    value = {key: {field: item.get(field) for field in fields} for key, item in data.items()}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def _group(item):
    category = item.get('category', 'skins')
    return category, item.get('champion_id') if category == 'skins' else None


def _plan(data, mod_ids, mode):
    requested = _ids(mod_ids)
    if mode not in ('enable', 'disable', 'replace'):
        raise ValueError('Geçersiz seçim işlemi.')
    if requested - data.keys():
        raise ValueError('Seçilen modlardan bazıları artık kütüphanede değil. Listeyi yenile.')
    before = {key for key, item in data.items() if item['enabled']}
    if mode == 'disable':
        selected = before - requested
    else:
        groups = {}
        for mod_id in sorted(requested):
            item = data[mod_id]
            if not library.mod_folder(item).is_dir():
                raise ValueError(item['name'] + ' dosyaları bulunamadı. Önce geri yükle veya yeniden ekle.')
            group = _group(item)
            if group in groups:
                raise ValueError('Aynı şampiyon veya kategori için tek mod seç: ' + groups[group] + ' / ' + item['name'])
            groups[group] = item['name']
        selected = requested if mode == 'replace' else requested | {key for key in before if _group(data[key]) not in groups}
    describe = lambda ids: [{'id': key, 'name': data[key]['name'], 'category': data[key].get('category', 'skins')} for key in sorted(ids)]
    return {'revision': revision(data), 'mode': mode, 'requested': sorted(requested),
            'before': sorted(before), 'after': sorted(selected), 'enable': describe(selected - before),
            'disable': describe(before - selected), 'changed': selected != before}


def preview(mod_ids, mode='enable'):
    with library.mutation_lock():
        return _plan(library.installed(strict=True), mod_ids, mode)


def apply(mod_ids, mode='enable', expected_revision=None, remember=True):
    with library.mutation_lock():
        data = library.installed(strict=True)
        plan = _plan(data, mod_ids, mode)
        if expected_revision is not None and expected_revision != plan['revision']:
            raise ValueError('Mod listesi değişti. Güncel değişiklikleri tekrar kontrol et.')
        if not plan['changed']:
            return plan
        after = set(plan['after'])
        # Persist the undo intent first. If the index write fails, the stored
        # expected state will not match and undo will safely refuse to run.
        journal = {'schema': 1, 'before': plan['before'] if remember else plan['after'], 'after': plan['after'],
                   'created_at': int(time.time()), 'revision': plan['revision']}
        library.write_json(library.root() / 'selection-undo.json', journal)
        for item in data.values():
            if item['enabled'] and item['id'] not in after:
                library._clear_history(item)
            item['enabled'] = item['id'] in after
        library.write_json(library.root() / 'installed.json', data)
        from .activity import record
        record('selection' if remember else 'undo', count=len(plan['enable']) + len(plan['disable']))
        return plan


def undo_status(data=None):
    data = library.installed() if data is None else data
    record = library.read_json(library.root() / 'selection-undo.json', {})
    try:
        if record.get('schema') != 1:
            return {'available': False}
        before, after = _ids(record.get('before')), _ids(record.get('after'))
        current = {key for key, item in data.items() if item['enabled']}
        available = current == after and before != after and before <= data.keys()
        return {'available': available, 'restore_count': len(before)}
    except (ValueError, TypeError):
        return {'available': False}


def undo():
    with library.mutation_lock():
        record = library.read_json(library.root() / 'selection-undo.json', {})
        if not undo_status()['available']:
            raise ValueError('Seçimler değiştiği için bu işlem geri alınamıyor.')
        # Applying the old set also validates missing files and category conflicts.
        return apply(record['before'], 'replace', remember=False)
