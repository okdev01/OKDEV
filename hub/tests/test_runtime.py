import ctypes
import json
from unittest.mock import Mock, patch

from hub import diagnostics, runtime
from hub.desktop import run
from hub.tests.test_library import LibraryFixture


class RuntimeTests(LibraryFixture):
    def test_version_allocation_is_freed_even_when_native_lookup_fails(self):
        buffer = ctypes.create_unicode_buffer('154.0.1.2')
        def lookup(_path, target):
            ctypes.cast(target, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.addressof(buffer)
            return result
        for result in (0, -1):
            free = Mock()
            with patch.object(runtime.sys, 'platform', 'win32'), patch.object(runtime, '_native_functions', return_value=(lookup, free)):
                self.assertEqual(runtime.available_version(), '154.0.1.2' if result == 0 else None)
            free.assert_called_once()
            self.assertEqual(free.call_args.args[0].value, ctypes.addressof(buffer))

    def test_missing_native_runtime_returns_none_without_freeing_null(self):
        free = Mock()
        with patch.object(runtime.sys, 'platform', 'win32'), patch.object(runtime, '_native_functions', return_value=(Mock(return_value=-1), free)):
            self.assertIsNone(runtime.available_version())
        free.assert_not_called()

    def test_missing_loader_does_not_leak_an_exception_to_ui(self):
        with patch.object(runtime, '_native_functions', side_effect=OSError('missing loader')):
            self.assertIsNone(runtime.available_version())

    def test_download_page_opens_only_when_user_selects_yes(self):
        for answer in (0, 7, 6):
            with patch.object(runtime, '_message', return_value=answer), patch.object(runtime.webbrowser, 'open') as browser:
                runtime.show_missing_runtime()
                if answer == 6:
                    browser.assert_called_once_with(runtime.RUNTIME_URL)
                else:
                    browser.assert_not_called()

    def test_missing_runtime_never_opens_legacy_browser_window(self):
        with patch.object(runtime, 'available_version', return_value=None), patch.object(runtime, 'show_missing_runtime') as help_dialog, patch('hub.desktop._run_window') as window:
            run()
            window.assert_not_called()
            help_dialog.assert_called_once()

    def test_headless_smoke_reports_missing_runtime_without_dialog(self):
        report = self.root / 'smoke.json'
        with patch.object(runtime, 'available_version', return_value=None), patch.object(runtime, 'show_missing_runtime') as help_dialog:
            run(report)
        self.assertFalse(json.loads(report.read_text(encoding='utf-8'))['ok'])
        help_dialog.assert_not_called()

    def test_startup_failure_gets_a_visible_recovery_message(self):
        with patch.object(runtime, 'available_version', return_value='154.0.1.2'), patch('hub.desktop._run_window', side_effect=RuntimeError('private detail')), patch.object(runtime, 'show_startup_error') as message:
            run()
            message.assert_called_once()

    def test_diagnostics_reports_runtime_version_or_missing_prerequisite(self):
        for version in ('154.0.1.2', None):
            with patch.object(runtime, 'available_version', return_value=version):
                item = next(c for c in diagnostics.collect()['checks'] if c['name'] == 'WebView2 Runtime')
            self.assertEqual(item['status'], 'ok' if version else 'warning')
            self.assertIn(version or 'WebView2 bulunamadı', item['detail'])
