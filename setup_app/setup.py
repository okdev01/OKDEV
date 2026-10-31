"""OKDEV per-user installer. LTK binaries are supplied by the recipient."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
import stat
from pathlib import Path, PurePosixPath

from patcher_check import read_dll_eol, read_game_build

VERSION = '2.1.3'
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
    patcher, game = find_patcher(patcher) if patcher else None, find_game(game)
    if existing_install(destination) is not None:
        check_closed(destination)
    if patcher is None:
        # First launch obtains and verifies the official skin dependency. Users
        # do not need another download or a directory of manually copied DLLs.
        return None, game, destination
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
        if patcher is not None:
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
    return '', game, destination


def gui(smoke=False):
    from installer_ui import run
    icon = RESOURCES / 'icon.ico'
    if not icon.is_file():
        icon = Path(__file__).resolve().parents[1] / 'assets/icon.ico'
    return run(VERSION, detect_paths(), validate, install, icon, smoke=smoke)


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
