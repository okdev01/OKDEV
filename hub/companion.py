"""Window commands and lifecycle for the opt-in Mobalytics companion.

Remote Mobalytics pages never receive a Python API bridge. Automatic visibility
uses SW_SHOWNOACTIVATE, so champion selection does not steal keyboard focus.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
from collections import deque

from . import guides, library, preferences

_process = None
_last_start = 0
_start_lock = threading.Lock()
HOTKEYS = {'Ctrl+Shift+B': (0x0002 | 0x0004, 0x42), 'Ctrl+Shift+M': (0x0002 | 0x0004, 0x4D), 'Alt+B': (0x0001, 0x42)}


def window_rectangle(area, position, size='normal'):
    left, top, right, bottom = area
    wanted_width, wanted_height = {'compact': (400, 560), 'normal': (470, 720), 'wide': (600, 800)}.get(size, (470, 720))
    width, height = min(wanted_width, right - left - 32), min(wanted_height, bottom - top - 32)
    x = right - width - 16 if position == 'right' else left + 16
    return x, top + max(16, (bottom - top - height) // 2), width, height


def status():
    value = library.read_json(library.root() / 'companion-status.json', {})
    timestamp = value.get('updated_at')
    if type(timestamp) not in (int, float) or not 0 <= time.time() - timestamp < 15:
        return {'running': False, 'visible': False, 'hotkey_ok': False, 'error': ''}
    return {key: value.get(key) for key in ('running', 'visible', 'hotkey_ok', 'hotkey', 'error')}


def ensure_running():
    global _process, _last_start
    if not preferences.get()['mobalytics_enabled']:
        return False
    with _start_lock:
        if _process is not None and _process.poll() is None or status()['running']:
            return True
        if time.monotonic() - _last_start < 30:
            return False
        command = ([sys.executable, '--guide-companion'] if getattr(sys, 'frozen', False)
                   else [sys.executable, str(Path(__file__).resolve().parents[1] / 'main.py'), '--guide-companion'])
        _last_start = time.monotonic()
        _process = subprocess.Popen(command, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True


def command(action, pick=None):
    if action not in ('show', 'prepare', 'hide', 'toggle', 'quit'):
        raise ValueError('Geçersiz rehber işlemi.')
    if action in ('show', 'prepare', 'toggle'):
        if not preferences.get()['mobalytics_enabled']:
            raise ValueError('Önce oyun rehberini etkinleştir.')
        if pick is None:
            pick = guides.read_state().get('pick')
        if pick is None:
            raise ValueError('Bir şampiyon seç veya şampiyonunu kilitle.')
        # Reconstruct URL from a bundled champion ID; never accept arbitrary URLs.
        champion_id = pick.get('champion', {}).get('id')
        pick = {'champion': guides.champions().get(champion_id), 'role': pick.get('role', ''),
                'url': guides.build_url(champion_id, pick.get('role', ''))}
    library.write_json(library.root() / 'companion-command.json', {
        'id': uuid.uuid4().hex, 'action': action, 'pick': pick, 'created_at': time.time()})
    if action in ('show', 'prepare', 'toggle'):
        ensure_running()


class WindowState:
    """Testable navigation/visibility decisions, independent of Windows APIs."""
    def __init__(self):
        self.visible = False
        self.url = None
        self.title = 'OKDEV · Oyun rehberi'
        self.command_ids = deque(maxlen=128)

    def apply(self, value, now=None):
        if not isinstance(value, dict) or not isinstance(value.get('id'), str) or not value['id'] or value['id'] in self.command_ids:
            return []
        self.command_ids.append(value['id'])
        timestamp = value.get('created_at')
        now = time.time() if now is None else now
        if type(timestamp) not in (int, float) or not 0 <= now - timestamp < 30:
            return []
        action = value.get('action')
        if action == 'quit':
            return [('quit', None)]
        if action == 'hide':
            self.visible = False
            return [('hide', None)]
        if action not in ('prepare', 'show', 'toggle'):
            return []
        pick = value.get('pick')
        try:
            champion_id = pick['champion']['id']
            url = guides.build_url(champion_id, pick.get('role', ''))
        except (KeyError, TypeError, ValueError):
            return []
        events = []
        if url != self.url:
            self.url = url
            self.title = guides.champions()[champion_id]['name'] + ' · Mobalytics — Ctrl+Shift+B ile gizle'
            events.append(('navigate', url))
        if action == 'show':
            self.visible = True
            events.append(('show', None))
        elif action == 'toggle':
            self.visible = not self.visible
            events.append(('show' if self.visible else 'hide', None))
        return events


class WindowsHotkey:
    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.wintypes = ctypes, wintypes
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        self.user32.RegisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
        self.user32.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
        self.user32.PeekMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT)
        self.key = None
        self.registered = False

    def set(self, key):
        if key == self.key:
            return self.registered
        self.close()
        self.key = key
        if key in HOTKEYS:
            modifiers, vk = HOTKEYS[key]
            self.registered = bool(self.user32.RegisterHotKey(None, 0x4F4B, modifiers | 0x4000, vk))
        return self.registered

    def pressed(self):
        message = self.wintypes.MSG()
        return bool(self.user32.PeekMessageW(self.ctypes.byref(message), None, 0x0312, 0x0312, 1))

    def close(self):
        if self.registered:
            self.user32.UnregisterHotKey(None, 0x4F4B)
        self.registered = False


def run():
    import ctypes
    from ctypes import wintypes
    import webview
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    mutex = kernel.CreateMutexW(None, False, r'Local\OKDEV-GuideCompanion')
    if not mutex:
        return
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle(mutex)
        return
    if not preferences.get()['mobalytics_enabled']:
        kernel.CloseHandle(mutex)
        return
    machine = WindowState()
    stopping = threading.Event()
    window = webview.create_window('OKDEV · Oyun rehberi', html='<html><body style="background:#11131c;color:#ddd;font:16px Segoe UI;padding:32px">Rehber hazırlanıyor…</body></html>',
        width=470, height=720, min_size=(380, 500), hidden=True, focus=False, on_top=True,
        background_color='#11131c', text_select=True)

    def closing():
        if stopping.is_set():
            return True
        machine.visible = False
        window.hide()
        return False

    window.events.closing += closing

    def install_navigation():
        try:
            base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
            source = (base / 'hub/web/guide.js').read_text(encoding='utf-8')
            key = json.dumps(preferences.get()['mobalytics_hotkey'])
            window.evaluate_js('window.OKDEV_GUIDE_HOTKEY=' + key + ';' + source)
        except Exception:
            # Site navigation still works if its document is being replaced.
            pass

    window.events.loaded += install_navigation

    def worker():
        hotkey = WindowsHotkey()
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.MonitorFromWindow.argtypes = (wintypes.HWND, wintypes.DWORD)
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        class MonitorInfo(ctypes.Structure):
            _fields_ = [('size', wintypes.DWORD), ('monitor', wintypes.RECT), ('work', wintypes.RECT), ('flags', wintypes.DWORD)]
        user32.GetMonitorInfoW.argtypes = (wintypes.HANDLE, ctypes.POINTER(MonitorInfo))

        def position_window(hwnd, position, size):
            monitor = user32.MonitorFromWindow(user32.GetForegroundWindow(), 2)
            info = MonitorInfo(size=ctypes.sizeof(MonitorInfo))
            if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                r = info.work
                area = (r.left, r.top, r.right, r.bottom)
            else:
                area = (0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
            x, y, width, height = window_rectangle(area, position, size)
            user32.SetWindowPos(hwnd, -1, x, y, width, height, 0x0010)
        last_status = 0
        last_position = None
        last_hotkey = None
        failure = ''
        try:
            if not window.events.loaded.wait(25):
                raise RuntimeError('Rehber penceresi başlatılamadı.')
            hwnd = int(window.native.Handle.ToInt64())
            while not stopping.wait(.2):
                prefs = preferences.get()
                if not prefs['mobalytics_enabled']:
                    break
                hotkey_ok = hotkey.set(prefs['mobalytics_hotkey'])
                if prefs['mobalytics_hotkey'] != last_hotkey:
                    window.set_title(machine.title.replace('Ctrl+Shift+B', prefs['mobalytics_hotkey']))
                    install_navigation()
                    last_hotkey = prefs['mobalytics_hotkey']
                layout = (prefs['mobalytics_position'], prefs['mobalytics_size'])
                if layout != last_position:
                    position_window(hwnd, *layout)
                    last_position = layout
                value = library.read_json(library.root() / 'companion-command.json', {})
                if hotkey.pressed():
                    current = guides.read_state()
                    if machine.visible:
                        value = {'id': uuid.uuid4().hex, 'action': 'hide', 'created_at': time.time()}
                    elif current.get('pick'):
                        value = {'id': uuid.uuid4().hex, 'action': 'show', 'pick': current['pick'], 'created_at': time.time()}
                for event, payload in machine.apply(value):
                    if event == 'navigate':
                        window.load_url(payload)
                        window.set_title(machine.title.replace('Ctrl+Shift+B', prefs['mobalytics_hotkey']))
                    elif event == 'show':
                        position_window(hwnd, *layout)
                        user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
                    elif event == 'hide':
                        user32.ShowWindow(hwnd, 0)
                    elif event == 'quit':
                        stopping.set()
                if time.time() - last_status >= 2:
                    library.write_json(library.root() / 'companion-status.json', {
                        'running': True, 'visible': machine.visible, 'hotkey_ok': hotkey_ok,
                        'hotkey': prefs['mobalytics_hotkey'], 'updated_at': time.time(),
                        'error': '' if hotkey_ok else 'Kısayol başka bir uygulama tarafından kullanılıyor. Ayarlardan değiştir.'})
                    last_status = time.time()
        except Exception:
            failure = 'Rehber başlatılamadı. WebView2 kurulumunu kontrol et veya rehberi tarayıcıda aç.'
        finally:
            hotkey.close()
            stopping.set()
            library.write_json(library.root() / 'companion-status.json', {
                'running': False, 'visible': False, 'hotkey_ok': False, 'updated_at': time.time(), 'error': failure})
            window.destroy()
    try:
        webview.start(worker, gui='edgechromium', storage_path=str(library.root() / 'guide-webview'), private_mode=False)
    finally:
        stopping.set()
        kernel.CloseHandle(mutex)
