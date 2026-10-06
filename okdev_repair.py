"""Self-contained repair of existing installations; no game or LTK download."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

VERSION = '1.2.1'
DIGEST = '765a220508a8ac891d9a4af6b927d5838738d2dbf22fa46ed0884f1cd51a3085'
RESOURCES = Path(getattr(sys, '_MEIPASS', Path(__file__).parent/'release'))


def validate_install(install):
    from okdev_update_helper import validate_tree
    install = Path(install).resolve()
    validate_tree(install)
    metadata = json.loads((install/'okdev-install.json').read_text(encoding='utf-8'))
    if not metadata.get('install_id') or not (install/'OKDEV.exe').is_file():
        raise ValueError('Geçerli bir OKDEV kurulum klasörü seçin.')
    current = tuple(int(x) for x in metadata['version'].split('.'))
    if current > (1, 2, 1):
        raise ValueError('Kurulu sürüm bu araçtan daha yeni. Eski sürüme dönülmedi.')
    return install


def verified_archive():
    archive = RESOURCES/'OKDEV_Update_1.2.1.zip'
    if hashlib.sha256(archive.read_bytes()).hexdigest() != DIGEST:
        raise ValueError('Onarım paketinin bütünlüğü doğrulanamadı. Yeniden indirin.')
    return archive


def repair(install):
    import psutil
    from launcher.update.update_installer import UpdateInstaller
    from okdev_update_helper import apply_update, wait_for_install_exit
    from okdev_branding import refresh_shortcut
    install = validate_install(install)
    archive = verified_archive()
    processes = list(psutil.process_iter(['name', 'exe', 'cmdline']))
    if any((p.info['name'] or '').lower() in {'leagueclient.exe', 'leagueclientux.exe', 'leagueclientuxrender.exe', 'league of legends.exe'} for p in processes):
        raise ValueError('League oyununu ve istemcisini kapatıp yeniden deneyin. Hiçbir işlem kapatılmadı.')
    updater_path = Path(os.environ['LOCALAPPDATA'])/'OKDEV/updates/OKDEV-Updater.exe'
    log_path = updater_path.parent/'updater.log'
    targets = []
    for p in processes:
        exe = p.info.get('exe')
        if not exe:
            if (p.info['name'] or '').lower() in {'okdev.exe', 'okdev-updater.exe'}:
                raise ValueError('OKDEV işlemine erişilemiyor. Aracı yönetici olarak çalıştırın.')
            continue
        exe = Path(exe).resolve()
        if exe.is_relative_to(install):
            targets.append(p)
        elif exe == updater_path.resolve():
            args = p.info.get('cmdline') or []
            if '--install-dir' in args and Path(args[args.index('--install-dir')+1]).resolve() == install:
                if not log_path.exists() or not log_path.read_text(encoding='utf-8').startswith('Update failed;'):
                    raise ValueError('Bir güncelleme çalışıyor. Tamamlanmasını bekleyin.')
                targets.append(p)
    # Verify/extract before stopping any application. The temporary directory is external.
    import shutil
    with tempfile.TemporaryDirectory(prefix='OKDEV-repair-') as folder:
        work = Path(folder)
        local = work/archive.name
        shutil.copy2(archive, local)
        errors = []
        payload = UpdateInstaller().extract_update(local, work/'staging', lambda _: None, errors.append)
        if payload is None:
            raise ValueError('; '.join(errors))
        for process in reversed(targets):
            try:
                process.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(targets, timeout=15)
        if alive:
            raise ValueError('OKDEV kapanmadı. Bilgisayarı yeniden başlatıp bu aracı çalıştırın.')
        wait_for_install_exit(install)
        backup = apply_update(install, payload)
    try:
        refresh_shortcut(install)
    except (OSError, subprocess.SubprocessError):
        pass
    return backup


def main():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    import threading
    import queue
    if '--smoke-test' in sys.argv:
        with zipfile.ZipFile(verified_archive()) as z:
            assert z.testzip() is None
            assert json.loads(z.read('okdev-update.json'))['version'] == VERSION
        Path(sys.argv[sys.argv.index('--smoke-test')+1]).write_text('PASS: embedded 1.2.1 repair payload and SHA-256')
        return
    window = tk.Tk()
    window.title('OKDEV • Güncelleme Onarımı')
    window.geometry('630x340')
    window.resizable(False, False)
    panel = ttk.Frame(window, padding=24); panel.pack(fill='both', expand=True)
    ttk.Label(panel, text='OKDEV 1.2.1 güncelleme onarımı', font=('Segoe UI', 17, 'bold')).pack(anchor='w')
    ttk.Label(panel, text='Eski güncelleyicide takılan kurulumlar için tek seferlik onarım.\nOnar düğmesi OKDEV ve Mod Merkezi işlemlerini kapatır.\nAyarlar ve LTK dosyaları korunur; önceki kurulum yedeklenir.\nLeague açıksa hiçbir değişiklik yapılmaz.', wraplength=570).pack(anchor='w', pady=15)
    target = tk.StringVar(value=str(Path(os.environ['LOCALAPPDATA'])/'Programs/OKDEV'))
    entry = ttk.Entry(panel, textvariable=target, width=77); entry.pack(fill='x')
    def choose():
        path = filedialog.askdirectory(title='Mevcut OKDEV kurulum klasörü')
        if path: target.set(path)
    browse = ttk.Button(panel, text='Kurulum klasörünü seç', command=choose); browse.pack(anchor='w', pady=7)
    status = tk.StringVar(value='League’i kapatın, ardından Onar düğmesine basın.')
    ttk.Label(panel, textvariable=status, wraplength=570).pack(anchor='w', pady=7)
    results = queue.Queue(); busy = False
    def start():
        nonlocal busy
        busy = True
        for control in (entry, browse, action): control.configure(state='disabled')
        status.set('Paket doğrulanıyor ve kurulum onarılıyor…')
        chosen = target.get()
        def worker():
            try: results.put((True, str(repair(chosen))))
            except Exception as exc: results.put((False, str(exc)))
        threading.Thread(target=worker, daemon=True).start()
    action = ttk.Button(panel, text='Onar ve 1.2.1’e geçir', command=start); action.pack(fill='x')
    def poll():
        nonlocal busy
        try:
            ok, value = results.get_nowait(); busy = False
            if ok:
                status.set('Onarım tamamlandı. Sonraki güncellemeleri OKDEV içinden alabilirsiniz.')
                action.configure(text='OKDEV’i aç', state='normal', command=lambda: subprocess.Popen([str(Path(target.get())/'OKDEV.exe')], cwd=target.get()))
                messagebox.showinfo('OKDEV', '1.2.1 kuruldu. Eski kurulumun yedeği:\n'+value, parent=window)
            else:
                status.set('Onarım tamamlanamadı.')
                for control in (entry, browse, action): control.configure(state='normal')
                messagebox.showerror('OKDEV onarım', value, parent=window)
        except queue.Empty: pass
        window.after(100, poll)
    window.protocol('WM_DELETE_WINDOW', lambda: None if busy else window.destroy())
    poll(); window.mainloop()


if __name__ == '__main__':
    main()
