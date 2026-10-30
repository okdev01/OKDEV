"""Second audit fixes: integrated choices, migration, failure recovery and profiles."""
import os
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from hub import library, profiles, client_sync, selections, backups
from hub.tests.test_library import LibraryFixture
from injection.mods.storage import ModStorageService
from utils.core import historic, mod_historic


class Audit2Regressions(LibraryFixture):
    def test_restart_helper_preserves_unicode_percent_and_quotes_without_cmd(self):
        import ast
        import base64
        import sys
        root = Path(__file__).resolve().parents[1]
        source = root / 'main/__init__.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_schedule_restart')
        namespace = dict(Path=Path, sys=SimpleNamespace(executable=str(self.root / "Özel %PATH% O'Neil" / 'OKDEV.exe'), frozen=True), log=Mock(), __file__=str(source))
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(source), 'exec'), namespace)
        with patch('subprocess.Popen') as launch:
            self.assertTrue(namespace['_schedule_restart']())
        args = launch.call_args.args[0]
        self.assertEqual(args[1:6], ['-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-EncodedCommand'])
        script = base64.b64decode(args[-1]).decode('utf-16-le')
        self.assertIn("Özel %PATH% O''Neil", script)
        self.assertIn('WaitForExit()', script)
        self.assertIn('$launch.UseShellExecute = $false', script)

    def test_cache_quota_retains_active_junction_and_unrelated_folders(self):
        from utils.core.junction import prune_extraction_cache, create_junction, safe_remove_entry
        cache, staging = self.root / 'cache', self.root / 'staging'
        cache.mkdir()
        staging.mkdir()
        active, retired, unrelated = cache / ('a' * 24), cache / ('b' * 24), cache / 'user-folder'
        for folder in (active, retired, unrelated):
            folder.mkdir()
            (folder / 'file').write_bytes(b'data')
        dest = staging / 'active'
        create_junction(active, dest)
        try:
            prune_extraction_cache(cache, staging, max_bytes=0, max_entries=0)
            self.assertTrue(active.exists())
            self.assertTrue((dest / 'file').exists())
            self.assertFalse(retired.exists())
            self.assertTrue(unrelated.exists())
        finally:
            safe_remove_entry(dest, strict=True)

    def client_mod(self, **kwargs):
        return library.import_client_archive(ModStorageService(), self.archive(), champion_id=103, targets=[103001, 103002], **kwargs)

    def test_disabled_client_skin_never_reaches_custom_injection(self):
        from state import SharedState
        from threads.handlers.injection_trigger import InjectionTrigger
        item = self.client_mod()
        client_sync.select('skins', [item['relative_path']], champion_id=103, skin_id=103001)
        state = SharedState()
        state.locked_champ_id = 103
        state.last_hovered_skin_id = state.selected_skin_id = 103001
        state.owned_skin_ids = {103001}
        state.selected_custom_mod = dict(champion_id=103, skin_id=103001, target_skin_ids=[103001, 103002],
            mod_name=item['folder_name'], mod_folder_name=item['folder_name'], mod_path=str(library.mod_folder(item)), relative_path=item['relative_path'])
        library.enable(item['id'], False)
        trigger = InjectionTrigger(Mock(), state, Mock())
        trigger._inject_custom_mod = Mock()
        trigger._force_owned_skin = Mock()
        trigger.trigger_injection('skin_103001', 1, 'Ahri')
        trigger._inject_custom_mod.assert_not_called()
        self.assertIsNone(state.selected_custom_mod)

    def test_client_selection_adopts_legacy_map_before_hub_opens(self):
        from hub.integration import apply_category_selections
        service = ModStorageService()
        folder, name = service.import_category_mod_file('maps', self.archive())
        relative = folder.relative_to(service.mods_root).as_posix()
        client_sync.select('maps', [relative])
        state = SimpleNamespace(selected_map_mod=dict(mod_path=str(folder), relative_path=relative))
        client_sync.reconcile(service)
        apply_category_selections(state)
        self.assertEqual(state.selected_map_mod['relative_path'], relative)

    def test_legacy_archive_can_be_removed_exported_restored_and_enabled(self):
        service = ModStorageService()
        parent = service.get_champion_dir(103)
        parent.mkdir(parents=True)
        source = self.archive()
        target = parent / 'legacy.fantome'
        target.write_bytes(source.read_bytes())
        service.set_champion_target_ids(103, [103001], mod_name='legacy')
        self.assertTrue(library.remove_client_mod(service, champion_id=103, mod_name='legacy', relative_path=target.relative_to(service.mods_root).as_posix()))
        self.assertFalse(target.exists())
        backup = library.removed()[0]['backup_id']
        self.assertEqual(backups.inspect(backup)['files'], 1)
        with tempfile.TemporaryDirectory() as output:
            export = Path(output) / 'export.zip'
            backups.export(backup, export)
            library.validate_archive(export)
        restored = library.restore(backup)
        self.assertEqual(target.read_bytes(), source.read_bytes())
        library.enable(restored['id'], True)
        self.assertEqual(library.active_mod(103)['skin_id'], 103001)
        self.assertEqual(service.list_mods_for_champion(103)[0].target_skin_ids, (103001,))

    def test_legacy_archive_removal_recovers_after_interrupted_index_write(self):
        service = ModStorageService()
        parent = service.get_champion_dir(103)
        parent.mkdir(parents=True)
        target = parent / 'legacy.fantome'
        target.write_bytes(self.archive().read_bytes())
        service.set_champion_target_ids(103, [103001], mod_name='legacy')
        client_sync.reconcile(service)
        item = next(iter(library.installed().values()))
        class PowerLoss(BaseException):
            pass
        original = library.write_json
        def write(path, data):
            if path.name == 'installed.json':
                raise PowerLoss()
            return original(path, data)
        with patch.object(library, 'write_json', side_effect=write), self.assertRaises(PowerLoss):
            library.remove(item['id'])
        self.assertFalse(target.exists())
        with library.mutation_lock():
            pass
        self.assertTrue(target.exists())
        self.assertIn(item['id'], library.installed())

    def test_legacy_archive_alias_without_relative_path_updates_hub(self):
        service = ModStorageService()
        parent = service.get_champion_dir(103)
        parent.mkdir(parents=True)
        (parent / 'legacy.fantome').write_bytes(self.archive().read_bytes())
        service.set_champion_target_ids(103, [103001], mod_name='legacy')
        client_sync.rename(service, name='Legacy alias', champion_id=103, mod_name='legacy')
        self.assertEqual(next(iter(library.installed().values()))['name'], 'Legacy alias')

    def test_client_rename_updates_shared_name_for_skin_and_category(self):
        service = ModStorageService()
        item = self.client_mod()
        client_sync.rename(service, name='Renamed', champion_id=103, mod_name=item['folder_name'], relative_path=item['relative_path'])
        self.assertEqual(library.installed()[item['id']]['name'], 'Renamed')
        self.assertEqual(service.list_mods_for_champion(103)[0].display_name, 'Renamed')
        category = library.import_client_archive(service, self.archive('map.zip'), category='maps')
        client_sync.rename(service, name='Map alias', category='maps', mod_name=category['folder_name'])
        self.assertEqual(library.installed()[category['id']]['name'], 'Map alias')

    def test_failed_rename_restores_manifest_alias(self):
        service = ModStorageService()
        item = self.client_mod()
        original = (service.get_champion_dir(103) / service.TARGET_METADATA).read_bytes()
        original_write = library.write_json
        def write(path, data):
            if path.name == 'installed.json':
                raise PermissionError('locked')
            return original_write(path, data)
        with patch.object(library, 'write_json', side_effect=write), self.assertRaises(PermissionError):
            client_sync.rename(service, name='Changed', champion_id=103, mod_name=item['folder_name'], relative_path=item['relative_path'])
        self.assertEqual((service.get_champion_dir(103) / service.TARGET_METADATA).read_bytes(), original)

    def test_portable_profile_matches_reimported_local_package_and_target(self):
        source = self.archive()
        service = ModStorageService()
        first = library.import_client_archive(service, source, champion_id=103, targets=[103001, 103002])
        client_sync.select('skins', [first['relative_path']], champion_id=103, skin_id=103002)
        document = profiles.export_profile(profiles.save('Portable'))
        library.remove(first['id'])
        second = library.import_client_archive(service, source, champion_id=103, targets=[103001, 103002])
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(profiles.inspect_portable(document)['missing'], 0)
        imported = profiles.import_profile(document)
        profiles.apply(imported['id'])
        self.assertEqual(library.active_mod(103)['relative_path'], second['relative_path'])
        self.assertEqual(library.active_mod(103)['skin_id'], 103002)

    def test_ambiguous_package_match_is_not_guessed(self):
        first = self.client_mod()
        library.enable(first['id'], True)
        document = profiles.export_profile(profiles.save('Ambiguous'))
        library.remove(first['id'])
        source = self.archive()
        for unused in range(2):
            library.import_client_archive(ModStorageService(), source, champion_id=103, targets=[103001, 103002])
        # Ensure the fixture uses exactly the same bytes as the exported archive.
        document['mods'][0]['package_sha256'] = next(iter(library.installed().values()))['package_sha256']
        self.assertEqual(profiles.inspect_portable(document)['missing'], 1)

    def test_preexisting_mod_without_package_hash_exports_portable_identity(self):
        source = self.archive()
        service = ModStorageService()
        folder, manifest, name = service.import_mod_file(103, source, [103001])
        client_sync.reconcile(service)
        old = next(iter(library.installed().values()))
        self.assertNotIn('package_sha256', old)
        library.enable(old['id'], True)
        document = profiles.export_profile(profiles.save('Legacy portable'))
        self.assertIn('content_sha256', document['mods'][0])
        library.remove(old['id'])
        new = library.import_client_archive(service, source, champion_id=103, targets=[103001])
        preview = profiles.inspect_portable(document)
        self.assertEqual(preview['missing'], 0)
        self.assertEqual(preview['mods'][0]['id'], new['id'])

    def test_profile_target_only_change_has_preview_and_undo(self):
        item = self.client_mod()
        client_sync.select('skins', [item['relative_path']], champion_id=103, skin_id=103001)
        profile = profiles.save('First target')
        client_sync.select('skins', [item['relative_path']], champion_id=103, skin_id=103002)
        stored = profiles.list_profiles()[profile]
        plan = selections.preview(stored['mods'], 'replace', stored['targets'])
        self.assertTrue(plan['changed'])
        self.assertEqual(len(plan['target_changes']), 1)
        profiles.apply(profile)
        self.assertEqual(library.active_mod(103)['skin_id'], 103001)
        self.assertTrue(selections.undo_status()['available'])
        selections.undo()
        self.assertEqual(library.active_mod(103)['skin_id'], 103002)
        self.assertFalse(selections.undo_status()['available'])

    def test_target_change_invalidates_outstanding_selection_preview(self):
        item = self.client_mod()
        client_sync.select('skins', [item['relative_path']], champion_id=103, skin_id=103001)
        plan = selections.preview([item['id']], 'disable')
        client_sync.select('skins', [item['relative_path']], champion_id=103, skin_id=103002)
        with self.assertRaises(ValueError):
            selections.apply([item['id']], 'disable', plan['revision'])

    def test_partial_copy_raises_and_never_leaves_ready_destination(self):
        from utils.core.junction import link_or_extract
        source, dest = self.root / 'source', self.root / 'dest'
        source.mkdir()
        (source / 'one').write_bytes(b'one')
        (source / 'two').write_bytes(b'two')
        def partial(source, target, **kwargs):
            (target / 'one').write_bytes(b'one')
            raise OSError('disk full')
        with patch('_winapi.CreateJunction', side_effect=OSError('unavailable')), patch('utils.core.junction.shutil.copytree', side_effect=partial):
            with self.assertRaises(OSError):
                link_or_extract(source, dest, self.root / 'cache')
        self.assertFalse(dest.exists())
        self.assertFalse(list(self.root.glob('.copy-*')))

    def test_full_zip_failure_retains_working_old_file_and_reports_failure(self):
        from utils.download.repo_downloader import RepoDownloader
        skins = self.root / 'skins'
        skins.mkdir()
        old = skins / 'old.fantome'
        old.write_bytes(b'working')
        repository = self.archive('repository.zip', {'LeagueSkins-main/skins/new.fantome': b'new'})
        downloader = RepoDownloader(skins)
        with patch('utils.download.repo_downloader.atomic_write', side_effect=OSError('disk full')):
            self.assertFalse(downloader.extract_skins_from_zip(repository))
        self.assertEqual(old.read_bytes(), b'working')
        self.assertFalse((skins / 'new.fantome').exists())
        self.assertEqual(downloader.last_extraction_failures, 1)

    def test_archive_replacement_with_same_stat_gets_new_content(self):
        from utils.core.junction import _get_or_extract_to_cache
        source = self.archive(files={'WAD/Ahri.wad.client': b'AAAA'})
        before = source.stat()
        first = _get_or_extract_to_cache(source, source.stem, self.root / 'cache')
        self.archive(files={'WAD/Ahri.wad.client': b'BBBB'})
        os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
        second = _get_or_extract_to_cache(source, source.stem, self.root / 'cache')
        self.assertNotEqual(first, second)
        self.assertEqual((first / 'WAD/Ahri.wad.client').read_bytes(), b'AAAA')
        self.assertEqual((second / 'WAD/Ahri.wad.client').read_bytes(), b'BBBB')

    def test_invalid_automation_state_does_not_block_theme_and_is_disabled(self):
        from hub import preferences
        library.write_json(library.root() / 'settings.json', {'auto_pick_enabled': True, 'lane_profiles': None})
        actual = preferences.update({'theme': 'light'})
        self.assertEqual(actual['theme'], 'light')
        self.assertFalse(actual['auto_pick_enabled'])
        self.assertTrue(preferences.valid('lane_profiles', actual['lane_profiles']))

    def test_failed_history_clear_aborts_disable(self):
        item = self.client_mod()
        library.enable(item['id'], True)
        historic.write_historic_entry(103, 'path:' + item['relative_path'])
        with patch.object(historic, '_write_json', side_effect=PermissionError('locked')), self.assertRaises(PermissionError):
            library.enable(item['id'], False)
        self.assertTrue(library.installed()[item['id']]['enabled'])

    def test_clear_holds_history_lock_until_target_is_cleared(self):
        historic.write_historic_selection(103, 'path:old', 103001)
        started, finished = threading.Event(), threading.Event()
        errors = []
        def writer():
            started.set()
            try:
                historic.write_historic_selection(103, 'path:new', 103002)
            except Exception as exc:
                errors.append(exc)
            finally:
                finished.set()
        thread = threading.Thread(target=writer)
        original = historic.clear_historic_target
        def clear_target(champion):
            thread.start()
            self.assertTrue(started.wait(2))
            self.assertFalse(finished.wait(.1), 'New writer must wait for the whole clear operation')
            original(champion)
        with patch.object(historic, 'clear_historic_target', side_effect=clear_target):
            historic.clear_historic_entry(103)
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(historic.get_historic_skin_for_champion(103), 'path:new')
        self.assertEqual(historic.get_historic_target_for_champion(103), 103002)

    def test_client_rejects_readme_only_package_without_installing(self):
        with self.assertRaises(ValueError):
            library.import_client_archive(ModStorageService(), self.archive(files={'readme.txt': b'text'}), champion_id=103, targets=[103000])
        self.assertEqual(library.installed(), {})

    def test_migration_retains_saved_target_and_alias(self):
        service = ModStorageService()
        folder, manifest, name = service.import_mod_file(103, self.archive(), [103001, 103002])
        service.set_champion_mod_display_name(103, 'My alias', mod_name=name)
        historic.write_historic_selection(103, 'path:' + folder.relative_to(service.mods_root).as_posix(), 103002)
        client_sync.reconcile(service)
        self.assertEqual(library.active_mod(103)['skin_id'], 103002)
        self.assertEqual(library.active_mod(103)['display_name'], 'My alias')

    def test_old_history_cannot_override_new_selection_on_list_request(self):
        from pengu.communication.message_handler import MessageHandler
        service = ModStorageService()
        first = library.import_client_archive(service, self.archive('first.zip'), category='maps')
        second = library.import_client_archive(service, self.archive('second.zip'), category='maps')
        mod_historic.write_historic_mod('map', first['relative_path'])
        client_sync.select('maps', [second['relative_path']])
        fake = SimpleNamespace(mod_storage=service, shared_state=SimpleNamespace(selected_map_mod=None), _send_response=Mock())
        fake._auto_select_historic_mod = lambda *args: MessageHandler._auto_select_historic_mod(fake, *args)
        fake._handle_select_map = Mock()
        MessageHandler._handle_request_maps(fake, {})
        fake._handle_select_map.assert_called_once()
        self.assertEqual(fake._handle_select_map.call_args.args[0]['mapId'], second['relative_path'])
        import json
        self.assertEqual(json.loads(fake._send_response.call_args.args[0])['historicMod'], second['relative_path'])
        self.assertFalse(library.installed()[first['id']]['enabled'])
        self.assertTrue(library.installed()[second['id']]['enabled'])
