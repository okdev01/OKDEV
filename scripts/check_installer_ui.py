"""Exercise installer presentation with fake install/validate callbacks only."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'setup_app'))
from installer_ui import InstallerWindow


def capture_window(window, path):
    """Print only this QA window into a bitmap; never capture the desktop."""
    from PIL import Image
    user32, gdi = ctypes.windll.user32, ctypes.windll.gdi32
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    gdi.SelectObject.restype = wintypes.HANDLE
    gdi.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi.DeleteDC.argtypes = [wintypes.HDC]
    class Header(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('width', wintypes.LONG), ('height', wintypes.LONG),
                    ('planes', wintypes.WORD), ('bits', wintypes.WORD), ('compression', wintypes.DWORD),
                    ('image_size', wintypes.DWORD), ('xppm', wintypes.LONG), ('yppm', wintypes.LONG),
                    ('used', wintypes.DWORD), ('important', wintypes.DWORD)]
    gdi.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(Header), wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    gdi.CreateDIBSection.restype = wintypes.HBITMAP
    window.update_idletasks(); window.update()
    hwnd = user32.GetAncestor(window.winfo_id(), 2)
    rect = wintypes.RECT()
    assert user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    screen = user32.GetDC(hwnd)
    dc = gdi.CreateCompatibleDC(screen)
    data = ctypes.c_void_p()
    header = Header(ctypes.sizeof(Header), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
    bitmap = gdi.CreateDIBSection(screen, ctypes.byref(header), 0, ctypes.byref(data), None, 0)
    assert bitmap and data.value
    old = gdi.SelectObject(dc, bitmap)
    try:
        assert user32.PrintWindow(hwnd, dc, 2), 'Native installer capture failed'
        pixels = ctypes.string_at(data, width * height * 4)
        image = Image.frombytes('RGB', (width, height), pixels, 'raw', 'BGRX')
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
    finally:
        gdi.SelectObject(dc, old); gdi.DeleteObject(bitmap); gdi.DeleteDC(dc); user32.ReleaseDC(hwnd, screen)


def main():
    out = ROOT / 'output/ui2-20261030'
    report = {'ok': False, 'checks': [], 'geometry': [], 'scope': 'Real Tk windows with isolated fake validation/install callbacks. No installation or shortcut is written.'}
    def check(value, name):
        assert value, name
        report['checks'].append(name)
    def pump(ui, predicate=lambda: False, timeout=.15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            ui.window.update()
            if predicate():
                return
            time.sleep(.01)
        if timeout > 1:
            assert predicate(), 'Installer UI did not reach expected state'
    ui = None
    try:
        with tempfile.TemporaryDirectory(prefix='okdev-installer-ui-', dir=ROOT / 'build') as tmp:
            target = Path(tmp) / 'OKDEV'
            paths = [r'C:\Apps\LTK Manager', r'C:\Riot Games\League of Legends', str(target)]
            release = threading.Event()
            runs = []
            def validate(*args):
                return args
            def install(*args, make_shortcut=True, progress=lambda _: None):
                runs.append((args, make_shortcut))
                progress('QA: Dosya hazırlığı simüle ediliyor…')
                if not release.wait(5):
                    raise RuntimeError('QA worker timeout')
                return target, ''
            ui = InstallerWindow('2.0.0', paths, validate, install, ROOT / 'assets/icon.ico')
            pump(ui)
            geometry = ui.geometry(); report['geometry'].append({'case':'normal', **geometry})
            check(geometry['footer_bottom'] <= geometry['height'], 'Installer actions fit the initial window')
            capture_window(ui.window, out / 'screenshots/installer-ready.png')
            ui.validate = lambda *_: (_ for _ in ()).throw(ValueError('League of Legends.exe bulunamadı. Oyun klasörünü kontrol et.'))
            ui.action.invoke(); pump(ui)
            check('Oyun klasörünü' in ui.status.get() and not ui.busy, 'Validation failure stays inline and permits correction')
            check(str(ui.action['state']) == 'normal', 'Validation failure leaves install action available')
            capture_window(ui.window, out / 'screenshots/installer-validation.png')
            ui.validate = validate
            ui.start(); ui.start(); pump(ui)
            check(len(runs) == 1, 'Repeated start cannot launch two installers')
            check(all(str(widget['state']) == 'disabled' for widget in ui.controls + [ui.action, ui.cancel]), 'Fields and actions are locked during the write operation')
            ui.close(); check(ui.window.winfo_exists(), 'Closing during a write keeps the installer alive')
            capture_window(ui.window, out / 'screenshots/installer-progress.png')
            release.set(); pump(ui, lambda: not ui.busy, 5)
            check(ui.installed == target and str(ui.action['state']) == 'normal', 'Completion changes the primary action to the installed folder')
            check(ui.cancel['text'] == 'Bitir', 'Completion offers an explicit finish action')
            capture_window(ui.window, out / 'screenshots/installer-complete.png')
            with patch('installer_ui.os.startfile', side_effect=OSError('QA folder unavailable')):
                ui.action.invoke(); pump(ui)
            check(ui.installed == target and ui.status_title.get() == 'Klasör açılamadı', 'Folder opening failure preserves completed installation state')
            ui.close(); ui = None

            def fail_install(*args, **kwargs):
                raise OSError('QA: Yazma işlemi başarısız. ' + 'Uzun dosya yolu / ayrıntı ' * 70)
            ui = InstallerWindow('2.0.0', paths, validate, fail_install, ROOT / 'assets/icon.ico')
            ui.window.geometry('720x590')
            ui.start(); pump(ui, lambda: not ui.busy, 5)
            check(ui.installed is None and ui.status_title.get() == 'Kurulum tamamlanamadı', 'Worker failure produces a recoverable installation error')
            check(all(str(widget['state']) == 'normal' for widget in ui.controls + [ui.action, ui.cancel]), 'Worker failure restores editable controls and retry')
            check(len(ui.status.get()) <= 180 and ui.details_action.winfo_viewable(), 'Long failure messages stay bounded with accessible full details')
            geometry = ui.geometry()
            check(geometry['footer_bottom'] <= geometry['height'] and geometry['body_viewport'] >= 100, 'Long errors preserve the action footer and scroll area')
            ui.details_action.invoke(); pump(ui)
            check(ui._detail_window is not None and ui._detail_window.winfo_viewable(), 'Full error details open in a readable scrollable dialog')
            capture_window(ui._detail_window, out / 'screenshots/installer-error-details.png')
            ui._detail_window.focus_force(); pump(ui)
            ui._detail_window.event_generate('<Escape>'); pump(ui)
            check(ui._detail_window is None, 'Escape closes error details without closing the installer')
            capture_window(ui.window, out / 'screenshots/installer-worker-error.png')
            ui.install = install
            ui.start(); pump(ui, lambda: not ui.busy, 5)
            check(ui.installed == target, 'Retry succeeds after a worker failure')
            ui.close(); ui = None

            for scale in (1.0, 1.5, 2.0):
                ui = InstallerWindow('2.0.0', paths, validate, install, ROOT / 'assets/icon.ico', scale=scale)
                # Exercise a constrained height at the current font scale.
                ui.window.geometry(f'{round(720*scale)}x{round(590*scale)}')
                pump(ui)
                geometry = ui.geometry(); report['geometry'].append({'case':f'scale-{scale}', **geometry})
                check(abs(geometry['scale'] - scale) < .02, f'Test uses the requested {int(scale*100)}% font scale')
                check(geometry['footer_bottom'] <= geometry['height'], f'Action footer fits at {int(scale*100)}% font scale')
                check(geometry['body_viewport'] >= 100, f'Scroll viewport remains usable at {int(scale*100)}% font scale')
                ui.entries[-1].focus_force(); ui.reveal(ui.entries[-1]); pump(ui)
                top = ui.entries[-1].winfo_rooty(); bottom = top + ui.entries[-1].winfo_height()
                viewport_top = ui.canvas.winfo_rooty(); viewport_bottom = viewport_top + ui.canvas.winfo_height()
                check(viewport_top <= top and bottom <= viewport_bottom, f'Keyboard focus reveals the destination field at {int(scale*100)}% scale')
                capture_window(ui.window, out / f'screenshots/installer-{int(scale*100)}.png')
                ui.close(); ui = None
            check(not target.exists(), 'UI verification created no installation')
            report['ok'] = True
    except Exception as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        if ui and not ui._closed:
            ui.busy = False
            ui.close()
        (out / 'installer-ui.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
