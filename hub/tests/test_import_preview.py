from unittest.mock import patch

from hub import library
from hub.desktop import Api
from hub.tests.test_library import LibraryFixture


class ImportPreviewTests(LibraryFixture):
    def api(self):
        api = Api()
        api._selected = self.archive()
        return api

    def test_new_import_preview_never_installs_and_applies_guarded_revision(self):
        api = self.api()
        fields = self.item()
        preview = api.preview_import(fields)
        self.assertTrue(preview['ok'])
        self.assertIsNone(preview['result']['existing'])
        self.assertEqual(library.installed(), {})
        self.assertTrue(api.import_mod(fields, preview['result']['revision'])['ok'])
        self.assertIn('sample', library.installed())

    def test_replacement_preview_shows_versions_and_preserves_old_payload(self):
        api = self.api()
        old = library.import_archive(api._selected, self.item())
        library.enable('sample', True)
        fields = dict(self.item(), version='2.0.0')
        preview = api.preview_import(fields)['result']
        self.assertEqual(preview['existing'], {'name':'Test mod', 'version':'1.0.0', 'enabled':True})
        self.assertEqual(preview['version'], '2.0.0')
        self.assertEqual(library.installed()['sample']['version'], '1.0.0')
        self.assertTrue(library.mod_folder(old).exists())
        self.assertTrue(api.import_mod(fields, preview['revision'])['ok'])
        self.assertEqual(library.installed()['sample']['version'], '2.0.0')
        self.assertTrue(library.installed()['sample']['enabled'])
        self.assertEqual(library.removed()[0]['version'], '1.0.0')

    def test_concurrent_new_install_invalidates_empty_preview(self):
        api = self.api()
        fields = self.item()
        revision = api.preview_import(fields)['result']['revision']
        library.import_archive(api._selected, fields)
        before = (library.root() / 'installed.json').read_bytes()
        with patch('injection.mods.storage.ModStorageService') as storage:
            result = api.import_mod(fields, revision)
            self.assertFalse(result['ok'])
            self.assertIn('önizlemeden sonra', result['error'])
            storage.assert_not_called()
        self.assertEqual((library.root() / 'installed.json').read_bytes(), before)
        self.assertEqual(library.removed(), [])

    def test_selection_change_invalidates_replacement_preview(self):
        api = self.api()
        library.import_archive(api._selected, self.item())
        fields = dict(self.item(), version='2.0.0')
        revision = api.preview_import(fields)['result']['revision']
        library.enable('sample', True)
        result = api.import_mod(fields, revision)
        self.assertFalse(result['ok'])
        self.assertEqual(library.installed()['sample']['version'], '1.0.0')
        self.assertTrue(library.installed()['sample']['enabled'])
        self.assertEqual(library.removed(), [])

    def test_unrelated_mod_change_does_not_invalidate_reviewed_item(self):
        api = self.api()
        fields = self.item()
        revision = api.preview_import(fields)['result']['revision']
        library.import_archive(api._selected, self.item('other'))
        self.assertTrue(api.import_mod(fields, revision)['ok'])
        self.assertEqual(set(library.installed()), {'sample', 'other'})

    def test_preview_refuses_reusing_id_for_another_category(self):
        api = self.api()
        library.import_archive(api._selected, self.item())
        api._selected = self.archive('hud.fantome', {'WAD/UI.wad.client':b'fixture'})
        fields = dict(self.item(), category='ui', champion='', champion_id=None)
        result = api.preview_import(fields)
        self.assertFalse(result['ok'])
        self.assertIn('farklı bir mod kimliği', result['error'])
        self.assertEqual(library.installed()['sample']['champion_id'], 103)
