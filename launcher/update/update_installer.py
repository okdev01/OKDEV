"""Validate OKDEV packages and launch the transactional update helper."""
from pathlib import Path, PurePosixPath
import json
import os
import shutil
import stat
import subprocess
import zipfile


class UpdateInstaller:
    def extract_update(self, zip_path, staging_dir, progress_callback, status_callback):
        try:
            staging_dir = Path(staging_dir)
            if staging_dir.name != 'staging' or staging_dir.parent.resolve() != Path(zip_path).parent.resolve():
                raise ValueError('Invalid update staging location')
            if staging_dir.is_symlink() or staging_dir.is_junction():
                raise ValueError('Linked staging directory')
            if staging_dir.exists():
                shutil.rmtree(staging_dir)
            staging_dir.mkdir(parents=True)
            with zipfile.ZipFile(zip_path) as archive:
                members = archive.infolist()
                for item in members:
                    p = PurePosixPath(item.filename)
                    if (p.is_absolute() or '..' in p.parts or '\\' in item.filename
                            or ':' in item.filename or stat.S_ISLNK(item.external_attr >> 16)
                            or any(part.lower().startswith('ltk_patcher') for part in p.parts)):
                        raise ValueError('Unsafe update archive member')
                archive.extractall(staging_dir)
            manifest = json.loads((staging_dir/'okdev-update.json').read_text(encoding='utf-8'))
            if manifest.get('app') != 'OKDEV' or not (staging_dir/'OKDEV.exe').is_file():
                raise ValueError('Not an OKDEV update')
            progress_callback(60)
            return staging_dir
        except Exception as exc:
            status_callback(f'Update package rejected: {exc}')
            return None

    def prepare_updater_launch(self, extracted_root, install_dir, updates_root, zip_path, staging_dir, status_callback):
        if not (install_dir/'okdev-install.json').is_file():
            status_callback('Install OKDEV with its setup once to enable automatic updates')
            return None
        # The caller has already verified the release archive's SHA-256.
        # Use its helper so future updater fixes apply during this update too.
        helper = extracted_root/'OKDEV-Updater.exe'
        if not helper.is_file():
            helper = install_dir/'OKDEV-Updater.exe'
        if not helper.is_file():
            status_callback('OKDEV update helper missing; reinstall this version')
            return None
        external = updates_root/'OKDEV-Updater.exe'
        shutil.copy2(helper, external)
        return {'helper': external, 'pid': os.getpid(), 'install': install_dir,
                'payload': extracted_root, 'log': updates_root/'updater.log'}

    def launch_updater(self, params, install_dir, updates_root, zip_path, staging_dir, status_callback):
        try:
            subprocess.Popen([str(params['helper']), '--pid', str(params['pid']),
                '--install-dir', str(params['install']), '--staging-dir', str(params['payload']),
                '--log-file', str(params['log'])], close_fds=True, cwd=updates_root,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            return True
        except OSError as exc:
            status_callback(f'Cannot launch OKDEV updater: {exc}')
            return False
