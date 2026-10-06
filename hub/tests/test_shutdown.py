import os
import threading
import time
from unittest.mock import Mock, patch

from hub import downloads, library, lifecycle
from hub.desktop import Api
from hub.tests.test_library import LibraryFixture


class ShutdownTests(LibraryFixture):
    def test_active_install_finishes_before_window_is_destroyed(self):
        entered, release, destroyed = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def operation(job, progress, cancelled):
            progress({'stage': 'installing', 'received': 1, 'total': 1})
            entered.set()
            release.wait(3)
        api = Api()
        api._window = Mock()
        api._window.destroy.side_effect = destroyed.set
        api._queue = downloads.DownloadQueue(operation)
        self.addCleanup(api._queue.close)
        with patch('hub.sources.entries', return_value=[dict(self.item(), download_url='https://example.test/a')]):
            api._queue.enqueue('sample')
        self.assertTrue(entered.wait(1))
        self.assertFalse(api._before_close())
        self.assertTrue(api.close_window()['ok'])
        self.assertFalse(destroyed.wait(.05))
        self.assertFalse(api.save_profile('Cannot save while closing')['ok'])
        release.set()
        self.assertTrue(destroyed.wait(2))
        self.assertTrue(api._before_close())
        reopened = downloads.DownloadQueue()
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.snapshot()['jobs'][0]['status'], 'completed')

    def test_failed_install_during_graceful_close_stays_failed(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def operation(job, progress, cancelled):
            progress({'stage': 'installing', 'received': 1, 'total': 1})
            entered.set()
            release.wait(3)
            raise OSError('disk full')
        queue = downloads.DownloadQueue(operation)
        self.addCleanup(queue.close)
        with patch('hub.sources.entries', return_value=[dict(self.item(), download_url='https://example.test/a')]):
            queue.enqueue('sample')
        self.assertTrue(entered.wait(1))
        queue.close(persist_completion=True)
        release.set()
        self.assertTrue(queue.wait_closed(2))
        reopened = downloads.DownloadQueue()
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.snapshot()['jobs'][0]['status'], 'failed')

    def test_disk_failure_during_graceful_close_never_hangs_worker(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def operation(*args):
            entered.set()
            release.wait(3)
        queue = downloads.DownloadQueue(operation)
        self.addCleanup(queue.close)
        with patch('hub.sources.entries', return_value=[dict(self.item(), download_url='https://example.test/a')]):
            queue.enqueue('sample')
        self.assertTrue(entered.wait(1))
        queue.close(persist_completion=True)
        with patch('hub.library.write_json', side_effect=OSError('disk full')):
            release.set()
            self.assertTrue(queue.wait_closed(2))

    def test_normal_idle_close_needs_no_prompt(self):
        api = Api()
        api._window = Mock()
        self.assertTrue(api._before_close())
        api._window.evaluate_js.assert_not_called()

    def test_busy_foreground_operation_blocks_close_request(self):
        api = Api()
        api._window = Mock()
        with api._busy:
            self.assertFalse(api._before_close())
            self.assertFalse(api.close_window()['ok'])
        self.assertFalse(api._closing)

    def test_no_storage_is_recreated_after_shutdown(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def operation(*args):
            entered.set()
            release.wait(3)
        queue = downloads.DownloadQueue(operation)
        with patch('hub.sources.entries', return_value=[dict(self.item(), download_url='https://example.test/a')]):
            queue.enqueue('sample')
        self.assertTrue(entered.wait(1))
        queue.close()
        with patch('hub.library.write_json') as writer:
            release.set()
            self.assertTrue(queue.wait_closed(2))
            writer.assert_not_called()

    def test_tray_exit_waits_for_foreground_action_without_another_prompt(self):
        api = Api()
        api._window = Mock()
        destroyed = threading.Event()
        api._window.destroy.side_effect = destroyed.set
        with api._busy:
            lifecycle.request_shutdown(os.getpid())
            self.assertFalse(api._before_close())
            self.assertTrue(api._closing)
            self.assertFalse(destroyed.wait(.05))
            api._window.evaluate_js.assert_not_called()
        self.assertTrue(destroyed.wait(2))
        self.assertTrue(api._before_close())

    def test_shutdown_handoff_ignores_stale_and_other_process_records(self):
        now = time.time()
        for record in ({'pid': os.getpid() + 1, 'created_at': now},
                       {'pid': os.getpid(), 'created_at': now - 50},
                       {'pid': os.getpid(), 'created_at': now + 50},
                       {'pid': os.getpid(), 'created_at': float('nan')},
                       {'pid': True, 'created_at': now}):
            library.write_json(library.root() / 'shutdown.json', record)
            self.assertFalse(lifecycle.consume_shutdown(now))
        lifecycle.request_shutdown(os.getpid())
        self.assertTrue(lifecycle.consume_shutdown(now))
        self.assertFalse(lifecycle.consume_shutdown(now))

    def test_parent_shutdown_never_destroys_before_active_install_commits(self):
        entered, release, destroyed = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def operation(job, progress, cancelled):
            progress({'stage': 'installing', 'received': 1, 'total': 1})
            entered.set()
            release.wait(3)
        api = Api()
        api._window = Mock()
        api._window.destroy.side_effect = destroyed.set
        api._queue = downloads.DownloadQueue(operation)
        self.addCleanup(api._queue.close)
        with patch('hub.sources.entries', return_value=[dict(self.item(), download_url='https://example.test/a')]):
            api._queue.enqueue('sample')
        self.assertTrue(entered.wait(1))
        lifecycle.request_shutdown(os.getpid())
        self.assertFalse(api._before_close())
        self.assertFalse(destroyed.wait(.05))
        release.set()
        self.assertTrue(destroyed.wait(2))
        self.assertEqual(api._queue.snapshot()['jobs'][0]['status'], 'completed')
