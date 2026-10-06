import warnings
import zipfile

from hub import library
from hub.tests.test_library import LibraryFixture


class ArchiveNameTests(LibraryFixture):
    def make_entries(self, names):
        path = self.root / 'names.fantome'
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(path, 'w') as archive:
                for name in names:
                    archive.writestr(name, b'fixture')
        return path

    def test_windows_renaming_and_device_paths_are_rejected_before_import(self):
        for name in ('WAD/CON.bin', 'WAD/AUX', 'WAD/LPT1.txt', 'WAD/test.',
                     'WAD/test ', 'WAD/a?.bin', 'WAD/a|b.bin', 'WAD/a<b.bin',
                     'WAD/./file.bin', 'WAD//file.bin', 'WAD/a\x01.bin'):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, 'Windows'):
                    library.import_archive(self.make_entries([name]), self.item())
                self.assertEqual(library.installed(), {})
        self.assertFalse((self.root / 'mods').exists())

    def test_duplicate_files_and_file_directory_collisions_are_rejected(self):
        for names in (['WAD/a.bin', 'WAD/a.bin'], ['WAD/A.bin', 'wad/a.BIN'],
                      ['WAD/a', 'WAD/a/b.bin'], ['WAD/a/b.bin', 'wad/A'],
                      ['WAD/a/', 'WAD/A'], ['WAD/a', 'WAD/a/']):
            with self.subTest(names=names):
                with self.assertRaisesRegex(ValueError, 'çakışan'):
                    library.validate_archive(self.make_entries(names))

    def test_unicode_percent_and_shared_directory_entries_remain_valid(self):
        package = self.make_entries(['WAD/', 'wad/', 'WAD/测试-Çağrı%100.bin',
                                     'WAD/nested/', 'WAD/nested/Игрок.bin'])
        library.validate_archive(package)


if __name__ == '__main__':
    import unittest
    unittest.main()
