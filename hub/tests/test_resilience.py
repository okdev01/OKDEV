import json
from types import SimpleNamespace
from unittest.mock import patch, Mock

import requests

from hub import library
from hub.integration import apply_category_selections
from hub.desktop import Api, build_html
from hub.tests.test_library import LibraryFixture


class ResilienceTests(LibraryFixture):
    def test_corrupt_settings_are_preserved_and_reported(self):
        path = library.root() / 'settings.json'
        for content in ('{bad', '[]', '{"auto_accept":"yes"}', '{"favorites":[null]}'):
            with self.subTest(content=content):
                path.write_text(content)
                self.assertFalse(library.settings()['auto_accept'])
                for action in (lambda: library.set_auto_accept(True), lambda: library.set_favorite('sample', True)):
                    with self.assertRaisesRegex(ValueError, 'korunuyor'):
                        action()
                self.assertEqual(path.read_text(), content)
                self.assertIn('Tercihler', Api().snapshot()['warning'])

    def test_diagnostics_reports_invalid_profiles_and_settings(self):
        from hub.diagnostics import collect
        library.write_json(library.root() / 'profiles.json', {'invalid': {'name': 4}})
        library.write_json(library.root() / 'settings.json', {'auto_accept': 'true'})
        report = {item['name']: item['status'] for item in collect()['checks']}
        self.assertEqual(report['Mod profilleri'], 'warning')
        self.assertEqual(report['Tercihler'], 'warning')

    def test_ritobin_text_with_compiled_sibling_is_game_data(self):
        text = '#PROP_text\ntype: string = "PROP"\nversion: u32 = 3\nlinked: list[string] = {}\nentries: map[hash,embed] = {\n0x123 = SkinData {}\n}'
        path = self.archive(files={'WAD/Ahri.wad.client/skin0.py': text, 'WAD/Ahri.wad.client/skin0.bin': b'PROP'})
        library.validate_archive(path)

    def test_python_script_and_spoofed_ritobin_header_are_rejected(self):
        for text in ('print("no")', '#PROP_text\nimport os\n'):
            path = self.archive(files={'WAD/Ahri.wad.client/skin0.py': text, 'WAD/Ahri.wad.client/skin0.bin': b'PROP'})
            with self.assertRaises(ValueError):
                library.validate_archive(path)

    def test_ritobin_can_omit_empty_dependencies_only_when_binary_confirms(self):
        text = '#PROP_text\ntype: string = "PROP"\nversion: u32 = 3\nentries: map[hash,embed] = {\n0x123 = VfxSystemDefinitionData {}\n}'
        for dependencies in (0, 1):
            binary = b'PROP' + (3).to_bytes(4, 'little') + dependencies.to_bytes(4, 'little')
            path = self.archive(files={'WAD/Ahri.wad.client/vfx.py': text, 'WAD/Ahri.wad.client/vfx.bin': binary})
            if dependencies == 0:
                library.validate_archive(path)
            else:
                with self.assertRaises(ValueError):
                    library.validate_archive(path)

    def test_cdtb_patch_needs_compiled_patch_sibling(self):
        text = '#PROP_text\npatches: map[hash,embed] = {\n"UI/Test" = patch {\npath: string = "Position"\nvalue: vec2 = { 1, 2 }\n}\n}'
        for binary in (b'PTCH', b'PROP', b'not-game-data'):
            path = self.archive(files={'WAD/UI.wad.client/UIBase.cdtb.py': text, 'WAD/UI.wad.client/UIBase': binary})
            if binary == b'PTCH':
                library.validate_archive(path)
            else:
                with self.assertRaises(ValueError):
                    library.validate_archive(path)

    def test_import_preserves_unrecognized_user_folders(self):
        backup = self.root / 'mods/my-personal-backup'
        backup.mkdir(parents=True)
        (backup / 'keep.txt').write_text('user data')
        library.import_archive(self.archive(), self.item())
        self.assertEqual((backup / 'keep.txt').read_text(), 'user data')

    def test_corrupt_cache_offline_still_opens(self):
        path = library.root() / 'catalog.json'
        for data in ('broken-json', '{"schema": 1, "mods": [null]}', '{"schema": 1, "mods": [{"id":3}]}'):
            with self.subTest(data=data):
                path.write_text(data)
                with patch.object(library.requests, 'get', side_effect=requests.ConnectionError()):
                    catalog, warning = library.catalog()
                self.assertEqual(catalog['mods'], [])
                self.assertIn('ulaşılamadı', warning)

    def test_bad_remote_preserves_valid_cached_catalog(self):
        item = self.item(sha256='a' * 64, url='https://github.com/okdev01/OKDEV/releases/download/test/mod.zip')
        cached = {'schema': 1, 'mods': [item]}
        library.write_json(library.root() / 'catalog.json', cached)
        response = Mock(content=b'{}')
        response.iter_content.return_value = [b'{"schema": 1, "mods": [{"id": null}]}']
        with patch.object(library.requests, 'get', return_value=response):
            value, warning = library.catalog(True)
        self.assertEqual(value, cached)
        self.assertTrue(warning)

    def test_favorites_preserve_auto_accept_and_unknown_settings(self):
        library.write_json(library.root() / 'settings.json', {'custom': 42})
        library.set_favorite('sample', True)
        library.set_auto_accept(True)
        library.set_favorite('sample', True)
        self.assertEqual(library.settings(), {'auto_accept': True, 'favorites': ['sample']})
        self.assertEqual(library.read_json(library.root() / 'settings.json', {})['custom'], 42)

    def test_catalog_stream_limit_preserves_cache_and_closes_connection(self):
        cached = {'schema': 1, 'mods': []}
        path = library.root() / 'catalog.json'
        library.write_json(path, cached)
        original = path.read_bytes()
        for declared in ('', str(5 * 1024**2)):
            with self.subTest(content_length=declared):
                response = Mock(status_code=200, headers={'Content-Length': declared})
                response.iter_content.return_value = iter([b'x' * 1024**2] * 5)
                with patch.object(library.requests, 'get', return_value=response):
                    value, warning = library.catalog(True)
                self.assertEqual(value, cached)
                self.assertTrue(warning)
                self.assertEqual(path.read_bytes(), original)
                response.close.assert_called_once()
                if declared:
                    response.iter_content.assert_not_called()

    def test_valid_streamed_catalog_is_cached_after_complete_validation(self):
        response = Mock(status_code=200, headers={})
        response.iter_content.return_value = [b'{"schema":', b'1,"mods":[]}']
        with patch.object(library.requests, 'get', return_value=response):
            value, warning = library.catalog(True)
        self.assertFalse(warning)
        self.assertEqual(value, {'schema': 1, 'mods': []})
        self.assertEqual(library.read_json(library.root() / 'catalog.json', {}), value)
        response.close.assert_called_once()

    def test_boolean_catalog_schema_is_not_a_version(self):
        with self.assertRaises(ValueError):
            library.validate_catalog({'schema': True, 'mods': []})
        library.set_favorite('sample', False)
        self.assertEqual(library.settings()['favorites'], [])

    def test_bad_index_is_preserved_when_importing(self):
        path = library.root() / 'installed.json'
        path.write_text('{bad')
        self.assertEqual(library.installed(), {})
        with self.assertRaisesRegex(ValueError, 'korunuyor'):
            library.import_archive(self.archive(), self.item())
        self.assertEqual(path.read_text(), '{bad')

    def test_missing_mod_cannot_be_enabled(self):
        item = library.import_archive(self.archive(), self.item())
        folder = self.root / 'mods' / item['relative_path']
        folder.rename(folder.with_name('renamed'))
        with self.assertRaisesRegex(ValueError, 'bulunamadı'):
            library.enable('sample', True)
        self.assertFalse(library.installed()['sample']['enabled'])

    def test_update_cannot_reassign_champion_or_category(self):
        library.import_archive(self.archive(), self.item())
        changed = self.item(); changed['champion_id'] = 18
        with self.assertRaises(ValueError):
            library.import_archive(self.archive('next.fantome'), changed)
        self.assertEqual(library.installed()['sample']['champion_id'], 103)

    def test_hud_import_selection_and_disable_after_historic_restore(self):
        item = self.item(); item.update(category='ui', champion_id=None, champion='')
        first = library.import_archive(self.archive(), item)
        item2 = dict(item, id='second')
        second = library.import_archive(self.archive('second.fantome'), item2)
        library.enable('sample', True)
        library.enable('second', True)
        self.assertFalse(library.installed()['sample']['enabled'])
        self.assertIsNone(library.active_mod(103))
        external = {'relative_path': 'others/external', 'mod_name': 'External'}
        state = SimpleNamespace(selected_other_mods=[external, {'relative_path': first['relative_path']}])
        apply_category_selections(state)
        self.assertEqual(len(state.selected_other_mods), 2)
        self.assertEqual(state.selected_other_mods[-1]['relative_path'], second['relative_path'])
        with patch('utils.core.mod_historic.get_user_data_dir', return_value=self.root):
            library.enable('second', False)
        apply_category_selections(state)
        self.assertEqual(state.selected_other_mods, [external])

    def test_invalid_paths_cannot_escape_mods(self):
        for path in ('..', '../outside', '.', ''):
            with self.subTest(path=path), self.assertRaises(ValueError):
                library.mod_folder({'relative_path': path})

    def test_remove_and_restore_preserves_files_but_does_not_enable(self):
        item = library.import_archive(self.archive(), self.item())
        library.enable('sample', True)
        library.remove('sample')
        backups = library.removed()
        self.assertEqual(len(backups), 1)
        restored = library.restore(backups[0]['backup_id'])
        self.assertFalse(restored['enabled'])
        self.assertEqual((library.mod_folder(restored) / 'WAD/Ahri.wad.client').read_bytes(), b'fixture-wad-data')
        self.assertEqual(library.removed(), [])

    def test_remove_write_failure_rolls_back_files(self):
        item = library.import_archive(self.archive(), self.item())
        write = library.write_json
        def fail_index(path, data):
            if path.name == 'installed.json':
                raise OSError('disk error')
            return write(path, data)
        with patch.object(library, 'write_json', side_effect=fail_index), self.assertRaises(OSError):
            library.remove('sample')
        self.assertTrue(library.mod_folder(item).is_dir())
        self.assertIn('sample', library.installed())

    def test_restore_never_overwrites_an_existing_import(self):
        library.import_archive(self.archive(), self.item())
        library.remove('sample')
        backup_id = library.removed()[0]['backup_id']
        library.import_archive(self.archive('new.fantome'), self.item())
        with self.assertRaises(ValueError):
            library.restore(backup_id)
        self.assertEqual(len(library.removed()), 1)

    def test_updating_preserves_old_version_as_recoverable_backup(self):
        old = library.import_archive(self.archive(), self.item())
        library.enable('sample', True)
        new = dict(self.item(), version='2.0.0')
        current = library.import_archive(self.archive('new.fantome'), new)
        self.assertTrue(current['enabled'])
        self.assertFalse(library.mod_folder(old).exists())
        backups = library.removed()
        self.assertEqual(backups[0]['version'], '1.0.0')
        self.assertEqual(backups[0]['reason'], 'update')
        library.remove('sample')
        restored = library.restore(backups[0]['backup_id'])
        self.assertEqual(restored['version'], '1.0.0')

    def test_failed_update_keeps_old_version_and_files(self):
        old = library.import_archive(self.archive(), self.item())
        write = library.write_json
        def fail_index(path, data):
            if path.name == 'installed.json':
                raise OSError('disk error')
            return write(path, data)
        with patch.object(library, 'write_json', side_effect=fail_index), self.assertRaises(OSError):
            library.import_archive(self.archive('new.fantome'), dict(self.item(), version='2.0.0'))
        self.assertTrue(library.mod_folder(old).is_dir())
        self.assertEqual(library.installed()['sample']['version'], '1.0.0')

    def test_tampered_path_cannot_move_a_whole_category(self):
        item = library.import_archive(self.archive(), self.item())
        item['relative_path'] = 'skins'
        library.write_json(library.root() / 'installed.json', {'sample': item})
        with self.assertRaises(ValueError):
            library.remove('sample')
        self.assertTrue((self.root / 'mods/skins').is_dir())

    def test_html_bundles_script_style_and_source_data(self):
        html = build_html()
        self.assertNotIn('/*APP_JS*/', html)
        self.assertNotIn('/*APP_CSS*/', html)
        self.assertIn('Dark Mode HUD', html)
        self.assertIn('pywebviewready', html)

    def test_api_source_import_preserves_credit_and_blocks_republish(self):
        api = Api()
        self.assertTrue(api.prepare_import('rf-dark-mode-hud')['ok'])
        api._selected = self.archive(files={'WAD/UI.wad.client': b'fixture'})
        item = self.item(); item.update(category='ui', champion_id=None, champion='')
        self.assertTrue(api.import_mod(item)['ok'])
        self.assertEqual(library.installed()['sample']['author'], 'p1mek')
        self.assertFalse(api.publish_mod(item, 'unused')['ok'])
        api.prepare_import()
        self.assertIsNone(api._selected)

    def test_import_rejects_wrong_champion_before_extracting(self):
        api = Api()
        api._selected = self.archive()
        fields = dict(self.item(), champion='Lux', champion_id=99)
        result = api.import_mod(fields)
        self.assertFalse(result['ok'])
        self.assertIn('eşleşmiyor', result['error'])
        self.assertEqual(library.installed(), {})

    def test_import_preserves_author_from_package_metadata(self):
        api = Api()
        api._selected = self.archive(files={'META/info.json': json.dumps({'Author': 'Original maker'}), 'WAD/Ahri.wad.client': b'fixture'})
        self.assertTrue(api.import_mod(self.item())['ok'])
        self.assertEqual(library.installed()['sample']['author'], 'Original maker')
