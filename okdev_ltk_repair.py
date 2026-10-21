"""One-time bridge for old clients blocked before their application updater."""
import hashlib
import json
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading

VERSION = '1.5.2'
RESOURCES = Path(getattr(sys, '_MEIPASS', Path(__file__).parent/'release'))


def repair(install, game, status):
    import psutil
    from launcher.update.update_installer import UpdateInstaller
    from okdev_install_transaction import installation_lock, recover
    from okdev_update_helper import apply_update, validate_tree, wait_for_install_exit
    from okdev_ltk_update import ensure_patcher
    install, game = Path(install).absolute(), Path(game).absolute()
    validate_tree(install)
    metadata = json.loads((install/'okdev-install.json').read_text(encoding='utf-8'))
    if not metadata.get('install_id') or not (install/'OKDEV.exe').is_file():
        raise ValueError('Geçerli OKDEV kurulum klasörünü seçin.')
    if tuple(map(int, metadata['version'].split('.'))) > (1, 5, 2):
        raise ValueError('Kurulu OKDEV daha yeni; eski sürüme geçilmedi.')
    # Old elevated processes may hide their paths. Never proceed around them.
    for process in psutil.process_iter(['name', 'exe']):
        name = (process.info.get('name') or '').lower()
        if name in {'okdev.exe', 'okdev-updater.exe', 'ltk_patcher_host.exe'}:
            raise ValueError('OKDEV’i (eski hata penceresi dahil) ve LTK Manager’ı tamamen kapatın.')
    wait_for_install_exit(install, timeout=0)
    manifest = json.loads((RESOURCES/'ltk-repair-payload.json').read_text(encoding='utf-8'))
    archive = RESOURCES/f'OKDEV_Update_{VERSION}.zip'
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != manifest['sha256']:
            raise ValueError('Onarım paketinin bütünlüğü doğrulanamadı.')
    with tempfile.TemporaryDirectory(prefix='okdev-repair-') as temp:
        import shutil
        temp = Path(temp)
        local_archive = temp/archive.name
        shutil.copy2(archive, local_archive)
        payload = UpdateInstaller().extract_update(local_archive, temp/'staging', lambda _: None, status)
        if payload is None:
            raise ValueError('Güncelleme paketi reddedildi.')
        with installation_lock(install):
            recover(install)
            wait_for_install_exit(install, timeout=0)
            ensure_patcher(install/'_internal/injection/tools', game/'League of Legends.exe', status)
            wait_for_install_exit(install, timeout=0)
            status('OKDEV 1.5.2 kuruluyor; mevcut kurulum yedekleniyor…')
            backup = apply_update(install, payload)
    return backup


def main():
    import tkinter as tk
    from tkinter import filedialog, messagebox
    root = tk.Tk()
    root.title('OKDEV 1.5.2 — LTK ve güncelleme onarımı')
    root.geometry('690x330')
    install = tk.StringVar(value=str(Path(os.environ.get('LOCALAPPDATA', ''))/'Programs/OKDEV'))
    game = tk.StringVar(value='C:/Riot Games/League of Legends/Game')
    try:
        from injection.config.config_manager import ConfigManager
        saved = ConfigManager().load_league_path()
        if saved:
            game.set(saved)
    except Exception:
        pass
    tk.Label(root, text='Başlamadan önce League istemcisini, OKDEV’i ve eski hata penceresini kapatın.',
             wraplength=650).pack(pady=14)
    controls = []
    for label, variable in [('OKDEV kurulum klasörü', install), ('League Game klasörü', game)]:
        frame = tk.Frame(root)
        frame.pack(fill='x', padx=18, pady=7)
        tk.Label(frame, text=label, width=24, anchor='w').pack(side='left')
        entry = tk.Entry(frame, textvariable=variable)
        entry.pack(side='left', fill='x', expand=True)
        def choose(value=variable):
            selected = filedialog.askdirectory()
            if selected:
                value.set(selected)
        button = tk.Button(frame, text='Seç…', command=choose)
        button.pack(side='right')
        controls.extend([entry, button])
    text = tk.StringVar(value='Resmî LTK paketi internetten indirilir. Modlarınız ve ayarlarınız korunur.')
    tk.Label(root, textvariable=text, wraplength=650).pack(padx=18, pady=16)
    messages = queue.Queue()
    running = False

    def start():
        nonlocal running
        running = True
        selected_install, selected_game = install.get(), game.get()
        for control in controls:
            control.configure(state='disabled')
        def work():
            try:
                backup = repair(selected_install, selected_game, lambda msg: messages.put(('status', msg)))
                messages.put(('done', f'Onarım tamamlandı. OKDEV’i açabilirsiniz.\nYedek: {backup}'))
            except Exception as exc:
                messages.put(('error', str(exc)))
        threading.Thread(target=work, daemon=True).start()

    controls.append(tk.Button(root, text='LTK’yi onar ve OKDEV 1.5.2’ye güncelle', command=start))
    controls[-1].pack(pady=5)

    def poll():
        nonlocal running
        while not messages.empty():
            kind, message = messages.get_nowait()
            text.set(message)
            if kind != 'status':
                running = False
                for control in controls:
                    control.configure(state='normal')
                if kind == 'error':
                    messagebox.showerror('Onarım tamamlanamadı', message)
        root.after(100, poll)
    root.protocol('WM_DELETE_WINDOW', lambda: None if running else root.destroy())
    poll()
    root.mainloop()


if __name__ == '__main__':
    if '--ltk-self-check' in sys.argv:
        from okdev_ltk_update import self_check
        offset = sys.argv.index('--ltk-self-check')
        raise SystemExit(self_check(*sys.argv[offset+1:offset+4]))
    else:
        main()
