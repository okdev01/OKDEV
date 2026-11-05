# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
root = Path(SPECPATH)
a = Analysis([str(root / 'okdev_maintenance.py')], pathex=[str(root)],
             binaries=[], datas=[(str(root / 'assets/7zip'), 'assets/7zip')],
             hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='OKDEV_Maintenance',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
          console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True,
               name='OKDEV_Maintenance')
