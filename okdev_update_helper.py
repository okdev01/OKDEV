"""Standalone transactional updater, copied outside the installation before launch."""
from pathlib import Path
import json
import shutil
import uuid


def wait_for_install_exit(install, timeout=30):
    """Allow launcher/child shutdown to settle before replacing its files."""
    import psutil
    import time
    install = Path(install).resolve()
    deadline = time.monotonic() + timeout
    while True:
        blockers = []
        for process in psutil.process_iter(['name', 'exe']):
            name = (process.info.get('name') or '').lower()
            exe = process.info.get('exe')
            if name in {'leagueclientux.exe', 'leagueclientuxrender.exe', 'league of legends.exe'}:
                raise RuntimeError('Güncellemeden önce League of Legends istemcisini kapatın.')
            if exe and Path(exe).resolve().is_relative_to(install):
                blockers.append(f'{process.info.get("name")} (PID {process.pid})')
        if not blockers:
            return
        if time.monotonic() >= deadline:
            raise RuntimeError('OKDEV sistem tepsisinden tamamen kapatılmalı: ' + ', '.join(blockers))
        time.sleep(.5)

PRESERVED = {'config.ini', 'okdev-install.json', 'datastore', 'config',
             'ltk_patcher_host.exe', 'ltk_patcher_dll.dll'}


def validate_tree(root):
    for item in [root, *root.rglob('*')]:
        if item.is_symlink() or item.is_junction():
            raise ValueError(f'Linked installation file: {item}')


def apply_update(install, payload):
    from okdev_install_transaction import installation_lock, recover
    with installation_lock(install):
        recover(install)
        return _apply_update(install, payload)


def _apply_update(install, payload):
    install, payload = Path(install).absolute(), Path(payload).absolute()
    validate_tree(install)
    validate_tree(payload)
    metadata = json.loads((install/'okdev-install.json').read_text(encoding='utf-8'))
    manifest = json.loads((payload/'okdev-update.json').read_text(encoding='utf-8'))
    if (not metadata.get('install_id') or manifest.get('app') != 'OKDEV'
            or not (payload/'OKDEV.exe').is_file() or not (install/'OKDEV.exe').is_file()):
        raise ValueError('Invalid OKDEV installation or update')
    if payload.is_relative_to(install) or install.is_relative_to(payload):
        raise ValueError('Update payload overlaps installation')
    suffix = uuid.uuid4().hex[:12]
    prepared = install.with_name('.okdev-update-' + suffix)
    backup = install.with_name(install.name + '.backup-' + suffix)
    try:
        shutil.copytree(install, prepared)
        for source in payload.rglob('*'):
            if not source.is_file() or source.name in PRESERVED or source.name == 'okdev-update.json':
                continue
            target = prepared / source.relative_to(payload)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        metadata['version'] = manifest['version']
        from okdev_branding import retire_legacy_plugins
        retire_legacy_plugins(prepared / '_internal/Pengu Loader')
        (prepared/'okdev-install.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        from okdev_install_transaction import commit
        commit(install, prepared, backup)
        return backup
    finally:
        if prepared.exists() and prepared.resolve().parent == install.resolve().parent:
            shutil.rmtree(prepared)


def main():
    import argparse
    import psutil
    import subprocess
    parser = argparse.ArgumentParser()
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--install-dir', type=Path, required=True)
    parser.add_argument('--staging-dir', type=Path, required=True)
    parser.add_argument('--log-file', type=Path, required=True)
    args = parser.parse_args()
    try:
        # An inherited working directory inside the installation locks its rename on Windows.
        import os
        os.chdir(args.log_file.resolve().parent)
        try:
            psutil.Process(args.pid).wait(timeout=90)
        except psutil.NoSuchProcess:
            pass
        wait_for_install_exit(args.install_dir)
        backup = apply_update(args.install_dir, args.staging_dir)
        args.log_file.write_text('Update installed. Backup: '+str(backup), encoding='utf-8')
        from okdev_branding import refresh_shortcut
        try:
            refresh_shortcut(args.install_dir)
        except (OSError, subprocess.SubprocessError):
            pass  # A shortcut failure does not invalidate a committed update.
    except Exception as exc:
        args.log_file.write_text('Update failed; previous installation retained: '+str(exc), encoding='utf-8')
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(exc), 'OKDEV güncelleme tamamlanamadı', 0x10)
    finally:
        if (args.install_dir/'OKDEV.exe').is_file():
            subprocess.Popen([str(args.install_dir/'OKDEV.exe')], cwd=args.install_dir)


if __name__ == '__main__':
    main()
