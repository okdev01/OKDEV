"""Exercise the opt-in guide in isolated storage, with no League connection."""
import ctypes
import json
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from utils.core import paths
    import webview
    report = {'ok': False, 'checks': [], 'errors': []}
    previous = paths._cached_user_data_dir
    previous_migration = paths._migration_checked
    with tempfile.TemporaryDirectory(prefix='okdev-guide-qa-', ignore_cleanup_errors=True) as temporary:
        paths._cached_user_data_dir = Path(temporary)
        paths._migration_checked = True
        from hub import library, preferences, guides, companion
        preferences.update({'mobalytics_enabled': True})
        pick = {'champion': guides.champions()[11], 'role': 'jungle'}

        def wait_for(predicate, timeout=25):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if predicate():
                    return
                time.sleep(.15)
            raise AssertionError('Timed out waiting for companion')

        def exercise():
            try:
                wait_for(lambda: companion.status().get('running'))
                window = webview.windows[0]
                assert not companion.status()['visible']
                report['checks'].append('Starts hidden')
                assert window._js_api is None
                report['checks'].append('Remote page has no Python API')
                user32 = ctypes.WinDLL('user32')
                user32.GetForegroundWindow.restype = ctypes.c_void_p
                before = user32.GetForegroundWindow()
                with patch.object(companion, 'ensure_running', return_value=True):
                    companion.command('show', pick)
                wait_for(lambda: companion.status().get('visible'))
                assert before == user32.GetForegroundWindow()
                report['checks'].append('Automatic show preserves foreground window')
                wait_for(lambda: window.get_current_url() and '/masteryi/build/jungle' in window.get_current_url())
                report['checks'].append('Correct Master Yi jungle URL loaded')
                report['hotkey_registered'] = companion.status()['hotkey_ok']
                assert report['hotkey_registered']
                report['checks'].append('Global hotkey registered')
                preferences.update({'mobalytics_size': 'compact'})
                wait_for(lambda: window.native.Width == 400)
                assert before == user32.GetForegroundWindow()
                report['checks'].append('Compact size applies without taking keyboard focus')
                preferences.update({'mobalytics_size': 'wide'})
                wait_for(lambda: window.native.Width == 600)
                report['checks'].append('Wide size applies to the existing panel')
                preferences.update({'mobalytics_size': 'normal'})
                wait_for(lambda: window.native.Width == 470)
                time.sleep(8)
                report['page_title'] = window.evaluate_js('document.title')
                wait_for(lambda: window.evaluate_js("!!document.getElementById('okdev-guide-navigation')?.shadowRoot.querySelector('.key')"))
                preferences.update({'mobalytics_hotkey': 'Ctrl+Shift+M'})
                wait_for(lambda: window.evaluate_js("document.getElementById('okdev-guide-navigation')?.shadowRoot.querySelector('.key')?.textContent === 'Ctrl+Shift+M'"))
                report['checks'].append('Changing hotkey updates the visible page without reloading')
                report['page_excerpt'] = window.evaluate_js('document.body.innerText.slice(0,1200)')
                report['page_targets'] = window.evaluate_js("Array.from(document.querySelectorAll('h1,h2,h3,h4,[id]')).filter(e=>/^(RUNES|ITEMS|SPELLS|ABILITY ORDER|SKILLS|Builds|Runes|Core Items)$/i.test(e.textContent.trim())).map(e=>({tag:e.tagName,id:e.id,text:e.textContent.trim(),cls:e.className})).slice(0,30)")
                from System import Func, Object
                from System.IO import FileStream, FileMode
                from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat
                stream = FileStream(str(ROOT / 'build/guide-companion-preview.png'), FileMode.Create)
                try:
                    task = window.native.webview.Invoke(Func[Object](lambda: window.native.webview.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, stream)))
                    assert task.Wait(10000)
                finally:
                    stream.Dispose()
                with patch.object(companion, 'ensure_running', return_value=True):
                    companion.command('show', dict(pick, role='aram'))
                wait_for(lambda: window.get_current_url() and '/masteryi/aram-builds' in window.get_current_url())
                wait_for(lambda: 'ARAM' in window.evaluate_js('document.title'))
                report['checks'].append('ARAM selection loads official ARAM page')
                report['aram_title'] = window.evaluate_js('document.title')
                companion.command('hide')
                wait_for(lambda: not companion.status().get('visible'))
                report['checks'].append('Hide command works')
                preferences.update({'mobalytics_enabled': False})
                wait_for(lambda: not companion.status().get('running'))
                report['checks'].append('Disabling exits companion')
                report['ok'] = True
            except Exception as exc:
                report['errors'].append(f'{type(exc).__name__}: {exc}')
            finally:
                preferences.update({'mobalytics_enabled': False})
                library.write_json(ROOT / 'build/guide-companion-check.json', report)
                try:
                    companion.command('quit')
                except Exception:
                    pass

        thread = threading.Thread(target=exercise, daemon=True)
        thread.start()
        try:
            # The user's installed companion may already own the production
            # mutex and shortcuts. Keep this disposable QA instance independent.
            with patch.object(companion, '_MUTEX_NAME', 'Local\\OKDEV-GuideQA-' + uuid.uuid4().hex), patch.dict(companion.HOTKEYS, {
                    'Ctrl+Shift+B': (0x0002 | 0x0004, 0x7C),  # Ctrl+Shift+F13
                    'Ctrl+Shift+M': (0x0002 | 0x0004, 0x7D)}):
                companion.run()
                thread.join(35)
        finally:
            paths._cached_user_data_dir = previous
            paths._migration_checked = previous_migration
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
