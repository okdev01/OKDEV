"""Exercise the native startup window without running any startup operations."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from launcher.ui.update_dialog import UpdateDialog
from utils.system.win32_base import user32, PBM_SETPOS, WM_CLOSE
from check_installer_ui import capture_window


def main():
    out=ROOT/'output/ui2-20261030'
    report={'ok':False,'checks':[],'geometry':[],'scope':'Actual Win32 startup windows, simulated download progress and isolated real archive preparation. No public network, installation or game launch.'}
    dialog=None
    def check(value,label):
        assert value,label
        report['checks'].append(label)
    def pump(seconds=.08):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            dialog.pump_messages();time.sleep(.01)
    def get_text(hwnd):
        buffer=ctypes.create_unicode_buffer(2048)
        user32.GetWindowTextW(hwnd,buffer,len(buffer))
        return buffer.value
    def capture(name):
        adapter=SimpleNamespace(update_idletasks=dialog.pump_messages,update=dialog.pump_messages,winfo_id=lambda:dialog.hwnd)
        capture_window(adapter,out/f'screenshots/startup-{name}.png')
    try:
        for scale in (1,1.5,2):
            dialog=UpdateDialog(scale=scale)
            dialog.show_window();pump()
            dialog.set_detail('OKDEV güncelleniyor…')
            dialog.set_status('Güncelleme dosyaları indiriliyor. Mevcut ayarların korunur.')
            dialog.update_transfer_progress(5*1024*1024,20*1024*1024);pump()
            check(dialog._progress_value==25 and not dialog._marquee_enabled,f'Known download size shows 25% at {int(scale*100)}% DPI')
            check(user32.SendMessageW(dialog.progress_hwnd,0x0408,0,0)==25,f'Native progress control reflects 25% at {int(scale*100)}% DPI')
            check(get_text(dialog.detail_hwnd)=='OKDEV güncelleniyor…','Phase heading is preserved alongside detail')
            check('Güncelleme dosyaları' in get_text(dialog.status_hwnd) and '%25' in get_text(dialog.status_hwnd),'Detail and transfer progress are both visible')
            width,height=dialog.get_client_size()
            client=wintypes.RECT();user32.GetWindowRect(dialog.hwnd,ctypes.byref(client))
            item={'scale':scale,'client_width':width,'client_height':height,'controls':[]}
            for hwnd in (dialog.brand_hwnd,dialog.detail_hwnd,dialog.status_hwnd,dialog.progress_hwnd):
                rect=wintypes.RECT();user32.GetWindowRect(hwnd,ctypes.byref(rect))
                point=wintypes.POINT(rect.left,rect.top);user32.ScreenToClient(dialog.hwnd,ctypes.byref(point))
                box={'x':point.x,'y':point.y,'width':rect.right-rect.left,'height':rect.bottom-rect.top}
                item['controls'].append(box)
                check(box['x']>=0 and box['y']>=0 and box['x']+box['width']<=width and box['y']+box['height']<=height,f'Native control fits at {int(scale*100)}% DPI')
            report['geometry'].append(item)
            capture(f'{int(scale*100)}')
            dialog.update_transfer_progress(8*1024*1024,None);pump()
            check(dialog._marquee_enabled and dialog._progress_value is None,'Unknown transfer size uses indeterminate progress')
            dialog.set_progress(150);pump()
            check(dialog._progress_value==100 and not dialog._marquee_enabled,'Determinate progress clamps to 100 and stops marquee')
            dialog.reset_progress();check(dialog._progress_value==0,'Reset clears determinate progress without restarting marquee')
            dialog.clear_transfer_text();pump()
            check('%' not in get_text(dialog.status_hwnd),'Clearing a transfer removes its old byte status')
            worker=threading.Thread(target=lambda:dialog.update_transfer_progress(7,10));worker.start();worker.join();pump()
            check(dialog._progress_value==70,'Worker-thread progress is marshalled to the UI thread')
            user32.SendMessageW(dialog.hwnd,WM_CLOSE,0,0);pump()
            check(user32.IsWindow(dialog.hwnd),'Close is guarded while startup work is active')
            dialog.allow_close();user32.SendMessageW(dialog.hwnd,WM_CLOSE,0,0);pump()
            check(not user32.IsWindow(dialog.hwnd),'Completion permits closing the startup window')
            dialog.destroy_window();dialog=None
        from startup_preparation_qa import run
        dialog=UpdateDialog()
        dialog.show_window();pump()
        report['preparation']=run(dialog,capture,ROOT)
        check(report['preparation']['ok'],'Actual package preparation reaches the native progress control and clears old download state')
        dialog.destroy_window();dialog=None
        report['ok']=True
    except Exception as error:
        report['error']=f'{type(error).__name__}: {error}'
    finally:
        if dialog: dialog.destroy_window()
        (out/'startup-ui.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    return 0 if report['ok'] else 1


if __name__=='__main__': raise SystemExit(main())
