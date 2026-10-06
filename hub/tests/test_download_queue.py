import json
import threading
import time
from unittest.mock import patch

from hub import downloads, library
from hub.tests.test_library import LibraryFixture


class DownloadQueueTests(LibraryFixture):
    def queue(self, operation=None):
        queue = downloads.DownloadQueue(operation)
        self.addCleanup(queue.close)
        return queue

    def source(self, mod_id='source'):
        return dict(self.item(mod_id), download_url='https://example.test/mod', sha256='a' * 64)

    def wait(self, queue, status, job_id=None):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            jobs = queue.snapshot()['jobs']
            if any(j['status'] == status and (job_id is None or j['id'] == job_id) for j in jobs):
                return
            time.sleep(.005)
        self.fail(f'Queue never reached {status}: {queue.snapshot()}')

    def test_serial_queue_deduplicates_and_allows_preferences_during_network_io(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        calls = []

        def operation(job, progress, cancelled):
            calls.append(job['mod_id'])
            entered.set()
            release.wait(3)
            progress({'stage': 'installing', 'received': 128, 'total': 128})

        queue = self.queue(operation)
        with patch('hub.sources.entries', return_value=[self.source(), self.source('second')]):
            first = queue.enqueue('source')
            self.assertTrue(entered.wait(1))
            self.assertEqual(queue.enqueue('source')['id'], first['id'])
            second = queue.enqueue('second')
            library.set_auto_accept(True)
            self.assertTrue(library.settings()['auto_accept'])
            self.assertEqual(calls, ['source'])
            release.set()
            self.wait(queue, 'completed', second['id'])
        self.assertEqual(calls, ['source', 'second'])
        self.assertEqual(queue.snapshot()['active'], 0)
        persisted = json.loads((library.root() / 'downloads.json').read_text())
        self.assertTrue(all(j['status'] == 'completed' for j in persisted['jobs']))

    def test_queued_cancellation_never_runs_and_active_cancellation_is_cooperative(self):
        entered = threading.Event()

        def operation(job, progress, cancelled):
            entered.set()
            deadline = time.monotonic() + 3
            while not cancelled() and time.monotonic() < deadline:
                time.sleep(.005)
            raise ValueError('İndirme iptal edildi.')

        queue = self.queue(operation)
        with patch('hub.sources.entries', return_value=[self.source(), self.source('second')]):
            first = queue.enqueue('source')
            self.assertTrue(entered.wait(1))
            second = queue.enqueue('second')
            queue.cancel(second['id'])
            queue.cancel(first['id'])
            self.wait(queue, 'cancelled', first['id'])
        self.assertTrue(all(j['status'] == 'cancelled' for j in queue.snapshot()['jobs']))

    def test_failure_is_sanitized_and_next_job_proceeds(self):
        def operation(job, progress, cancelled):
            if job['mod_id'] == 'source':
                raise OSError('private/path?token=secret')
        queue = self.queue(operation)
        with patch('hub.sources.entries', return_value=[self.source(), self.source('second')]):
            queue.enqueue('source')
            second = queue.enqueue('second')
            self.wait(queue, 'completed', second['id'])
        failed = queue.snapshot()['jobs'][0]
        self.assertEqual(failed['status'], 'failed')
        self.assertNotIn('secret', failed['error'])
        self.assertNotIn('private', (library.root() / 'downloads.json').read_text())

    def test_restart_recovers_pending_jobs_without_starting_network(self):
        job = dict(id='job', mod_id='source', source='curated', name='Mod', status='downloading', created_at=1)
        library.write_json(library.root() / 'downloads.json', {'schema': 1, 'jobs': [job]})
        calls = []
        queue = self.queue(lambda *args: calls.append(args))
        self.assertEqual(queue.snapshot()['jobs'][0]['status'], 'interrupted')
        self.assertIsNone(queue._thread)
        with patch('hub.sources.entries', return_value=[self.source()]):
            retried = queue.retry('job')
            self.wait(queue, 'completed', retried['id'])
        self.assertEqual(len(calls), 1)
        self.assertNotEqual(retried['id'], 'job')

    def test_corrupt_record_is_preserved_and_blocks_overwrite(self):
        path = library.root() / 'downloads.json'
        path.write_text('{broken', encoding='utf-8')
        queue = self.queue()
        with patch('hub.sources.entries', return_value=[self.source()]):
            with self.assertRaisesRegex(ValueError, 'Özgün kayıt'):
                queue.enqueue('source')
        self.assertEqual(queue.snapshot()['jobs'], [])
        self.assertEqual(path.read_text(), '{broken')

    def test_installing_cannot_be_cancelled(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def operation(job, progress, cancelled):
            progress({'stage': 'installing', 'received': 10, 'total': 10})
            entered.set()
            release.wait(3)

        queue = self.queue(operation)
        with patch('hub.sources.entries', return_value=[self.source()]):
            job = queue.enqueue('source')
            self.assertTrue(entered.wait(1))
            with self.assertRaisesRegex(ValueError, 'Paket yükleniyor'):
                queue.cancel(job['id'])
            self.assertEqual(queue.clear_finished(), 0)
            release.set()
            self.wait(queue, 'completed')
            self.assertEqual(queue.clear_finished(), 1)

    def test_arbitrary_ids_and_source_values_are_rejected(self):
        queue = self.queue()
        for mod_id, source in [('../file', 'curated'), ('source', 'https://evil.test'), (None, 'catalog')]:
            with self.assertRaises(ValueError):
                queue.enqueue(mod_id, source)
        with patch('hub.sources.entries', return_value=[]):
            with self.assertRaises(ValueError):
                queue.enqueue('unknown')
        self.assertIsNone(queue._thread)

    def test_disk_failure_prevents_unrecorded_download(self):
        queue = self.queue()
        with patch('hub.sources.entries', return_value=[self.source()]), patch('hub.library.write_json', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                queue.enqueue('source')
        self.assertEqual(queue.snapshot()['jobs'], [])
        self.assertIsNone(queue._thread)

    def test_repair_preserves_original_bytes_and_allows_new_download(self):
        path = library.root() / 'downloads.json'
        original = b'{broken\xffhistory'
        path.write_bytes(original)
        queue = self.queue(lambda *args: None)
        self.assertTrue(queue.snapshot()['warning'])
        result = queue.repair_history()
        self.assertEqual((path.parent / result['backup']).read_bytes(), original)
        self.assertFalse(queue.snapshot()['warning'])
        with patch('hub.sources.entries', return_value=[self.source()]):
            job = queue.enqueue('source')
            self.wait(queue, 'completed', job['id'])
        self.assertEqual(queue.repair_history(), {'repaired': False})

    def test_failed_repair_keeps_warning_and_original_backup(self):
        path = library.root() / 'downloads.json'
        path.write_text('{broken', encoding='utf-8')
        queue = self.queue()
        with patch('hub.library.write_json', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                queue.repair_history()
        self.assertTrue(queue.snapshot()['warning'])
        self.assertEqual(path.read_text(), '{broken')
        self.assertEqual(next(path.parent.glob('downloads-recovery-*.json')).read_text(), '{broken')

    def test_invalid_timestamps_are_preserved_without_entering_public_state(self):
        path = library.root() / 'downloads.json'
        base = dict(id='job', mod_id='source', source='curated', name='Mod', status='completed', created_at=1)
        for field, value in [('created_at', float('nan')), ('created_at', True),
                             ('finished_at', float('inf')), ('finished_at', {'private': 'value'})]:
            with self.subTest(field=field, value=value):
                document = {'schema': 1, 'jobs': [{**base, field: value}]}
                path.write_text(json.dumps(document), encoding='utf-8')
                original = path.read_bytes()
                queue = self.queue()
                self.assertTrue(queue.snapshot()['warning'])
                self.assertEqual(queue.snapshot()['jobs'], [])
                self.assertEqual(path.read_bytes(), original)

    def test_history_read_is_bounded_before_json_parsing(self):
        path = library.root() / 'downloads.json'
        path.write_bytes(b' ' * (512 * 1024 + 1))
        with patch('hub.library.json.loads') as parse:
            queue = self.queue()
        parse.assert_not_called()
        self.assertTrue(queue.snapshot()['warning'])
