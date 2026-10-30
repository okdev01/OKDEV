"""2.0 cross-surface regressions: persisted intent survives every entry point."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from hub import library, profiles, client_sync
from hub.tests.test_library import LibraryFixture
from injection.mods.storage import ModStorageService


class V2Regressions(LibraryFixture):
    def skin(self):
        return library.import_client_archive(ModStorageService(), self.archive(), champion_id=103, targets=[103001, 103002])

    def test_profile_import_before_package_resolves_after_install_and_restart(self):
        first = self.skin()
        client_sync.select('skins', [first['relative_path']], champion_id=103, skin_id=103002)
        document = profiles.export_profile(profiles.save('Source'))
        library.remove(first['id'])
        imported = profiles.import_profile(document)
        self.assertEqual(imported['missing'], 1)
        second = self.skin()
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(profiles.list_profiles(resolve=True)[imported['id']]['mods'], [second['id']])
        profiles.apply(imported['id'])
        self.assertEqual(library.active_mod(103)['skin_id'], 103002)
        self.assertEqual(profiles.export_profile(imported['id'])['mods'], document['mods'])

    def test_same_legacy_id_different_content_cannot_apply_portable_profile(self):
        service = ModStorageService()
        folder, _, _ = service.import_mod_file(103, self.archive(), [103001])
        client_sync.reconcile(service)
        item = next(iter(library.installed().values()))
        library.enable(item['id'], True)
        document = profiles.export_profile(profiles.save('Original'))
        (folder / 'WAD/Ahri.wad.client').write_bytes(b'different machine content')
        imported = profiles.import_profile(document)
        self.assertEqual(imported['missing'], 1)
        before = library.installed()
        with self.assertRaises(ValueError):
            profiles.apply(imported['id'])
        self.assertEqual(library.installed(), before)

    def test_removed_client_skin_is_rejected_by_history_and_overlay_preflight(self):
        from threads.handlers.injection_trigger import InjectionTrigger
        item = self.skin()
        source = library.mod_folder(item)
        library.remove(item['id'])
        self.assertFalse(client_sync.history_path_allowed(item['relative_path']))
        fake = SimpleNamespace(state=SimpleNamespace(locked_champ_id=103, selected_custom_mod=item),
                               injection_manager=SimpleNamespace(injector=Mock(), _monitor_active=False,
                                                                 resume_game=Mock(), _stop_monitor=Mock()))
        InjectionTrigger._inject_custom_mod(fake, dict(mod_folder_name=item['folder_name'], mod_path=str(source), champion_id=103))
        fake.injection_manager.injector._clean_mods_dir.assert_not_called()
        fake.injection_manager.injector._clean_overlay_dir.assert_not_called()
        self.assertIsNone(fake.state.selected_custom_mod)

    def test_client_effect_delta_preserves_hub_selection_with_stale_client_state(self):
        from pengu.communication.message_handler import MessageHandler
        service = ModStorageService()
        first = library.import_client_archive(service, self.archive('vfx.zip'), category='vfx')
        second = library.import_client_archive(service, self.archive('sfx.zip'), category='sfx')
        library.enable(first['id'], True)
        fake = SimpleNamespace(mod_storage=service, shared_state=SimpleNamespace(selected_other_mods=[]),
                               _send_response=Mock(), injection_manager=SimpleNamespace(injector=SimpleNamespace(mods_dir=self.root / 'staging')))
        with patch('pengu.communication.message_handler.link_or_extract'), patch('pengu.communication.message_handler.get_injection_dir', return_value=self.root):
            MessageHandler._handle_select_other(fake, {'otherId': second['relative_path'], 'otherData': {'path': second['relative_path']}})
        self.assertTrue(all(m['enabled'] for m in library.installed().values()))
        self.assertEqual(len(fake.shared_state.selected_other_mods), 2)
        MessageHandler._handle_select_other(fake, {'action': 'deselect', 'otherId': second['relative_path']})
        self.assertTrue(library.installed()[first['id']]['enabled'])
        self.assertFalse(library.installed()[second['id']]['enabled'])
        self.assertTrue(all(json.loads(call.args[0])['success'] for call in fake._send_response.call_args_list))

    def test_invalid_settings_have_no_partial_writes(self):
        from pengu.communication.message_handler import MessageHandler
        fake = SimpleNamespace(_is_valid_local_league_path=Mock(return_value=False), _send_settings_save_error=Mock())
        with patch('config.set_config_options') as batch, patch('pengu.communication.message_handler.set_config_option') as single:
            MessageHandler._handle_settings_save(fake, {'threshold': 1.75, 'gamePath': 'Z:/not-league'})
        batch.assert_not_called()
        single.assert_not_called()
        fake._send_settings_save_error.assert_called_once()

    def test_settings_disk_failure_rolls_back_autostart_and_reports_failure(self):
        from pengu.communication.message_handler import MessageHandler
        fake = SimpleNamespace(_send_settings_save_error=Mock(), _send_settings_save_success=Mock())
        with patch('config.set_config_options', side_effect=OSError('Disk full')), \
                patch('pengu.communication.message_handler.is_registered_for_autostart', return_value=False), \
                patch('pengu.communication.message_handler.is_admin', return_value=True), \
                patch('pengu.communication.message_handler.register_autostart', return_value=(True, '')) as enable, \
                patch('pengu.communication.message_handler.unregister_autostart', return_value=(True, '')) as rollback:
            MessageHandler._handle_settings_save(fake, {'autostart': True})
        enable.assert_called_once()
        rollback.assert_called_once()
        fake._send_settings_save_success.assert_not_called()
        fake._send_settings_save_error.assert_called_once()

    def test_migration_keeps_authoritative_champion_selection(self):
        from utils.core import historic
        first = self.skin()
        library.enable(first['id'], True)
        service = ModStorageService()
        folder, _, _ = service.import_mod_file(103, self.archive('legacy.zip'), [103001])
        historic.write_historic_entry(103, 'path:' + folder.relative_to(service.mods_root).as_posix())
        client_sync.reconcile(service)
        self.assertEqual([m['id'] for m in library.installed().values() if m['enabled']], [first['id']])
        profiles.apply(profiles.save('Current'))

    def test_readme_only_wad_is_rejected_but_loose_wad_is_accepted(self):
        with self.assertRaises(ValueError):
            library.import_archive(self.archive(files={'WAD/readme.txt': b'hello'}), self.item())
        library.import_archive(self.archive(files={'WAD/Ahri.wad.client/data/file.bin': b'PROP'}), self.item())

    def test_large_export_reimports_via_actual_file_dialog(self):
        from hub.desktop import Api
        data = {}
        for i in range(2000):
            key = 'effect-' + str(i)
            data[key] = dict(id=key, name='A' * 100, category='vfx', champion='', champion_id=None,
                             version='1.0.0', description='', enabled=True, relative_path='vfx/' + key,
                             folder_name=key, package_sha256='a' * 64)
        library.write_json(library.root() / 'installed.json', data)
        document = profiles.export_profile(profiles.save('All'))
        path = self.root / 'profile.json'
        library.write_json(path, document)
        self.assertGreater(path.stat().st_size, 512 * 1024)
        fake = SimpleNamespace(_window=SimpleNamespace(create_file_dialog=lambda *a, **k: [str(path)]), _run=lambda fn: fn())
        preview = Api.choose_profile(fake)
        self.assertEqual(len(preview['mods']), 2000)

    def test_response_distinguishes_committed_target_from_visible_skin(self):
        from pengu.communication.message_handler import MessageHandler
        item = self.skin()
        client_sync.select('skins', [item['relative_path']], champion_id=103, skin_id=103002)
        fake = SimpleNamespace(mod_storage=ModStorageService(), port=12345,
                               _get_compatible_skin_ids=lambda value: {int(value)},
                               _get_entry_target_skin_ids=MessageHandler._get_entry_target_skin_ids,
                               _normalize_mod_identifier=MessageHandler._normalize_mod_identifier,
                               _send_response=Mock())
        MessageHandler._handle_request_skin_mods(fake, {'championId': 103, 'skinId': 103001})
        response = json.loads(fake._send_response.call_args.args[0])
        self.assertTrue(response['selectionAuthoritative'])
        self.assertEqual(response['selection']['skinId'], 103002)
        self.assertEqual(response['skinId'], 103001)

    def test_unicode_cache_hit_and_corrupt_stamp_do_not_replace_live_directory(self):
        from utils.core import junction
        for name in ['şampiyon.fantome', '丁.fantome']:
            source = self.archive(name)
            cache = self.root / 'cache'
            with patch.object(junction, 'extract_mod_archive', wraps=junction.extract_mod_archive) as extract:
                first = junction._get_or_extract_to_cache(source, source.stem, cache)
                self.assertEqual(first, junction._get_or_extract_to_cache(source, source.stem, cache))
                (cache / (first.name + '.mtime')).write_bytes(b'\xffbroken')
                self.assertEqual(first, junction._get_or_extract_to_cache(source, source.stem, cache))
                self.assertEqual(extract.call_count, 1)
                self.assertTrue((first / 'WAD/Ahri.wad.client').is_file())

    def test_modpkg_desktop_metadata_and_actual_import(self):
        from utils.tests.test_modpkg import REFERENCE_PACKAGE
        from hub.package_info import inspect
        path = self.root / 'package.modpkg'
        path.write_bytes(REFERENCE_PACKAGE)
        info = inspect(path)
        self.assertEqual(info['suggested']['champion_id'], 266)
        self.assertEqual(info['suggested']['name'], 'Example')
        self.assertEqual(info['suggested']['author'], 'Crauzer')
        item = library.import_archive(path, info['suggested'])
        self.assertTrue((library.mod_folder(item) / 'WAD/aatrox.wad.client/35fa033498b5c335.bin').is_file())

    def test_revision_detects_same_version_package_replacement(self):
        from hub import selections
        library.import_archive(self.archive(), self.item())
        plan = selections.preview(['sample'], 'enable')
        library.import_archive(self.archive(files={'WAD/Ahri.wad.client': b'replacement'}), self.item())
        with self.assertRaises(ValueError):
            selections.apply(['sample'], 'enable', expected_revision=plan['revision'])
        self.assertFalse(library.installed()['sample']['enabled'])

    def test_existing_migration_conflicts_are_repaired_without_losing_files(self):
        first = self.skin()
        second = library.import_client_archive(ModStorageService(), self.archive('second.fantome'), champion_id=103, targets=[103001])
        data = library.installed()
        for index, item in enumerate([first, second]):
            data[item['id']]['enabled'] = True
            data[item['id']]['installed_at'] = index
        library.write_json(library.root() / 'installed.json', data)
        client_sync.reconcile()
        data = library.installed()
        self.assertFalse(data[first['id']]['enabled'])
        self.assertTrue(data[second['id']]['enabled'])
        self.assertTrue(all(library.mod_available(item) for item in data.values()))

    def test_profile_list_hashes_shared_legacy_content_once_per_snapshot(self):
        service = ModStorageService()
        service.import_mod_file(103, self.archive(), [103001])
        client_sync.reconcile(service)
        item = next(iter(library.installed().values()))
        library.enable(item['id'], True)
        document = profiles.export_profile(profiles.save('Original'))
        for _ in range(5):
            profiles.import_profile(document)
        with patch.object(profiles, '_content_identity', wraps=profiles._content_identity) as identity:
            resolved = profiles.list_profiles(resolve=True)
        self.assertEqual(len(resolved), 6)
        self.assertEqual(identity.call_count, 1)

    def test_state_revision_changes_after_external_client_selection(self):
        from hub.desktop import Api
        item = self.skin()
        api = Api()
        before = api.state_revision()
        client_sync.select('skins', [item['relative_path']], champion_id=103, skin_id=103002)
        self.assertNotEqual(api.state_revision(), before)

    def test_non_skin_portable_identity_rejects_invalid_champion(self):
        document = {'type':'okdev-profile', 'schema':2, 'name':'Invalid', 'mods':[
            {'id':'sample','name':'Sample','version':'1.0.0','category':'vfx','champion_id':[], 'package_sha256':'a'*64}]}
        with self.assertRaises(ValueError):
            profiles.import_profile(document)
        self.assertEqual(profiles.list_profiles(), {})

    def test_client_can_deselect_profile_mod_without_in_memory_selection(self):
        from pengu.communication.message_handler import MessageHandler
        item = self.skin()
        library.enable(item['id'], True)
        fake = SimpleNamespace(mod_storage=ModStorageService(), shared_state=SimpleNamespace(selected_custom_mod=None),
                               injection_manager=None, _get_compatible_skin_ids=lambda value:{int(value)},
                               _normalize_mod_identifier=MessageHandler._normalize_mod_identifier,
                               _send_custom_mod_selection_result=Mock())
        MessageHandler._handle_select_skin_mod(fake, {'championId':103,'skinId':103001,'modId':None,'expectedModId':item['relative_path']})
        self.assertFalse(library.installed()[item['id']]['enabled'])
        self.assertTrue(fake._send_custom_mod_selection_result.call_args.kwargs['success'])

    def test_stale_client_deselect_cannot_disable_new_hub_selection(self):
        from pengu.communication.message_handler import MessageHandler
        first = self.skin()
        second = library.import_client_archive(ModStorageService(), self.archive('other.zip'), champion_id=103, targets=[103001])
        library.enable(second['id'], True)
        fake = SimpleNamespace(mod_storage=ModStorageService(), shared_state=SimpleNamespace(selected_custom_mod={'champion_id':103,'relative_path':first['relative_path']}),
                               injection_manager=None, _get_compatible_skin_ids=lambda value:{int(value)},
                               _normalize_mod_identifier=MessageHandler._normalize_mod_identifier,
                               _send_custom_mod_selection_result=Mock())
        MessageHandler._handle_select_skin_mod(fake, {'championId':103,'skinId':103001,'modId':None,'expectedModId':first['relative_path']})
        self.assertTrue(library.installed()[second['id']]['enabled'])
        self.assertFalse(fake._send_custom_mod_selection_result.call_args.kwargs['success'])

    def test_single_category_handlers_acknowledge_commit_failure_and_deselect(self):
        from pengu.communication.message_handler import MessageHandler
        for category, key in [('maps','map'), ('fonts','font'), ('announcers','announcer')]:
            with self.subTest(category=category):
                service = ModStorageService()
                first = library.import_client_archive(service, self.archive(key+'-first.zip'), category=category)
                second = library.import_client_archive(service, self.archive(key+'-second.zip'), category=category)
                library.enable(first['id'], True)
                fake = SimpleNamespace(mod_storage=service, shared_state=SimpleNamespace(), _send_response=Mock(),
                                       injection_manager=SimpleNamespace(injector=SimpleNamespace(mods_dir=self.root/'staging')))
                handler = getattr(MessageHandler, '_handle_select_'+key)
                payload = {key+'Id':second['relative_path'],key+'Data':{'id':second['relative_path']}}
                with patch('pengu.communication.message_handler.link_or_extract', side_effect=OSError('Disk full')):
                    handler(fake,payload)
                self.assertTrue(library.installed()[first['id']]['enabled'])
                self.assertFalse(library.installed()[second['id']]['enabled'])
                reply = json.loads(fake._send_response.call_args.args[0])
                self.assertFalse(reply['success'])
                self.assertEqual(reply['selected'][category],[first['relative_path']])
                with patch('pengu.communication.message_handler.link_or_extract'):
                    handler(fake,payload)
                self.assertTrue(library.installed()[second['id']]['enabled'])
                self.assertFalse(library.installed()[first['id']]['enabled'])
                self.assertTrue(json.loads(fake._send_response.call_args.args[0])['success'])
                handler(fake,{key+'Id':None})
                self.assertFalse(library.installed()[second['id']]['enabled'])
                self.assertIsNone(getattr(fake.shared_state,'selected_'+key+'_mod'))

    def test_bridge_ignores_non_object_json_without_crashing(self):
        from pengu.communication.message_handler import MessageHandler
        fake = SimpleNamespace(_route=Mock(), _run_in_background=Mock())
        for message in ['null','[]','3','"hello"','{}','{"type":[]}']:
            MessageHandler.handle_message(fake,message)
        fake._route.assert_not_called()
        fake._run_in_background.assert_not_called()
