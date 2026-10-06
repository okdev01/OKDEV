import json

from hub import library, profiles
from hub.tests.test_library import LibraryFixture


class PortableProfileTests(LibraryFixture):
    def document(self):
        return {'schema': 1, 'type': 'okdev-profile', 'name': 'Taşınabilir',
                'mods': [{'id': 'sample', 'name': 'Ahri görünümü', 'version': '1.0.0'}]}

    def test_export_contains_references_not_paths_or_packages(self):
        library.import_archive(self.archive(), self.item())
        library.enable('sample', True)
        profile_id = profiles.save('Özel')
        document = profiles.export_profile(profile_id)
        self.assertEqual(document['mods'][0]['id'], 'sample')
        self.assertNotIn('relative_path', json.dumps(document))
        self.assertNotIn(str(self.root), json.dumps(document))
        self.assertEqual(set(document['mods'][0]), {'id', 'name', 'version'})

    def test_import_missing_references_does_not_change_selections(self):
        library.import_archive(self.archive(), self.item('other'))
        library.enable('other', True)
        result = profiles.import_profile(self.document())
        self.assertEqual(result['missing'], 1)
        self.assertEqual(profiles.list_profiles()[result['id']]['mods'], ['sample'])
        self.assertTrue(library.installed()['other']['enabled'])

    def test_conflicting_name_creates_copy_not_overwrite(self):
        first = profiles.import_profile(self.document())
        second = profiles.import_profile(self.document())
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(second['name'], 'Taşınabilir (2)')
        self.assertEqual(len(profiles.list_profiles()), 2)

    def test_preview_reports_missing_files_and_version_mismatch(self):
        library.import_archive(self.archive(), self.item())
        document = self.document()
        document['mods'][0]['version'] = '2.0.0'
        preview = profiles.inspect_portable(document)
        self.assertEqual(preview['different_versions'], 1)
        self.assertEqual(preview['missing'], 0)
        folder = library.mod_folder(library.installed()['sample'])
        folder.rename(folder.with_name('moved'))
        self.assertEqual(profiles.inspect_portable(document)['missing'], 1)

    def test_duplicate_or_invalid_references_are_rejected(self):
        document = self.document()
        document['mods'].append(dict(document['mods'][0]))
        with self.assertRaises(ValueError):
            profiles.import_profile(document)
        document['mods'] = [{'id': '../bad', 'name': 'Bad', 'version': '1.0.0'}]
        with self.assertRaises(ValueError):
            profiles.import_profile(document)
        self.assertEqual(profiles.list_profiles(), {})

    def test_unknown_schema_and_boolean_schema_are_rejected(self):
        for schema in (True, '1', 2, None):
            document = self.document()
            document['schema'] = schema
            with self.assertRaises(ValueError):
                profiles.inspect_portable(document)

    def test_empty_profile_is_portable(self):
        document = self.document()
        document['mods'] = []
        result = profiles.import_profile(document)
        self.assertEqual(profiles.export_profile(result['id']), document)
