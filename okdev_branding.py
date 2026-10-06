"""Repair branding left behind by older installations without deleting user data."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import uuid


def retire_legacy_plugins(loader):
    loader = Path(loader).resolve()
    plugins = loader / 'plugins'
    if not plugins.is_dir() or plugins.is_symlink() or plugins.is_junction():
        return []
    moved = []
    for old in plugins.iterdir():
        if not old.name.startswith('ROSE-') or not old.is_dir():
            continue
        replacement = plugins / ('OKDEV-' + old.name[5:])
        if not replacement.is_dir() or old.is_symlink() or old.is_junction():
            continue
        if old.resolve().parent != plugins.resolve():
            raise ValueError('Legacy plugin is outside runtime')
        backup = loader / 'legacy-plugin-backups' / uuid.uuid4().hex
        backup.mkdir(parents=True)
        old.rename(backup / old.name)
        moved.append(old.name)
    return moved


def refresh_shortcut(destination, create=False):
    destination = Path(destination).resolve()
    source = destination / 'icon.ico'
    if not source.is_file():
        return
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
    icon = destination / f'okdev-icon-{digest}.ico'
    if not icon.exists():
        shutil.copy2(source, icon)
    env = os.environ.copy()
    env.update(OKDEV_SETUP_TARGET=str(destination / 'OKDEV.exe'),
               OKDEV_SETUP_WORKDIR=str(destination), OKDEV_SETUP_ICON=str(icon),
               OKDEV_CREATE_SHORTCUT='1' if create else '0')
    script = r'''
$path = Join-Path ([Environment]::GetFolderPath('Desktop')) 'OKDEV.lnk'
if ($env:OKDEV_CREATE_SHORTCUT -eq '1' -or (Test-Path -LiteralPath $path)) {
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($path)
    if ($env:OKDEV_CREATE_SHORTCUT -eq '1' -or $link.TargetPath -eq $env:OKDEV_SETUP_TARGET) {
        $link.TargetPath = $env:OKDEV_SETUP_TARGET
        $link.WorkingDirectory = $env:OKDEV_SETUP_WORKDIR
        $link.IconLocation = $env:OKDEV_SETUP_ICON + ',0'
        $link.Description = 'OKDEV'
        $link.Save()
        Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public class OKDEVShell { [DllImport("shell32.dll")] public static extern void SHChangeNotify(uint e, uint f, IntPtr a, IntPtr b); }'
        [OKDEVShell]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
    }
}
'''
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                   env=env, check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
