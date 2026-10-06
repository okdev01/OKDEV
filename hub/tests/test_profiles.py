from unittest.mock import patch
from hub import library, profiles
from hub.tests.test_library import LibraryFixture


class ProfileTests(LibraryFixture):
    def test_roundtrip_restores_selection_and_keeps_other_settings(self):
        library.import_archive(self.archive(), self.item())
        library.import_archive(self.archive('second.fantome'), self.item('second'))
        library.enable('sample', True)
        saved = profiles.save('Akşam')
        library.set_favorite('second', True)
        library.enable('second', True)
        profiles.apply(saved)
        self.assertTrue(library.installed()['sample']['enabled'])
        self.assertFalse(library.installed()['second']['enabled'])
        self.assertEqual(library.settings()['favorites'], ['second'])

    def test_missing_mod_blocks_whole_profile_without_disabling_current(self):
        library.import_archive(self.archive(), self.item())
        library.enable('sample', True)
        saved = profiles.save('Birinci')
        library.remove('sample')
        library.import_archive(self.archive('second.fantome'), self.item('second'))
        library.enable('second', True)
        with self.assertRaisesRegex(ValueError, 'eksik'):
            profiles.apply(saved)
        self.assertTrue(library.installed()['second']['enabled'])

    def test_empty_profile_disables_all_mods(self):
        saved = profiles.save('Modsuz')
        library.import_archive(self.archive(), self.item())
        library.enable('sample', True)
        profiles.apply(saved)
        self.assertFalse(library.installed()['sample']['enabled'])

    def test_duplicate_name_does_not_overwrite(self):
        saved = profiles.save('Test')
        with self.assertRaises(ValueError):
            profiles.save('test')
        self.assertEqual(list(profiles.list_profiles()), [saved])

    def test_corrupt_profiles_preserved(self):
        path = library.root() / 'profiles.json'
        path.write_text('corrupt')
        self.assertEqual(profiles.list_profiles(), {})
        with self.assertRaises(ValueError):
            profiles.save('new')
        self.assertEqual(path.read_text(), 'corrupt')

    def test_remove_profile_keeps_mods(self):
        library.import_archive(self.archive(), self.item())
        profile_id = profiles.save('Test')
        profiles.remove(profile_id)
        self.assertEqual(profiles.list_profiles(), {})
        self.assertIn('sample', library.installed())

    def test_rename_preserves_mods_and_blocks_duplicate_name(self):
        library.import_archive(self.archive(), self.item())
        library.enable('sample', True)
        first = profiles.save('First')
        profiles.save('Second')
        profiles.rename(first, 'Renamed')
        self.assertEqual(profiles.list_profiles()[first]['mods'], ['sample'])
        with self.assertRaises(ValueError):
            profiles.rename(first, 'second')
        self.assertEqual(profiles.list_profiles()[first]['name'], 'Renamed')

    def test_update_only_replaces_target_profile_choices(self):
        first, other = profiles.save('First'), profiles.save('Other')
        library.import_archive(self.archive(), self.item())
        library.enable('sample', True)
        profiles.update(first)
        self.assertEqual(profiles.list_profiles()[first]['mods'], ['sample'])
        self.assertEqual(profiles.list_profiles()[other]['mods'], [])
        library.enable('sample', False)
        profiles.apply(first)
        self.assertTrue(library.installed()['sample']['enabled'])
