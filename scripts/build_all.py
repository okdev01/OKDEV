"""Build all OKDEV release artifacts from source."""
import subprocess
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
for script in ('build_brand_assets.py','build_pyinstaller.py','create_installer.py'):
    subprocess.run([sys.executable,str(root/'scripts'/script)],cwd=root,check=True)
