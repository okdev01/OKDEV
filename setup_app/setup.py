"""OKDEV per-user installer. LTK binaries are supplied by the recipient."""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from patcher_check import read_dll_eol, read_game_build

VERSION = '1.0.0'
RESOURCES = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
PATCHER_NAMES = ('ltk_patcher_host.exe', 'ltk_patcher_dll.dll')


def find_patcher(selected):
    root = Path(selected)
    for folder in (root, root / '_internal/injection/tools', root / 'injection/tools'):
        if all((folder / name).is_file() for name in PATCHER_NAMES):
            return folder
    raise ValueError('Bu klasörde iki LTK patcher dosyası bulunamadı. LTK Manager veya Rose kurulum klasörünü seçin.')


def find_game(selected):
    root = Path(selected)
    for folder in (root / 'Game', root):
        if (folder / 'League of Legends.exe').is_file():
            return folder
    raise ValueError('League of Legends.exe bulunamadı. League of Legends veya Game klasörünü seçin.')


def validate(patcher, game, destination):
    patcher, game = find_patcher(patcher), find_game(game)
    destination = Path(destination).expanduser().absolute()
    if destination == Path(destination.anchor) or not destination.name:
        raise ValueError('Kurulum için sürücü kökü yerine OKDEV gibi ayrı bir klasör seçin.')
    if destination.exists():
        raise ValueError('Hedef klasör zaten var. Mevcut dosyaları korumak için yeni bir OKDEV klasörü seçin.')
    for name in PATCHER_NAMES:
        with (patcher / name).open('rb') as stream:
            if stream.read(2) != b'MZ':
                raise ValueError(f'{name} geçerli bir Windows dosyası değil.')
    cutoff = read_dll_eol(patcher / PATCHER_NAMES[1])
    build = read_game_build(game / 'League of Legends.exe')
    if cutoff is None or build is None:
        raise ValueError('Patcher veya oyun sürümü doğrulanamadı. Orijinal LTK ve oyun dosyalarını seçin.')
    if build > cutoff:
        raise ValueError('Bu patcher seçilen oyun sürümünü desteklemiyor. Güncel LTK patcher dosyaları gerekli.')
    return patcher, game, destination


def safe_members(bundle):
    for info in bundle.infolist():
        path = PurePosixPath(info.filename)
        if path.is_absolute() or '..' in path.parts or '\\' in info.filename or ':' in info.filename:
            raise ValueError('Kurulum paketinde geçersiz dosya yolu var.')
        if any(part.lower().startswith('ltk_patcher') for part in path.parts):
            raise ValueError('Dağıtım paketi LTK dosyaları içermemeli.')
        yield info


def shortcut(destination):
    # Pass paths through environment variables, never interpolate them into PowerShell code.
    env = os.environ.copy()
    env['OKDEV_SETUP_TARGET'] = str(destination / 'OKDEV.exe')
    env['OKDEV_SETUP_WORKDIR'] = str(destination)
    script = r'''$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'OKDEV.lnk'))
$link.TargetPath = $env:OKDEV_SETUP_TARGET
$link.WorkingDirectory = $env:OKDEV_SETUP_WORKDIR
$link.IconLocation = $env:OKDEV_SETUP_TARGET + ',0'
$link.Description = 'OKDEV'
$link.Save()
'''
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                   env=env, check=True, capture_output=True,
                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def install(patcher, game, destination, make_shortcut=True, progress=lambda text: None):
    patcher, game, destination = validate(patcher, game, destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.okdev-install-', dir=destination.parent))
    committed = False
    try:
        progress('Uygulama dosyaları çıkarılıyor…')
        with zipfile.ZipFile(RESOURCES / 'payload.zip') as bundle:
            members = list(safe_members(bundle))
            bundle.extractall(staging, members)
        if not (staging / 'OKDEV.exe').is_file():
            raise ValueError('Kurulum paketinde OKDEV.exe eksik.')
        tools = staging / '_internal/injection/tools'
        tools.mkdir(parents=True, exist_ok=True)
        progress('Seçtiğiniz LTK dosyaları kopyalanıyor…')
        for name in PATCHER_NAMES:
            shutil.copy2(patcher / name, tools / name)
        (staging / 'okdev-install.json').write_text(json.dumps({
            'install_id': str(uuid.uuid4()), 'version': VERSION, 'game_dir': str(game),
        }, ensure_ascii=False, indent=2), encoding='utf-8')
        # Rename is atomic and fails if another installation created the destination.
        staging.rename(destination)
        committed = True
        warning = ''
        if make_shortcut:
            progress('Masaüstü kısayolu oluşturuluyor…')
            try:
                shortcut(destination)
            except (OSError, subprocess.SubprocessError):
                warning = 'Kısayol oluşturulamadı. Kurulum klasöründen OKDEV.exe dosyasını açabilirsiniz.'
        return destination, warning
    finally:
        if not committed and staging.parent == destination.parent and staging.name.startswith('.okdev-install-'):
            shutil.rmtree(staging)


def detect_paths():
    program_files = Path(os.environ.get('ProgramFiles', r'C:\Program Files'))
    candidates = [program_files / 'LTK Manager', program_files / 'Rose',
                  Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/LTK Manager']
    patcher = ''
    for candidate in candidates:
        try:
            patcher = str(find_patcher(candidate))
            break
        except ValueError:
            pass
    game = ''
    for drive in ('C', 'D', 'E'):
        candidate = Path(f'{drive}:/Riot Games/League of Legends')
        try:
            game = str(find_game(candidate))
            break
        except ValueError:
            pass
    destination = str(Path(os.environ['LOCALAPPDATA']) / 'Programs/OKDEV')
    return patcher, game, destination


def gui(smoke=False):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    window = tk.Tk()
    window.title('OKDEV Kurulum')
    window.geometry('760x600')
    window.minsize(700, 570)
    window.configure(bg='#101724')
    if smoke:
        window.withdraw()
    style = ttk.Style(window)
    style.theme_use('clam')
    style.configure('TFrame', background='#101724')
    style.configure('TLabel', background='#101724', foreground='#e6edf7', font=('Segoe UI', 10))
    style.configure('Title.TLabel', font=('Segoe UI', 28, 'bold'), foreground='#61dec0')
    style.configure('TButton', font=('Segoe UI', 10), padding=(15, 8))
    style.configure('TCheckbutton', background='#101724', foreground='#e6edf7', font=('Segoe UI', 10))
    panel = ttk.Frame(window, padding=28)
    panel.pack(fill='both', expand=True)
    panel.columnconfigure(0, weight=1)
    ttk.Label(panel, text='OKDEV', style='Title.TLabel').grid(row=0, column=0, sticky='w')
    ttk.Label(panel, text='Kurulum • 1.0.0', foreground='#9daec5').grid(row=0, column=1, sticky='e')
    ttk.Label(panel, text='Klasörleri seçin. Gerekli dosyaları kontrol edip kurulumu tamamlayalım.',
              wraplength=650).grid(row=1, column=0, columnspan=2, sticky='w', pady=(8, 24))
    values = [tk.StringVar(value=value) for value in detect_paths()]
    controls = []
    labels = ['1  LTK Manager veya Rose dosya klasörü', '2  League of Legends klasörü', '3  OKDEV kurulum klasörü']
    for index, (label, value) in enumerate(zip(labels, values)):
        row = 2 + index * 2
        ttk.Label(panel, text=label).grid(row=row, column=0, columnspan=2, sticky='w', pady=(10, 5))
        entry = ttk.Entry(panel, textvariable=value, font=('Segoe UI', 10))
        entry.grid(row=row + 1, column=0, sticky='ew', padx=(0, 10))
        def choose(var=value, is_destination=index == 2):
            selected = filedialog.askdirectory(parent=window, title='Klasör seçin', mustexist=True)
            if selected:
                path = Path(selected)
                var.set(str(path / 'OKDEV' if is_destination else path))
        button = ttk.Button(panel, text='Gözat…', command=choose)
        button.grid(row=row + 1, column=1, sticky='ew')
        controls.extend((entry, button))
    desktop = tk.BooleanVar(value=True)
    check = ttk.Checkbutton(panel, text='Masaüstüne OKDEV kısayolu ekle', variable=desktop)
    check.grid(row=8, column=0, columnspan=2, sticky='w', pady=(22, 6))
    controls.append(check)
    status = tk.StringVar(value='LTK dosyaları seçtiğiniz klasörden alınır. Python kurulumu gerekmez.')
    ttk.Label(panel, textvariable=status, wraplength=650, foreground='#9daec5').grid(row=9, column=0, columnspan=2, sticky='w', pady=8)
    bar = ttk.Progressbar(panel, mode='indeterminate')
    bar.grid(row=10, column=0, columnspan=2, sticky='ew', pady=(2, 15))
    messages = queue.Queue()
    busy = False
    installed = None

    def start():
        nonlocal busy
        try:
            args = validate(*(value.get().strip() for value in values))
        except (ValueError, OSError) as error:
            messagebox.showerror('Klasörleri kontrol edin', str(error), parent=window)
            return
        busy = True
        for control in controls + [action]:
            control.configure(state='disabled')
        bar.start(12)
        add_shortcut = desktop.get()
        def worker():
            try:
                result = install(*args, make_shortcut=add_shortcut, progress=lambda text: messages.put(('progress', text)))
                messages.put(('done', result))
            except Exception as error:
                messages.put(('error', str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def poll():
        nonlocal busy, installed
        try:
            while True:
                kind, value = messages.get_nowait()
                if kind == 'progress':
                    status.set(value)
                    continue
                busy = False
                bar.stop()
                if kind == 'done':
                    installed, warning = value
                    status.set(warning or 'Kurulum tamamlandı. OKDEV açılırken Windows yönetici izni isteyebilir.')
                    action.configure(text='OKDEV klasörünü aç', state='normal', command=lambda: os.startfile(installed))
                else:
                    for control in controls + [action]:
                        control.configure(state='normal')
                    status.set('Kurulum tamamlanamadı. Konumları kontrol edip yeniden deneyin.')
                    messagebox.showerror('Kurulum hatası', value, parent=window)
        except queue.Empty:
            pass
        window.after(100, poll)

    action = ttk.Button(panel, text='Kontrol et ve kur', command=start)
    action.grid(row=11, column=0, columnspan=2, sticky='ew')
    ttk.Label(panel, text='Rose tabanlı bağımsız sürüm • Özgün geliştirici lisansları pakete dahildir.',
              foreground='#7488a4', wraplength=650).grid(row=12, column=0, columnspan=2, sticky='w', pady=(16, 0))
    window.protocol('WM_DELETE_WINDOW', lambda: None if busy else window.destroy())
    if smoke:
        window.update_idletasks()
        window.destroy()
        return
    poll()
    window.mainloop()


if __name__ == '__main__':
    if '--smoke-test' in sys.argv:
        gui(smoke=True)
        with zipfile.ZipFile(RESOURCES / 'payload.zip') as bundle:
            assert any(item.filename == 'OKDEV.exe' for item in safe_members(bundle))
            assert bundle.testzip() is None
        output = Path(sys.argv[sys.argv.index('--smoke-test') + 1])
        output.write_text('OKDEV installer UI and embedded payload: PASS', encoding='utf-8')
    else:
        gui()
