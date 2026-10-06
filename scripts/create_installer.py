"""Build the OKDEV setup and automatic update package."""
import subprocess
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
for script in ('build_okdev_setup.py','create_update_package.py'):
    subprocess.run([sys.executable,str(root/'scripts'/script)],cwd=root,check=True)
