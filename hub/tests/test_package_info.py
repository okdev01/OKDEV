import json
from hub.package_info import inspect, slug
from hub.tests.test_library import LibraryFixture


class PackageInfoTests(LibraryFixture):
    def test_reads_fantome_info_and_detects_champion(self):
        path = self.archive(files={'Info/info.json': json.dumps({'Name': 'Işık Ahri', 'Version': '1.2.3', 'Author': 'Maker'}),
                                   'WAD/Ahri.wad.client': b'fixture'})
        info = inspect(path)['suggested']
        self.assertEqual(info['champion_id'], 103)
        self.assertEqual(info['id'], 'isik-ahri')
        self.assertEqual(info['version'], '1.2.3')
        self.assertEqual(info['author'], 'Maker')

    def test_oversized_metadata_is_not_read(self):
        path = self.archive(files={'Info/info.json': 'x' * 100000, 'WAD/ui.wad.client': b'fixture'})
        self.assertEqual(inspect(path)['suggested']['name'], 'sample')

    def test_ambiguous_champions_require_manual_selection(self):
        path = self.archive(files={'WAD/Ahri.wad.client': b'a', 'WAD/Lux.wad.client': b'b'})
        self.assertNotIn('champion_id', inspect(path)['suggested'])

    def test_malformed_optional_json_keeps_import_possible(self):
        path = self.archive(files={'Info/info.json': '{bad', 'WAD/Ahri.wad.client': b'a'})
        self.assertTrue(inspect(path)['warning'])

    def test_non_zip_has_readable_error(self):
        path = self.root / 'bad.fantome'
        path.write_bytes(b'not-zip')
        with self.assertRaisesRegex(ValueError, 'paketi değil'):
            inspect(path)

    def test_slug_handles_turkish_and_length(self):
        self.assertEqual(slug('Çığ Özel!'), 'cig-ozel')
        self.assertLessEqual(len(slug('a' * 100)), 64)

    def test_meta_format_and_extracted_wad_directory(self):
        path = self.archive(files={'META/Info.json': json.dumps({'Name': 'Test', 'Version': '16.18.2.85.4133'}),
                                   'WAD/Ahri.wad.client/ASSETS/test.bin': b'fixture'})
        info = inspect(path)['suggested']
        self.assertEqual(info['version'], '16.18.2.85.4133')
        self.assertEqual(info['champion_id'], 103)
