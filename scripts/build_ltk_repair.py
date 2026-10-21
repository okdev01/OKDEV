"""Build a bridge with the current update ZIP; never embed LTK binaries."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from create_update_package import app_version

version = app_version()
archive = ROOT/f'release/OKDEV_Update_{version}.zip'
with archive.open('rb') as stream:
    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
manifest = ROOT/'build/ltk-repair-payload.json'
manifest.write_text(json.dumps({'version': version, 'sha256': digest}), encoding='utf-8')
subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
    '--onefile', '--windowed', '--uac-admin', '--name', f'OKDEV_LTK_Repair_{version}',
    '--icon', str(ROOT/'assets/icon.ico'), '--paths', str(ROOT),
    '--version-file', str(ROOT/'okdev_version.txt'),
    '--add-data', str(archive)+';.', '--add-data', str(manifest)+';.',
    '--add-data', str(ROOT/'assets/7zip')+';assets/7zip',
    '--distpath', str(ROOT/'release'), '--workpath', str(ROOT/'build/ltk-repair-build'),
    '--specpath', str(ROOT/'build'), str(ROOT/'okdev_ltk_repair.py')], cwd=ROOT, check=True)
exe = ROOT/f'release/OKDEV_LTK_Repair_{version}.exe'
with exe.open('rb') as stream:
    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
exe.with_suffix('.sha256.txt').write_text(digest+'  '+exe.name+'\n', encoding='ascii')
