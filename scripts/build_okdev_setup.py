"""Build the shareable installer from clean OKDEV application output."""
import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'scripts'))
from create_update_package import app_version
version = app_version()
app = root / 'dist/OKDEV'
setup = root / 'setup_app'
assert (app / 'OKDEV.exe').is_file()
shutil.copy2(root / 'LICENSE', app / 'LICENSE-Rose.txt')
shutil.copy2(root / 'vendor/PenguLoader-1.1.6/LICENSE', app / 'LICENSE-PenguLoader.txt')
shutil.copy2(root / 'injection/tools/patcher.py', setup / 'patcher_check.py')
(app / 'OKDEV-HAKKINDA.txt').write_text(
    f'OKDEV {version}\n'
    'Based on Rose 1.4.4: https://github.com/Alban1911/Rose\n'
    'Copyright (c) 2026 Alban and Florent - MIT license retained.\n'
    'Core built from PenguLoader/PenguLoader v1.1.6, MIT license retained.\n'
    'Application updates: https://github.com/okdev01/OKDEV/releases\n'
    'User data: LOCALAPPDATA/OKDEV. Legacy data is copied once.\n'
    'LTK patcher is supplied by the user and is not redistributed.\n', encoding='utf-8-sig')
with zipfile.ZipFile(setup / 'payload.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
    for path in sorted(app.rglob('*')):
        if not path.is_file():
            continue
        name = path.name.lower()
        assert 'ltk_patcher' not in name, path
        assert name not in {'config.ini', 'historic.json', 'analytics_install_id.txt', 'config', 'datastore'}, path
        assert not name.endswith(('.log', '.log.old')), path
        bundle.write(path, path.relative_to(app))
subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile',
    '--windowed', '--name', f'OKDEV_Setup_{version}', '--icon', str(root / 'assets/icon.ico'),
    '--version-file', str(root / 'okdev_version.txt'), '--paths', str(root),
    '--distpath', str(root / 'release'), '--workpath', str(root / 'build/setup'),
    '--specpath', str(setup), '--add-data', str(setup / 'payload.zip') + ';.',
    '--add-data', str(root / 'assets/icon.ico') + ';.',
    str(setup / 'setup.py')], cwd=root, check=True)
exe = root / f'release/OKDEV_Setup_{version}.exe'
exe.with_suffix('.sha256.txt').write_text(hashlib.sha256(exe.read_bytes()).hexdigest() + '  ' + exe.name + '\n', encoding='ascii')
print(f'Built {exe.name}: {exe.stat().st_size / 1048576:.1f} MiB')
