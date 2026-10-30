"""Verify that repeated startup-window lifetimes release native resources."""
import ctypes
from ctypes import wintypes
import gc
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from launcher.ui.update_dialog import UpdateDialog
from utils.system.win32_base import user32


def main():
    import psutil
    kernel=ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    user32.GetGuiResources.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    user32.GetGuiResources.restype=wintypes.DWORD
    process=kernel.GetCurrentProcess()
    def sample():
        return {'gdi':user32.GetGuiResources(process,0),'user':user32.GetGuiResources(process,1),
                'handles':psutil.Process().num_handles()}
    def cycle():
        window=UpdateDialog()
        window.create_window()
        window.set_detail('QA kaynak kontrolü')
        window.update_transfer_progress(1,4)
        window.pump_messages()
        window.destroy_window()
    for _ in range(3):cycle()
    gc.collect()
    before=sample()
    snapshots=[]
    for n in range(60):
        cycle()
        if n%10==9:
            gc.collect();snapshots.append({'cycle':n+1,**sample()})
    after=sample()
    report={'ok':after['gdi']<=before['gdi']+1 and after['user']<=before['user']+1 and after['handles']<=before['handles']+2,
            'cycles':60,'before':before,'after':after,'samples':snapshots,
            'scope':'Own hidden Win32 QA windows; no downloads or startup operations.'}
    (ROOT/'output/ui2-20261030/startup-resources.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
    return 0 if report['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
