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
from PyInstaller.utils.win32 import winmanifest, versioninfo

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
    from sync_release_version import synchronize
    synchronize(check=True)
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
    for source in (ROOT / 'hub').glob('*.py'):
        if source.stem != '__init__':
            check('hub.' + source.stem in pyz.toc, 'Current Hub module: ' + source.stem)
    source_hash = hashlib.sha256()
    compiled_module_count = 0
    for module in sorted(pyz.toc):
        source = ROOT / (module.replace('.', '/') + '.py')
        if not source.is_file() or module == 'main':
            source = ROOT / module.replace('.', '/') / '__init__.py'
        if not source.is_file():
            continue  # Third-party dependencies are checked separately.
        expected = compile(source.read_bytes(), str(source), 'exec', dont_inherit=True)
        check(normalized_code(expected) == normalized_code(pyz.extract(module)), 'Current compiled code: ' + module)
        source_hash.update(module.encode('utf-8') + b'\0' + source.read_bytes())
        compiled_module_count += 1
    plugins = ROOT / 'Pengu Loader/plugins'
    for source in plugins.rglob('*'):
        if source.is_file() and source.suffix.lower() in ('.js', '.css', '.json', '.html'):
            relative = source.relative_to(ROOT)
            check((dist / '_internal' / relative).is_file()
                  and digest(dist / '_internal' / relative) == digest(source),
                  'Current client plugin: ' + relative.as_posix())

    setup = release / f'OKDEV_Setup_{version}.exe'
    update = release / f'OKDEV_Update_{version}.zip'
    for executable in (dist / 'OKDEV.exe', dist / 'OKDEV-Updater.exe', setup):
        metadata = versioninfo.read_version_info_from_executable(str(executable))
        check(metadata is not None, executable.name + ': Windows version resource')
        fields = {item.name:item.val for block in metadata.kids if isinstance(block, versioninfo.StringFileInfo)
                  for table in block.kids for item in table.kids}
        check(fields.get('FileVersion') == version and fields.get('ProductVersion') == version,
              executable.name + ': matching Windows file and product version')
        check(fields.get('OriginalFilename') == executable.name, executable.name + ': correct original filename')
    for label, executable, entry, source_path in (
            ('setup', setup, 'setup', ROOT / 'setup_app/setup.py'),
            ('updater', dist / 'OKDEV-Updater.exe', 'okdev_update_helper', ROOT / 'okdev_update_helper.py')):
        packed = CArchiveReader(str(executable))
        check(normalized_code(compile(source_path.read_bytes(), str(source_path), 'exec', dont_inherit=True))
              == normalized_code(marshal.loads(packed.extract(entry))), label + ': current compiled entry point')
        embedded = packed.open_embedded_archive(next(name for name in packed.toc if name.endswith('.pyz')))
        if label == 'updater':
            source = ROOT/'okdev_client_update.py'
            check(normalized_code(compile(source.read_bytes(), str(source), 'exec', dont_inherit=True))
                  == normalized_code(embedded.extract('okdev_client_update')), 'updater: current client pause/resume module')
        if label == 'setup':
            source = ROOT / 'setup_app/installer_ui.py'
            check('installer_ui' in embedded.toc, 'setup: bundled installer interface')
            check(normalized_code(compile(source.read_bytes(), str(source), 'exec', dont_inherit=True))
                  == normalized_code(embedded.extract('installer_ui')), 'setup: current compiled installer interface')
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
    patch_assets = {}
    for manifest_path in sorted((ROOT / 'assets/skin-patches').glob('*/manifest.json')):
        patch_manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        prefix = '_internal/assets/skin-patches/' + manifest_path.parent.name + '/'
        patch_assets.update({prefix + item['path']: item['sha256'] for item in patch_manifest['packages']})
    check(len(patch_assets) == 75, '45 previous and 30 patch 26.22 skin/chroma packages')
    for label, path in [('installer_payload', ROOT / 'setup_app/payload.zip'), ('update', update)]:
        with zipfile.ZipFile(path) as bundle:
            names = bundle.namelist()
            check(bundle.testzip() is None, label + ': archive CRC')
            check(set(required).issubset(names), label + ': required files')
            check(not any(Path(name).name.lower() in forbidden or (name.lower().endswith(('.fantome', '.modpkg', '.log')) and name not in patch_assets)
                          or 'ltk_patcher' in name.lower() for name in names), label + ': no user data or third-party mod packages')
            for name, expected_hash in patch_assets.items():
                check(name in names and hashlib.sha256(bundle.read(name)).hexdigest() == expected_hash,
                      label + ': verified patch asset ' + name)
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
              'compiled_modules_checked': compiled_module_count,
              'compiled_source_sha256': source_hash.hexdigest(), 'app_sha256': digest(dist / 'OKDEV.exe'),
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
