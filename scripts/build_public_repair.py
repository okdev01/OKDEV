"""Build the single-use, public 1.2.1 migration tool."""
import hashlib
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
    '--onefile', '--windowed', '--uac-admin', '--name', 'OKDEV_Repair_1.2.1',
    '--icon', str(root/'assets/icon.ico'), '--add-data', str(root/'release/OKDEV_Update_1.2.1.zip')+';.',
    '--distpath', str(root/'release'), '--workpath', str(root/'build/repair-public'),
    '--specpath', str(root/'build'), str(root/'okdev_repair.py')], cwd=root, check=True)
exe = root/'release/OKDEV_Repair_1.2.1.exe'
exe.with_suffix('.sha256.txt').write_text(hashlib.sha256(exe.read_bytes()).hexdigest()+'  '+exe.name+'\n')
