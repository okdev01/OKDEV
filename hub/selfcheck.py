"""Offline packaged-backend check; never starts a window or a game connection."""
import io
import json
import tempfile
import zipfile
from pathlib import Path


def run(report_path):
    from utils.core import paths
    previous = paths._cached_user_data_dir
    previous_migration = paths._migration_checked
    result = {'ok': False, 'checks': [], 'scope': 'Isolated backend only; no windows, network or game interaction.'}
    try:
        with tempfile.TemporaryDirectory(prefix='okdev-backend-check-') as temporary:
            paths._cached_user_data_dir = Path(temporary)
            paths._migration_checked = True
            from PIL import Image
            from config import APP_VERSION
            from . import library, profiles, preferences, guides, companion
            from .desktop import Api, build_html
            from .sources import entries

            def check(condition, name):
                if not condition:
                    raise AssertionError(name)
                result['checks'].append(name)

            check(library.root().is_relative_to(Path(temporary)), 'Isolated user data')
            image = io.BytesIO()
            Image.new('RGB', (24, 24), '#6de5c3').save(image, 'PNG')
            package = Path(temporary) / 'fixture.fantome'
            with zipfile.ZipFile(package, 'w') as archive:
                archive.writestr('WAD/Ahri.wad.client', b'backend fixture, not a playable mod')
                archive.writestr('META/image.png', image.getvalue())
                archive.writestr('META/info.json', json.dumps({'Author': 'Self-check fixture'}))
            fields = {'id': 'fixture', 'name': 'Fixture', 'champion': 'Ahri', 'champion_id': 103,
                      'category': 'skins', 'version': '1.0.0', 'description': 'Isolated test fixture'}
            api = Api()
            api._selected = package
            check(api.import_mod(fields)['ok'], 'Package import')
            check(api.enable('fixture', True)['ok'], 'Enable selection')
            profile = profiles.save('Fixture')
            check(api.enable('fixture', False)['ok'], 'Disable selection')
            profiles.apply(profile)
            check(library.installed()['fixture']['enabled'], 'Profile restores selection')
            snapshot = api.snapshot()
            check('preview_data' not in snapshot['installed']['fixture'], 'Snapshot does not embed unbounded thumbnails')
            check(api.cover_previews(['fixture'])['fixture']['data'].startswith('data:image/jpeg;base64,'), 'Bundled Pillow thumbnail')
            check(api.undo_selection()['ok'], 'Selection undo')
            check(not library.installed()['fixture']['enabled'], 'Undo restored prior selection')
            exported = profiles.export_profile(profile)
            portable_id = profiles.import_profile(exported)['id']
            check(portable_id != profile, 'Portable profile import creates a copy')
            check(len(api.snapshot()['activity']['events']) > 0, 'Local activity history')
            check(api.downloads_status()['active'] == 0, 'Background queue initializes offline')
            check(api.remove('fixture')['ok'], 'Recoverable removal')
            backup = library.removed()[0]['backup_id']
            check(api.inspect_backup(backup)['result']['files'] > 0, 'Backup inspection')
            from . import backups
            with tempfile.TemporaryDirectory(prefix='okdev-export-check-') as export_directory:
                exported_package = Path(export_directory) / 'fixture.fantome'
                backups.export(backup, exported_package)
                library.validate_archive(exported_package)
                check(exported_package.is_file(), 'Portable backup package export')
            check(api.restore(backup)['ok'], 'Restore backup')
            check(not library.installed()['fixture']['enabled'], 'Restored mod stays disabled')
            html = build_html()
            check('/*APP_JS*/' not in html and '/*APP_CSS*/' not in html, 'Bundled web assets')
            check('id="commandSearch"' in html and 'id="loadoutSummary"' in html, '2.0 search and loadout UI')
            check(preferences.get()['data_saver'] is True, 'Offline cover preference defaults on')
            check(len(entries()) >= 32 and all(m.get('sha256') for m in entries()), 'Verified curated source data')
            preferences.update({'theme': 'light', 'mobalytics_enabled': True})
            check(preferences.get()['theme'] == 'light' and preferences.get()['mobalytics_enabled'], 'Shared preferences')
            session = {'localPlayerCellId': 1, 'myTeam': [{'cellId': 1, 'championId': 11, 'assignedPosition': 'jungle'}],
                       'actions': [[{'actorCellId': 1, 'type': 'pick', 'completed': True, 'championId': 11}]]}
            tracker = guides.GuideTracker(clock=lambda: 1000)
            guide, actions = tracker.update('ChampSelect', session, True, preferences.get())
            check(actions == ['show'] and guide['pick']['url'].endswith('/masteryi/build/jungle'), 'Locked champion guide')
            machine = companion.WindowState()
            events = machine.apply({'id':'fixture', 'action':'show', 'pick':guide['pick'], 'created_at':1000}, now=1000)
            check(machine.visible and events[-1][0] == 'show', 'Companion visibility logic')
            profiles.rename(profile, 'Renamed fixture')
            check(profiles.list_profiles()[profile]['name'] == 'Renamed fixture', 'Profile editing')
            library.remove('fixture')
            from injection.mods.storage import ModStorageService
            reimported = library.import_client_archive(ModStorageService(), package, champion_id=103, targets=[103000])
            profiles.apply(portable_id)
            check(library.installed()[reimported['id']]['enabled'], 'Portable profile resolves a later package with a new ID')
            from . import client_sync
            before_revision = api.state_revision()
            client_sync.select('skins', [], champion_id=103)
            check(api.state_revision() != before_revision, 'External selection revision changes')
            check(not library.installed()[reimported['id']]['enabled'], 'Client deselection commits to shared registry')
            check(api.diagnostics()['ok'], 'Local diagnostics')
            check('Sürüm ' in html and APP_VERSION in html, 'Bundled release identity')
            api._downloads().close()
            result.update(ok=True, version=APP_VERSION)
    except Exception as exc:
        result['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        paths._cached_user_data_dir = previous
        paths._migration_checked = previous_migration
        Path(report_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['ok'] else 1
