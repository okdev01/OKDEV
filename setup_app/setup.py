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
import stat
from pathlib import Path, PurePosixPath

from patcher_check import read_dll_eol, read_game_build

VERSION = '1.5.0'
RESOURCES = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
PATCHER_NAMES = ('ltk_patcher_host.exe', 'ltk_patcher_dll.dll')


def existing_install(destination):
    """Only update a recognized installation; never adopt an unrelated folder."""
    if not destination.exists():
        return None
    if destination.is_symlink() or destination.is_junction() or not destination.is_dir():
        raise ValueError('Hedef normal bir OKDEV kurulum klasörü olmalı; bağlantı veya dosya seçmeyin.')
    try:
        metadata = json.loads((destination / 'okdev-install.json').read_text(encoding='utf-8'))
        if not isinstance(metadata, dict) or not metadata.get('install_id') or not (destination / 'OKDEV.exe').is_file():
            raise ValueError()
        return metadata
    except PermissionError:
        raise ValueError('OKDEV kurulum klasörüne erişim izni yok. Kurulum klasörünün Windows izinleri onarılmalı; bu hata kurulumun eksik olduğu anlamına gelmez.') from None
    except (OSError, ValueError):
        raise ValueError('Hedef klasör var ancak doğrulanmış bir OKDEV kurulumu değil. OKDEV kurulum klasörünü veya yeni bir klasör seçin.') from None


def check_closed(destination):
    import psutil
    for process in psutil.process_iter(['exe']):
        try:
            executable = process.info.get('exe')
            if executable and Path(executable).resolve().is_relative_to(destination.resolve()):
                raise ValueError('OKDEV veya Pengu Loader açık. Sistem tepsisinden kapatıp yeniden deneyin.')
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


def copy_existing(source, staging):
    # Reject reparse points instead of copying data outside the installation.
    for folder, directories, files in os.walk(source, followlinks=False):
        for name in directories + files:
            path = Path(folder) / name
            if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError('Kurulum içinde klasör bağlantısı bulundu. Mevcut kurulumu korumak için yeni bir hedef klasör seçin.')
    shutil.copytree(source, staging, dirs_exist_ok=True)


def find_patcher(selected):
    root = Path(selected)
    for folder in (root, root / '_internal/injection/tools', root / 'injection/tools'):
        if all((folder / name).is_file() for name in PATCHER_NAMES):
            return folder
    raise ValueError('Bu klasörde iki LTK patcher dosyası bulunamadı. LTK Manager veya mevcut OKDEV kurulum klasörünü seçin.')


def find_game(selected):
    root = Path(selected)
    for folder in (root / 'Game', root):
        if (folder / 'League of Legends.exe').is_file():
            return folder
    raise ValueError('League of Legends.exe bulunamadı. League of Legends veya Game klasörünü seçin.')


def validate(patcher, game, destination):
    destination = Path(destination).expanduser().absolute()
    if destination == Path(destination.anchor) or not destination.name:
        raise ValueError('Kurulum için sürücü kökü yerine OKDEV gibi ayrı bir klasör seçin.')
    from okdev_install_transaction import installation_lock, recover
    with installation_lock(destination):
        recover(destination)
    patcher, game = find_patcher(patcher), find_game(game)
    if existing_install(destination) is not None:
        check_closed(destination)
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
    from okdev_branding import refresh_shortcut
    refresh_shortcut(destination, create=True)


def install(patcher, game, destination, make_shortcut=True, progress=lambda text: None):
    from okdev_install_transaction import installation_lock, recover
    with installation_lock(destination):
        recover(destination)
        return _install(patcher, game, destination, make_shortcut, progress)


def _install(patcher, game, destination, make_shortcut=True, progress=lambda text: None):
    patcher, game, destination = validate(patcher, game, destination)
    previous = existing_install(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.okdev-install-', dir=destination.parent))
    committed = False
    backup = None
    try:
        # tempfile.mkdtemp uses a private Windows ACL. Under UAC its owner may
        # be Administrators, which would lock the regular user out after rename.
        # Inherit the chosen installation parent's permissions before extraction.
        if os.name == 'nt':
            subprocess.run(['icacls.exe', str(staging), '/inheritance:e'],
                           check=True, capture_output=True,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if previous is not None:
            progress('Mevcut ayarlar ve dosyalar korunuyor…')
            copy_existing(destination, staging)
        progress('Uygulama dosyaları çıkarılıyor…')
        with zipfile.ZipFile(RESOURCES / 'payload.zip') as bundle:
            members = list(safe_members(bundle))
            if not any(item.filename == 'OKDEV.exe' for item in members):
                raise ValueError('Kurulum paketinde OKDEV.exe eksik.')
            bundle.extractall(staging, members)
        if not (staging / 'OKDEV.exe').is_file():
            raise ValueError('Kurulum paketinde OKDEV.exe eksik.')
        from okdev_branding import retire_legacy_plugins
        retire_legacy_plugins(staging / '_internal/Pengu Loader')
        tools = staging / '_internal/injection/tools'
        tools.mkdir(parents=True, exist_ok=True)
        progress('Seçtiğiniz LTK dosyaları kopyalanıyor…')
        for name in PATCHER_NAMES:
            shutil.copy2(patcher / name, tools / name)
        (staging / 'okdev-install.json').write_text(json.dumps({
            **(previous or {}),
            'install_id': previous['install_id'] if previous else str(uuid.uuid4()),
            'version': VERSION, 'game_dir': str(game),
        }, ensure_ascii=False, indent=2), encoding='utf-8')
        if previous is not None:
            check_closed(destination)
            if existing_install(destination) != previous:
                raise ValueError('Kurulum işlem sırasında değişti. Yeniden deneyin.')
            backup = destination.with_name(destination.name + '.backup-' + uuid.uuid4().hex[:12])
            # Both checked paths stay in the installation's parent directory.
            if backup.resolve().parent != destination.resolve().parent or backup.exists():
                raise ValueError('Güvenli yedek konumu oluşturulamadı.')
            from okdev_install_transaction import commit
            commit(destination, staging, backup)
        else:
            staging.rename(destination)
        committed = True
        warning = f'Güncelleme tamamlandı. Önceki kurulumun yedeği: {backup}' if backup else ''
        if make_shortcut:
            progress('Masaüstü kısayolu oluşturuluyor…')
            try:
                shortcut(destination)
            except (OSError, subprocess.SubprocessError):
                warning += ' Kısayol oluşturulamadı. Kurulum klasöründen OKDEV.exe dosyasını açabilirsiniz.'
        return destination, warning
    finally:
        if (not committed and staging.exists()
                and staging.resolve().parent == destination.parent.resolve()
                and not staging.is_symlink() and not staging.is_junction()
                and staging.name.startswith('.okdev-install-')):
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
    try:
        metadata = existing_install(Path(destination))
        if metadata:
            patcher = str(find_patcher(destination))
            if metadata.get('game_dir'):
                game = str(find_game(metadata['game_dir']))
    except ValueError:
        pass
    return patcher, game, destination


def gui(smoke=False):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    window = tk.Tk()
    icon = RESOURCES / 'icon.ico'
    if not icon.is_file():
        icon = Path(__file__).resolve().parents[1] / 'assets/icon.ico'
    if icon.is_file():
        window.iconbitmap(str(icon))
    window.title('OKDEV Kurulum')
    window.geometry('760x640')
    window.minsize(700, 640)
    window.configure(bg='#101116')
    if smoke:
        window.withdraw()
    style = ttk.Style(window)
    style.theme_use('clam')
    style.configure('TFrame', background='#101116')
    style.configure('TLabel', background='#101116', foreground='#f0edf7', font=('Segoe UI', 10))
    style.configure('Title.TLabel', font=('Segoe UI', 28, 'bold'), foreground='#baa3ff')
    style.configure('TButton', font=('Segoe UI', 10), padding=(15, 8), background='#25232e', foreground='#f0edf7', bordercolor='#393444')
    style.map('TButton', background=[('active', '#383046'), ('disabled', '#201e27')], foreground=[('disabled', '#77717e')])
    style.configure('Accent.TButton', background='#baa3ff', foreground='#211734')
    style.map('Accent.TButton', background=[('active', '#cbbaff'), ('disabled', '#665b80')], foreground=[('disabled', '#292433')])
    style.configure('TEntry', fieldbackground='#191920', foreground='#f0edf7', insertcolor='#baa3ff', padding=7)
    style.configure('TCheckbutton', background='#101116', foreground='#f0edf7', font=('Segoe UI', 10))
    style.map('TCheckbutton', background=[('active', '#101116')], foreground=[('disabled', '#77717e')])
    style.configure('Horizontal.TProgressbar', background='#baa3ff', troughcolor='#25232e', bordercolor='#25232e')
    panel = ttk.Frame(window, padding=28)
    panel.pack(fill='both', expand=True)
    panel.columnconfigure(0, weight=1)
    ttk.Label(panel, text='OKDEV', style='Title.TLabel').grid(row=0, column=0, sticky='w')
    ttk.Label(panel, text=f'Kurulum • {VERSION}', foreground='#b4adbf').grid(row=0, column=1, sticky='e')
    ttk.Label(panel, text='Yeni kurulum veya mevcut OKDEV klasörüne güncelleme. Güncellemede ayarlar ve eski kurulumun yedeği korunur.',
              wraplength=650).grid(row=1, column=0, columnspan=2, sticky='w', pady=(8, 24))
    values = [tk.StringVar(value=value) for value in detect_paths()]
    controls = []
    labels = ['1  LTK Manager veya mevcut OKDEV klasörü', '2  League of Legends klasörü', '3  OKDEV kurulum / güncelleme klasörü']
    for index, (label, value) in enumerate(zip(labels, values)):
        row = 2 + index * 2
        ttk.Label(panel, text=label).grid(row=row, column=0, columnspan=2, sticky='w', pady=(10, 5))
        entry = ttk.Entry(panel, textvariable=value, font=('Segoe UI', 10))
        entry.grid(row=row + 1, column=0, sticky='ew', padx=(0, 10))
        def choose(var=value, is_destination=index == 2):
            selected = filedialog.askdirectory(parent=window, title='Klasör seçin', mustexist=True)
            if selected:
                path = Path(selected)
                if is_destination and not (path / 'okdev-install.json').is_file() and path.name.lower() != 'okdev':
                    path = path / 'OKDEV'
                var.set(str(path))
        button = ttk.Button(panel, text='Gözat…', command=choose)
        button.grid(row=row + 1, column=1, sticky='ew')
        controls.extend((entry, button))
    desktop = tk.BooleanVar(value=True)
    check = ttk.Checkbutton(panel, text='Masaüstüne OKDEV kısayolu ekle', variable=desktop)
    check.grid(row=8, column=0, columnspan=2, sticky='w', pady=(22, 6))
    controls.append(check)
    status = tk.StringVar(value='LTK dosyaları seçtiğiniz klasörden alınır. Python kurulumu gerekmez.')
    ttk.Label(panel, textvariable=status, wraplength=650, foreground='#b4adbf').grid(row=9, column=0, columnspan=2, sticky='w', pady=8)
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

    action = ttk.Button(panel, text='Kur / Güncelle', command=start, style='Accent.TButton')
    action.grid(row=11, column=0, columnspan=2, sticky='ew')
    ttk.Label(panel, text='OKDEV • Açık kaynak bileşenlerin lisansları pakete dahildir.',
              foreground='#93889f', wraplength=650).grid(row=12, column=0, columnspan=2, sticky='w', pady=(16, 0))
    window.protocol('WM_DELETE_WINDOW', lambda: None if busy else window.destroy())
    if smoke:
        window.update_idletasks()
        geometry = {'width': 760, 'height': 640,
                    'content_width': panel.winfo_reqwidth(), 'content_height': panel.winfo_reqheight()}
        assert geometry['content_width'] <= geometry['width'] and geometry['content_height'] <= geometry['height'], 'Installer content exceeds its window'
        window.destroy()
        return geometry
    poll()
    window.mainloop()


if __name__ == '__main__':
    if '--smoke-test' in sys.argv:
        geometry = gui(smoke=True)
        with zipfile.ZipFile(RESOURCES / 'payload.zip') as bundle:
            assert any(item.filename == 'OKDEV.exe' for item in safe_members(bundle))
            assert bundle.testzip() is None
        output = Path(sys.argv[sys.argv.index('--smoke-test') + 1])
        output.write_text(json.dumps({'ok': True, 'version': VERSION, 'geometry': geometry,
            'checks': ['Installer UI constructed', 'Embedded archive CRC and application entry verified']}, indent=2), encoding='utf-8')
    else:
        gui()
