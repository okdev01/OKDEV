"""A bounded, restart-aware download queue. Only validated catalog IDs enter it.

Downloads run on one worker, outside the UI action lock. On restart pending work
is shown as interrupted, never silently restarted. The record contains no URLs,
credentials, absolute paths, or raw exception messages.
"""
import copy
import math
import shutil
import threading
import time
import uuid

from . import library

ACTIVE = {'queued', 'downloading', 'installing'}
TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted'}
MAX_JOBS = 100


class DownloadQueue:
    def __init__(self, operation=None, clock=time.time):
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._cancel = threading.Event()
        self._closed = False
        self._persist_close = False
        self._thread = None
        self._current = None
        self._clock = clock
        self._operation = operation or self._download
        self._jobs = []
        self._revision = 0
        self._warning = ''
        self._path = library.root() / 'downloads.json'
        self._load()

    def _load(self):
        if not self._path.exists():
            return
        try:
            if self._path.stat().st_size > 512 * 1024:
                raise ValueError()
            payload = library.load_json(self._path, 512 * 1024)
            if not isinstance(payload, dict) or type(payload.get('schema')) is not int or payload['schema'] != 1:
                raise ValueError()
            jobs = payload.get('jobs')
            if not isinstance(jobs, list) or len(jobs) > MAX_JOBS:
                raise ValueError()
            seen = set()
            for job in jobs:
                if (not isinstance(job, dict) or not library.valid_id(job.get('id'))
                        or job['id'] in seen or not library.valid_id(job.get('mod_id'))
                        or job.get('source') not in ('curated', 'catalog')
                        or job.get('status') not in ACTIVE | TERMINAL
                        or not isinstance(job.get('name'), str) or len(job['name']) > 100
                        or not self._valid_time(job.get('created_at'))
                        or (job.get('finished_at') is not None and not self._valid_time(job['finished_at']))):
                    raise ValueError()
                seen.add(job['id'])
            for job in jobs:
                # Rebuild the public shape instead of retaining arbitrary fields.
                clean = {k: job[k] for k in ('id', 'mod_id', 'source', 'name', 'status', 'created_at')}
                clean.update(received=0, total=0, speed=0, error='', finished_at=job.get('finished_at'))
                if clean['status'] in ACTIVE:
                    clean.update(status='interrupted', error='Uygulama kapandığı için durdu. Yeniden deneyebilirsin.')
                elif clean['status'] == 'failed':
                    clean['error'] = 'Önceki indirme tamamlanamadı. Yeniden deneyebilirsin.'
                self._jobs.append(clean)
        except (OSError, ValueError, TypeError, KeyError):
            self._jobs = []
            self._warning = 'İndirme geçmişi okunamadı. Özgün kayıt korundu; yeni indirmeler için Sistem durumu bölümünü kontrol et.'

    @staticmethod
    def _valid_time(value):
        return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 253402300799

    def _save(self):
        if self._warning:
            raise ValueError(self._warning)
        library.write_json(self._path, {'schema': 1, 'jobs': self._jobs})
        self._revision += 1

    def snapshot(self):
        with self._lock:
            return {'jobs': copy.deepcopy(self._jobs), 'revision': self._revision,
                    'warning': self._warning, 'active': sum(j['status'] in ACTIVE for j in self._jobs)}

    def enqueue(self, mod_id, source='curated'):
        if source not in ('curated', 'catalog') or not library.valid_id(mod_id):
            raise ValueError('Geçersiz indirme seçimi.')
        if source == 'curated':
            from .sources import entries
            candidates = entries()
        else:
            candidates, _ = library.catalog(allow_network=False)
            candidates = candidates['mods']
        item = next((m for m in candidates if m['id'] == mod_id), None)
        if not item or not item.get('download_url' if source == 'curated' else 'url'):
            raise ValueError('Bu içerik doğrudan indirilemiyor. Kaynak sayfasını kullan.')
        with self._lock:
            if self._closed:
                raise ValueError('Uygulama kapanıyor; indirme eklenemedi.')
            duplicate = next((j for j in self._jobs if j['mod_id'] == mod_id and j['status'] in ACTIVE), None)
            if duplicate:
                return copy.deepcopy(duplicate)
            if sum(j['status'] in ACTIVE for j in self._jobs) >= 20:
                raise ValueError('Kuyrukta en fazla 20 indirme olabilir. Birkaçının tamamlanmasını bekle.')
            previous = list(self._jobs)
            while len(self._jobs) >= MAX_JOBS:
                old = next((j for j in self._jobs if j['status'] in TERMINAL), None)
                if old is None:
                    raise ValueError('İndirme kuyruğu dolu.')
                self._jobs.remove(old)
            job = {'id': uuid.uuid4().hex, 'mod_id': mod_id, 'source': source,
                   'name': item['name'], 'status': 'queued', 'created_at': int(self._clock()),
                   'received': 0, 'total': 0, 'speed': 0, 'error': '', 'finished_at': None}
            self._jobs.append(job)
            try:
                self._save()
            except Exception:
                self._jobs = previous
                raise
            self._start()
            return copy.deepcopy(job)

    def _start(self):
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, name='OKDEV-downloads', daemon=True)
            self._thread.start()
        self._wake.set()

    def cancel(self, job_id):
        with self._lock:
            job = self._find(job_id)
            if job['status'] == 'installing':
                raise ValueError('Paket yükleniyor. Dosyaların korunması için bu adım tamamlanmalı.')
            if job['status'] == 'downloading':
                self._cancel.set()
                return {'requested': True}
            if job['status'] == 'queued':
                previous = dict(job)
                job.update(status='cancelled', finished_at=int(self._clock()))
                try:
                    self._save()
                except Exception:
                    job.update(previous)
                    raise
            return {'requested': False}

    def retry(self, job_id):
        with self._lock:
            job = self._find(job_id)
            if job['status'] not in {'failed', 'cancelled', 'interrupted'}:
                raise ValueError('Bu indirme yeniden başlatılamaz.')
            mod_id, source = job['mod_id'], job['source']
        return self.enqueue(mod_id, source)

    def clear_finished(self):
        with self._lock:
            previous = self._jobs
            self._jobs = [j for j in previous if j['status'] in ACTIVE]
            try:
                self._save()
            except Exception:
                self._jobs = previous
                raise
            return len(previous) - len(self._jobs)

    def repair_history(self):
        """Keep the original bytes, then re-save the valid in-memory history."""
        with self._lock:
            if not self._warning:
                return {'repaired': False}
            if any(j['status'] in ACTIVE for j in self._jobs):
                raise ValueError('Onarımdan önce devam eden indirmelerin bitmesini bekle.')
            backup = self._path.with_name('downloads-recovery-' + uuid.uuid4().hex + '.json')
            if self._path.exists():
                shutil.copy2(self._path, backup)
            previous = self._warning
            self._warning = ''
            try:
                self._save()
            except Exception:
                self._warning = previous
                raise
            return {'repaired': True, 'backup': backup.name}

    def _find(self, job_id):
        job = next((j for j in self._jobs if j['id'] == job_id), None)
        if job is None:
            raise ValueError('İndirme bulunamadı.')
        return job

    @staticmethod
    def _download(job, progress, cancelled):
        action = library.download_source if job['source'] == 'curated' else library.download
        return action(job['mod_id'], progress, cancelled)

    def _run(self):
        while True:
            self._wake.wait()
            with self._lock:
                if self._closed:
                    return
                job = next((j for j in self._jobs if j['status'] == 'queued'), None)
                if job is None:
                    self._wake.clear()
                    continue
                self._current = job['id']
                self._cancel.clear()
                job['status'] = 'downloading'
                self._revision += 1
            started = self._clock()

            def progress(value):
                with self._lock:
                    received = max(0, int(value.get('received', 0)))
                    total = max(0, int(value.get('total', 0)))
                    stage = value.get('stage', 'downloading')
                    job.update(status='installing' if stage == 'installing' else 'downloading',
                               received=received, total=total,
                               speed=received / max(.1, self._clock() - started))

            try:
                self._operation(copy.deepcopy(job), progress, self._cancel.is_set)
                status, error = 'completed', ''
            except Exception as exc:
                status = 'cancelled' if self._cancel.is_set() and job['status'] != 'installing' else 'failed'
                from .errors import message
                error = '' if status == 'cancelled' else message(exc,
                    'İndirme tamamlanamadı. Bağlantını kontrol edip yeniden dene.')
            with self._lock:
                if self._closed and not self._persist_close:
                    # The last durable record remains queued and is recovered
                    # as interrupted at next startup. Never recreate storage
                    # after the owning window has finished shutting down.
                    return
                job.update(status=status, error=error, speed=0, finished_at=int(self._clock()))
                self._current = None
                if self._closed:
                    for waiting in self._jobs:
                        if waiting['status'] == 'queued':
                            waiting.update(status='interrupted', finished_at=int(self._clock()),
                                           error='Uygulama kapatıldı. İstersen yeniden sıraya ekleyebilirsin.')
                try:
                    self._save()
                except (OSError, ValueError):
                    self._warning = 'İndirme sonucu diske kaydedilemedi. Modlarım bölümünden sonucu kontrol et.'
                    self._revision += 1
                    # Do not perform unrecorded follow-up work after disk errors.
                    for waiting in self._jobs:
                        if waiting['status'] == 'queued':
                            waiting.update(status='interrupted', error=self._warning)
                    self._wake.clear()
                if self._closed:
                    return

    def close(self, persist_completion=False):
        with self._lock:
            # The desktop's graceful close waits for the worker before it
            # destroys storage/window ownership, so it can retain the result.
            self._persist_close = self._persist_close or persist_completion
            self._closed = True
            self._cancel.set()
            self._wake.set()

    def wait_closed(self, timeout=None):
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)
            return not thread.is_alive()
        return True
