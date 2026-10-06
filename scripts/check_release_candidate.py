"""Verify a locally built candidate without launching any application windows."""
import hashlib
import json
import marshal
import shutil
import subprocess
import sys
import tempfile
import types
import zipfile
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader
from PyInstaller.utils.win32 import winmanifest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from create_update_package import app_version


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def normalized_code(code):
    # PyInstaller rewrites source filenames; compare executable code and its
    # nested functions independently of the developer's absolute build path.
    return code.replace(co_filename='', co_consts=tuple(
        normalized_code(value) if isinstance(value, types.CodeType) else value for value in code.co_consts))


def main():
    version = app_version()
    dist = ROOT / 'dist/OKDEV'
    release = ROOT / 'release'
    checks = []

    def check(condition, name):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    required = ['OKDEV.exe', 'OKDEV-Updater.exe', 'LICENSE-Rose.txt', 'LICENSE-PenguLoader.txt',
                '_internal/hub/web/index.html', '_internal/hub/web/app.js',
                '_internal/hub/web/app.css', '_internal/hub/web/sources.json',
                '_internal/hub/web/guide.js', '_internal/Pengu Loader/plugins/OKDEV-Guide/index.js',
                '_internal/hub/web/champions.json', '_internal/Pengu Loader/core.dll',
                '_internal/injection/tools/mod-tools.exe']
    for name in required:
        check((dist / name).is_file(), 'Required file: ' + name)

    for name in ('index.html', 'app.js', 'app.css', 'guide.js', 'sources.json', 'champions.json'):
        check(digest(dist / '_internal/hub/web' / name) == digest(ROOT / 'hub/web' / name),
              'Current web asset: ' + name)

    archive = CArchiveReader(str(dist / 'OKDEV.exe'))
    entrypoint = marshal.loads(archive.extract('main'))
    check(normalized_code(compile((ROOT / 'main.py').read_bytes(), 'main.py', 'exec', dont_inherit=True)) == normalized_code(entrypoint), 'Current compiled entry point')
    check('--hub-self-check' in entrypoint.co_consts, 'Windowless self-check entry point')
    pyz_name = next(name for name in archive.toc if name.endswith('.pyz'))
    pyz = archive.open_embedded_archive(pyz_name)
    check(version in pyz.extract('config').co_consts, 'Compiled application version')
    dependencies = dict(line.split('==', 1) for line in (ROOT / 'requirements.txt').read_text().splitlines()
                        if '==' in line and not line.startswith('#'))
    for package, module in [('requests', 'requests.__version__'), ('urllib3', 'urllib3._version'), ('Pillow', 'PIL._version')]:
        check(dependencies[package] in pyz.extract(module).co_consts, 'Bundled dependency version: ' + package)
    for module in ('library', 'desktop', 'covers', 'profiles', 'package_info', 'diagnostics', 'integration', 'sources', 'selfcheck', 'guides', 'companion', 'preferences', 'locking', 'downloads', 'selections', 'activity', 'transactions', 'backups', 'errors', 'lifecycle'):
        check('hub.' + module in pyz.toc, 'Bundled module: hub.' + module)
    changed_modules = [name for name in pyz.toc if name.startswith('hub.')]
    changed_modules += ['config', 'utils.core.mod_historic', 'utils.core.data_migration',
        'utils.integration.pengu_loader', 'injection.config.config_manager', 'okdev_install_paths',
        'injection.mods.storage', 'threads.handlers.injection_trigger', 'pengu.communication.message_handler', 'main']
    for module in changed_modules:
        source = ROOT / (module.replace('.', '/') + '.py')
        if module == 'main':
            source = ROOT / 'main/__init__.py'
        expected = compile(source.read_bytes(), str(source), 'exec', dont_inherit=True)
        check(normalized_code(expected) == normalized_code(pyz.extract(module)), 'Current compiled code: ' + module)
    plugin = 'Pengu Loader/plugins/OKDEV-Guide/index.js'
    check(digest(dist / '_internal' / plugin) == digest(ROOT / plugin), 'Current client guide plugin')

    setup = release / f'OKDEV_Setup_{version}.exe'
    update = release / f'OKDEV_Update_{version}.zip'
    for label, executable, entry, source_path in (
            ('setup', setup, 'setup', ROOT / 'setup_app/setup.py'),
            ('updater', dist / 'OKDEV-Updater.exe', 'okdev_update_helper', ROOT / 'okdev_update_helper.py')):
        packed = CArchiveReader(str(executable))
        check(normalized_code(compile(source_path.read_bytes(), str(source_path), 'exec', dont_inherit=True))
              == normalized_code(marshal.loads(packed.extract(entry))), label + ': current compiled entry point')
        embedded = packed.open_embedded_archive(next(name for name in packed.toc if name.endswith('.pyz')))
        for module in ('okdev_install_transaction', 'hub.locking', 'utils.core.atomic_file'):
            source = ROOT / (module.replace('.', '/') + '.py')
            check(module in embedded.toc, label + ': bundled transaction module ' + module)
            check(normalized_code(compile(source.read_bytes(), str(source), 'exec', dont_inherit=True))
                  == normalized_code(embedded.extract(module)), label + ': current compiled module ' + module)
    check(digest(setup) == setup.with_suffix('.sha256.txt').read_text().split()[0], 'Installer SHA-256')
    check(digest(update) == update.with_suffix('.zip.sha256').read_text().split()[0], 'Update SHA-256')
    file_counts = {}
    forbidden = {'config.ini', 'historic.json', 'mod_historic.json', 'party_sessions.json', 'party_keys.json',
                 'installed.json', 'settings.json', 'profiles.json', 'analytics_install_id.txt', 'mods_map.json',
                 'downloads.json', 'activity.json', 'selection-undo.json', 'shutdown.json'}
    for label, path in [('installer_payload', ROOT / 'setup_app/payload.zip'), ('update', update)]:
        with zipfile.ZipFile(path) as bundle:
            names = bundle.namelist()
            check(bundle.testzip() is None, label + ': archive CRC')
            check(set(required).issubset(names), label + ': required files')
            check(not any(Path(name).name.lower() in forbidden or name.lower().endswith(('.fantome', '.modpkg', '.log'))
                          or 'ltk_patcher' in name.lower() for name in names), label + ': no user data or third-party mod packages')
            for name in names:
                if name == 'okdev-update.json':
                    check(json.loads(bundle.read(name)) == {'app': 'OKDEV', 'version': version}, 'Update manifest')
                    continue
                check(hashlib.sha256(bundle.read(name)).hexdigest() == digest(dist / name), label + ': matching file ' + name)
            file_counts[label] = len(names)

    backend_report = ROOT / 'build/hub-backend-frozen-check.json'
    # The shipped game client requests elevation. Exercise the same bundled
    # Python code in a temporary, non-elevated copy so QA never shows UAC.
    with tempfile.NamedTemporaryFile(prefix='OKDEV-BackendCheck-', suffix='.exe', dir=dist, delete=False) as stream:
        test_exe = Path(stream.name)
    try:
        shutil.copy2(dist / 'OKDEV.exe', test_exe)
        manifest = winmanifest.read_manifest_from_executable(str(test_exe))
        manifest = winmanifest.create_application_manifest(manifest, uac_admin=False, uac_uiaccess=False)
        winmanifest.write_manifest_to_executable(str(test_exe), manifest)
        # Windows resource updates remove the appended PyInstaller payload.
        # Reattach the unchanged archive, then compare both executable entries.
        with (dist / 'OKDEV.exe').open('rb') as original, test_exe.open('ab') as target:
            original.seek(archive._start_offset)
            shutil.copyfileobj(original, target)
        test_archive = CArchiveReader(str(test_exe))
        check(test_archive.extract('main') == archive.extract('main'), 'Test copy preserves entry point')
        check(test_archive.extract(pyz_name) == archive.extract(pyz_name), 'Test copy preserves bundled Python code')
        subprocess.run([str(test_exe), '--hub-self-check', str(backend_report)], check=True, timeout=45,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                       | getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0))
        if '--with-ui' in sys.argv:
            ui_report = ROOT / 'build/hub-frozen-ui-check.json'
            subprocess.run([str(test_exe), '--hub', '--hub-smoke', str(ui_report)], check=True, timeout=60,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            check(json.loads(ui_report.read_text(encoding='utf-8')).get('ok') is True, 'Packaged WebView2 UI and Python bridge')
    finally:
        test_exe.unlink(missing_ok=True)
    backend = json.loads(backend_report.read_text(encoding='utf-8'))
    check(backend.get('ok') is True and backend.get('version') == version, 'Packaged backend self-check')

    result = {'ok': True, 'version': version, 'check_count': len(checks), 'file_counts': file_counts,
              'installer_sha256': digest(setup), 'update_sha256': digest(update),
              'backend_checks': len(backend['checks']),
              'backend_execution': 'Temporary non-elevated copy; shipped EXE remains unchanged',
              'ui_checked': '--with-ui' in sys.argv,
              'note': 'Package and isolated backend verification; optional isolated WebView2 window. No game interaction.'}
    target = ROOT / 'build/release-candidate-check.json'
    target.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
