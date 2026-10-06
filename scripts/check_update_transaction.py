"""Run the shipped updater against an isolated installation and a launch stub.

The full release is extracted by the real launcher. Only its OKDEV.exe is
replaced in staging with a tiny marker writer so no game client is started.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from create_update_package import app_version
from launcher.update.update_installer import UpdateInstaller


def main():
    report = {'ok': False, 'checks': []}
    def check(condition, message):
        assert condition, message
        report['checks'].append(message)
    try:
        with tempfile.TemporaryDirectory(prefix='okdev-update-qa-', dir=ROOT / 'build') as tmp:
            root = Path(tmp).resolve()
            install, updates = root / 'install', root / 'updates'
            install.mkdir(); updates.mkdir()
            package = updates / 'update.zip'
            original = ROOT / 'release' / f'OKDEV_Update_{app_version()}.zip'
            shutil.copy2(original, package)
            check(hashlib.file_digest(package.open('rb'), 'sha256').hexdigest() == original.with_suffix('.zip.sha256').read_text().split()[0], 'Release hash verified')
            messages = []
            installer = UpdateInstaller()
            staging = installer.extract_update(package, updates / 'staging', lambda _: None, messages.append)
            check(staging is not None, 'Real launcher extracted the release')
            # A standalone .NET marker writer replaces ONLY the application's
            # executable in the isolated test payload, never in the release ZIP.
            source = root / 'LaunchStub.cs'
            source.write_text('using System.IO; using System.Reflection; class Stub { static void Main() { File.WriteAllText(Path.Combine(Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location), "launch-marker.txt"), "launched"); } }', encoding='utf-8')
            csc = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
            (staging / 'OKDEV.exe').unlink()
            subprocess.run([str(csc), '/nologo', '/target:winexe', '/out:' + str(staging / 'OKDEV.exe'), str(source)], check=True,
                capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            (install / 'OKDEV.exe').write_bytes(b'old application fixture')
            (install / 'okdev-install.json').write_text(json.dumps({'install_id': 'isolated-fixture', 'version': '1.2.1'}))
            (install / 'config.ini').write_text('preserve-setting=true')
            tools = install / '_internal/injection/tools'; tools.mkdir(parents=True)
            (tools / 'ltk_patcher_host.exe').write_bytes(b'private fixture patcher')
            params = installer.prepare_updater_launch(staging, install, updates, package, staging, messages.append)
            check(params is not None and params['helper'].parent == updates, 'Packaged helper prepared outside installation')
            sleeper = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(1)'], creationflags=subprocess.CREATE_NO_WINDOW)
            params['pid'] = sleeper.pid
            check(installer.launch_updater(params, install, updates, package, staging, messages.append), 'Actual frozen helper launched')
            sleeper.wait(timeout=5)
            deadline = time.monotonic() + 45
            while not (install / 'launch-marker.txt').exists() and time.monotonic() < deadline:
                time.sleep(.2)
            check((install / 'launch-marker.txt').is_file(), 'Updated application relaunch reached marker stub')
            check('Update installed.' in params['log'].read_text(encoding='utf-8'), 'Transaction committed successfully')
            check(json.loads((install / 'okdev-install.json').read_text())['version'] == app_version(), 'Installation metadata advanced to release version')
            check((install / 'config.ini').read_text() == 'preserve-setting=true', 'User configuration preserved')
            check((install / '_internal/injection/tools/ltk_patcher_host.exe').read_bytes() == b'private fixture patcher', 'User-provided patcher preserved')
            backups = list(root.glob('install.backup-*'))
            check(len(backups) == 1 and (backups[0] / 'OKDEV.exe').read_bytes() == b'old application fixture', 'Original installation retained in backup')
            check((install / '_internal/hub/web/app.js').read_bytes() == (ROOT / 'hub/web/app.js').read_bytes(), 'New application UI delivered intact')
            report.update(ok=True, version=app_version(), scope='Actual frozen helper + actual launcher; isolated full payload with application launch stub. No real user installation modified.')
    except Exception as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
    (ROOT / 'build/update-transaction-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
