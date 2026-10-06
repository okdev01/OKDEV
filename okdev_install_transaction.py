"""Crash recovery for a prepared installation replacing an existing one.

Only sibling folders belonging to the named transaction can be moved. Recovery
never deletes payloads or overwrites a folder. The small journal is durable before
the original installation is renamed, closing the two-rename power-loss gap.
"""
import hashlib
import json
import re
import threading
from contextlib import contextmanager
from pathlib import Path

from hub.locking import settings_lock
from utils.core.atomic_file import atomic_write

_thread_lock = threading.RLock()
_local = threading.local()


def _target(value):
    value = Path(value).expanduser().absolute()
    if not value.name or value == Path(value.anchor):
        raise ValueError('Kurulum için ayrı bir klasör seçin.')
    if value.is_symlink() or getattr(value, 'is_junction', lambda: False)():
        raise ValueError('Bağlantılı kurulum klasörü değiştirilemez.')
    return value.parent.resolve() / value.name


def journal_path(target):
    target = _target(target)
    identity = hashlib.sha256(str(target).casefold().encode('utf-8')).hexdigest()[:24]
    return target.parent / ('.okdev-transaction-' + identity + '.json')


@contextmanager
def installation_lock(target):
    path = journal_path(target)
    with _thread_lock:
        active = getattr(_local, 'active', set())
        if path in active:
            yield
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with settings_lock(path):
            _local.active = active | {path}
            try:
                yield
            finally:
                _local.active = active


def _read_bounded(path, limit):
    with path.open('rb') as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError('Kurulum kayıt dosyası çok büyük; özgün dosyalar korundu.')
    return content


def _fingerprint(folder):
    if not folder.is_dir() or folder.is_symlink() or getattr(folder, 'is_junction', lambda: False)():
        raise ValueError('İşleme ait kurulum klasörü bulunamadı veya bağlantılı.')
    metadata, executable = folder / 'okdev-install.json', folder / 'OKDEV.exe'
    if metadata.is_symlink() or executable.is_symlink() or metadata.stat().st_size > 128 * 1024:
        raise ValueError('Kurulum kimliği doğrulanamadı.')
    content = _read_bounded(metadata, 128 * 1024)
    try:
        data = json.loads(content.decode('utf-8'))
    except RecursionError:
        raise ValueError('Kurulum kimliği doğrulanamadı.') from None
    if not isinstance(data, dict) or not isinstance(data.get('install_id'), str) or not data['install_id']:
        raise ValueError('Kurulum kimliği doğrulanamadı.')
    with executable.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'metadata': hashlib.sha256(content).hexdigest(), 'executable': digest}


def _paths(target, record):
    if (not isinstance(record, dict) or type(record.get('schema')) is not int or record['schema'] != 1
            or not isinstance(record.get('target'), str) or Path(record['target']) != Path(target.name)):
        raise ValueError('Kurulum işlem kaydı geçersiz; klasörlere dokunulmadı.')
    prepared, backup = record.get('prepared'), record.get('backup')
    if (not isinstance(prepared, str) or not re.fullmatch(r'\.okdev-(?:update|install)-[a-zA-Z0-9_-]{6,40}', prepared)
            or not isinstance(backup, str) or not re.fullmatch(re.escape(record['target']) + r'\.backup-[a-f0-9]{12}', backup)):
        raise ValueError('Kurulum işlem yolları geçersiz.')
    for key in ('before', 'after'):
        value = record.get(key)
        if not isinstance(value, dict) or set(value) != {'metadata', 'executable'} or not all(
                isinstance(v, str) and re.fullmatch('[a-f0-9]{64}', v) for v in value.values()):
            raise ValueError('Kurulum işlem kimliği geçersiz.')
    paths = [target.parent / prepared, target.parent / backup]
    for path in paths:
        if path.resolve().parent != target.parent or path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise ValueError('Kurulum işlemi başka bir klasöre yönlendirilemez.')
    return paths


def _finish(path):
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass  # Committed/rolled-back records can safely be revisited.


def recover(target):
    """Recover a previous interrupted swap. Caller owns installation_lock."""
    target = _target(target)
    journal = journal_path(target)
    if not journal.exists():
        return {'recovered': False}
    if journal.is_symlink() or journal.stat().st_size > 64 * 1024:
        raise ValueError('Kurulum işlem kaydı okunamadı; özgün dosyalar korundu.')
    try:
        record = json.loads(_read_bounded(journal, 64 * 1024).decode('utf-8'))
        prepared, backup = _paths(target, record)
        if target.exists():
            identity = _fingerprint(target)
            if backup.exists():
                if identity != record['after'] or prepared.exists() or _fingerprint(backup) != record['before']:
                    raise ValueError('Kurulum klasörleri işlemden sonra değişmiş; otomatik kurtarma durduruldu.')
                status = 'completed'
            elif identity == record['before']:
                status = 'not_started'
            else:
                raise ValueError('Kurulum kimliği değişmiş; özgün klasörler korundu.')
        elif backup.exists() and _fingerprint(backup) == record['before']:
            backup.rename(target)
            status = 'rolled_back'
        else:
            raise ValueError('Önceki kurulum yedeği bulunamadı; işlem kaydı korundu.')
        _finish(journal)
        return {'recovered': True, 'status': status, 'retained_prepared': prepared.name if prepared.exists() else None}
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError):
            raise
        raise ValueError('Yarım kurulum kurtarılamadı. Kurulum ve yanındaki yedek klasörlerini koruyup yeniden deneyin.') from None


def commit(target, prepared, backup):
    """Durably journal and swap; ordinary errors restore the previous folder."""
    target, prepared, backup = _target(target), Path(prepared).absolute(), Path(backup).absolute()
    with installation_lock(target):
        recover(target)
        if prepared.parent.resolve() != target.parent or backup.parent.resolve() != target.parent or backup.exists():
            raise ValueError('Güvenli kurulum yedek konumu oluşturulamadı.')
        record = {'schema': 1, 'target': target.name, 'prepared': prepared.name, 'backup': backup.name,
                  'before': _fingerprint(target), 'after': _fingerprint(prepared)}
        _paths(target, record)
        journal = journal_path(target)
        with atomic_write(journal) as stream:
            json.dump(record, stream, ensure_ascii=False)
        try:
            target.rename(backup)
            prepared.rename(target)
        except Exception:
            if backup.exists() and not target.exists():
                backup.rename(target)
            if target.exists() and not backup.exists() and _fingerprint(target) == record['before']:
                _finish(journal)
            raise
        _finish(journal)
        return backup
