"""Selection failures preserve committed choices, staging and profile records."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from hub import client_sync, library, profiles
from hub.tests.test_library import LibraryFixture
from injection.mods.storage import ModStorageService
from injection.mods.selection_staging import prepare_selection
from pengu.communication.message_handler import MessageHandler
from utils.core.junction import staging_name


class SelectionAtomicityTests(LibraryFixture):
    def prepare(self):
        self.storage = ModStorageService()
        self.old = library.import_client_archive(self.storage, self.archive('old.zip'), champion_id=103, targets=[103001])
        self.new = library.import_client_archive(self.storage, self.archive('new.zip'), champion_id=103, targets=[103001])
        library.enable(self.old['id'], True)
        self.mods = self.root / 'injection' / 'mods'
        self.mods.mkdir(parents=True)
        self.old_name = staging_name(library.mod_folder(self.old))
        (self.mods / self.old_name).mkdir()
        (self.mods / self.old_name / 'original').write_bytes(b'old staging')
        self.state = SimpleNamespace(selected_custom_mod=dict(self.old, mod_folder_name=self.old_name),
                                     historic_mode_active=True, historic_skin_id=103001)
        self.handler = SimpleNamespace(
            mod_storage=self.storage, shared_state=self.state,
            injection_manager=SimpleNamespace(injector=SimpleNamespace(mods_dir=self.mods)),
            _get_compatible_skin_ids=lambda value: {int(value)},
            _get_entry_target_skin_ids=lambda entry: set(entry.target_skin_ids),
            _mod_matches_identifier=lambda entry, value: entry.path.relative_to(self.storage.mods_root).as_posix() == value,
            _send_custom_mod_selection_result=Mock())
        self.original_state = self.state.selected_custom_mod
        self.index = (library.root() / 'installed.json').read_bytes()

    def select(self, item=None):
        with patch('pengu.communication.message_handler.get_injection_dir', return_value=self.mods.parent):
            MessageHandler._handle_select_skin_mod(self.handler, {
                'championId': 103, 'skinId': 103001, 'modId': (item or self.new)['relative_path']})
        return self.handler._send_custom_mod_selection_result.call_args.kwargs['success']

    def assert_preserved(self):
        self.assertIs(self.state.selected_custom_mod, self.original_state)
        self.assertTrue(self.state.historic_mode_active)
        self.assertEqual((library.root() / 'installed.json').read_bytes(), self.index)
        self.assertEqual((self.mods / self.old_name / 'original').read_bytes(), b'old staging')
        self.assertEqual({p.name for p in self.mods.iterdir()}, {self.old_name})
        self.assertFalse(list(self.mods.parent.glob('.selection-*')))

    def test_failed_preparation_keeps_previous_staging_and_selection(self):
        self.prepare()
        def fail(source, destination, **kwargs):
            destination.mkdir()
            (destination / 'partial').write_bytes(b'partial')
            raise OSError('extraction failed')
        with patch('injection.mods.selection_staging.link_or_extract', side_effect=fail):
            self.assertFalse(self.select())
        self.assert_preserved()

    def test_failed_registry_write_rolls_back_staging_and_memory(self):
        self.prepare()
        write = library.write_json
        def fail(path, data):
            if path.name == 'installed.json':
                raise OSError('disk full')
            return write(path, data)
        with patch.object(library, 'write_json', side_effect=fail):
            self.assertFalse(self.select())
        self.assert_preserved()
        self.assertTrue(library.mod_folder(self.new).exists())

    def test_reselecting_same_mod_failure_restores_existing_destination(self):
        self.prepare()
        with patch('hub.client_sync.select', side_effect=OSError('locked registry')):
            self.assertFalse(self.select(self.old))
        self.assert_preserved()

    def test_failed_destination_rename_restores_previous_staging(self):
        self.prepare()
        rename = Path.rename
        def fail(path, destination):
            if path.name == 'prepared':
                raise PermissionError('destination locked')
            return rename(path, destination)
        with patch.object(Path, 'rename', fail):
            self.assertFalse(self.select())
        self.assert_preserved()

    def test_success_commits_new_choice_and_keeps_other_categories(self):
        self.prepare()
        self.state.selected_map_mod = {'mod_folder_name': 'map'}
        (self.mods / 'map').mkdir()
        (self.mods / 'map' / 'keep').write_bytes(b'map')
        self.assertTrue(self.select())
        self.assertEqual(self.state.selected_custom_mod['relative_path'], self.new['relative_path'])
        self.assertTrue(library.installed()[self.new['id']]['enabled'])
        self.assertFalse(library.installed()[self.old['id']]['enabled'])
        self.assertFalse(self.state.historic_mode_active)
        self.assertFalse((self.mods / self.old_name).exists())
        self.assertEqual((self.mods / 'map' / 'keep').read_bytes(), b'map')
        self.assertTrue((self.mods / staging_name(library.mod_folder(self.new))).exists())
        self.assertFalse(list(self.mods.parent.glob('.selection-*')))

    def test_removed_unknown_wrong_category_and_conflicting_choices_are_rejected(self):
        self.prepare()
        library.remove(self.new['id'])
        before = (library.root() / 'installed.json').read_bytes()
        for category, paths, champion in [
            ('skins', [self.new['relative_path']], 103),
            ('skins', ['skins/103000/missing'], 103),
            ('maps', [self.old['relative_path']], None),
            ('skins', [self.old['relative_path']], 99),
        ]:
            with self.subTest(category=category, paths=paths, champion=champion):
                with self.assertRaises(ValueError):
                    client_sync.select(category, paths, champion_id=champion, skin_id=103001)
                self.assertEqual((library.root() / 'installed.json').read_bytes(), before)

    def test_missing_payload_and_multiple_skins_preserve_old_choice(self):
        self.prepare()
        with self.assertRaises(ValueError):
            client_sync.select('skins', [self.old['relative_path'], self.new['relative_path']], champion_id=103)
        source = library.mod_folder(self.new)
        source.rename(source.with_name(source.name + '-missing'))
        with self.assertRaises(ValueError):
            client_sync.select('skins', [self.new['relative_path']], champion_id=103)
        self.assertEqual((library.root() / 'installed.json').read_bytes(), self.index)

    def test_archive_preparation_prunes_against_active_staging(self):
        self.prepare()
        with patch('utils.core.junction.prune_extraction_cache') as prune:
            with prepare_selection(self.archive('archive.zip'), self.mods, self.root / 'cache', replace_all=False):
                pass
        self.assertEqual(prune.call_args.args[1], self.mods)


class ProfileCapacityTests(LibraryFixture):
    def test_all_growing_operations_reject_before_replacing_original(self):
        library.import_archive(self.archive(), self.item())
        ids = [profiles.save('Profile ' + str(i)) for i in range(12)]
        library.enable('sample', True)
        path = library.root() / 'profiles.json'
        original = path.read_bytes()
        document = {'type': 'okdev-profile', 'schema': 2, 'name': 'Imported', 'mods': [
            {'id': 'sample', 'name': '\U0001f600' * 100, 'version': '1.0.0'}]}
        operations = [lambda: profiles.save('New'), lambda: profiles.import_profile(document),
                      lambda: profiles.rename(ids[0], '\U0001f600' * 50), lambda: profiles.update(ids[0])]
        with patch.object(library, 'MAX_INDEX_BYTES', len(original)):
            for index, operation in enumerate(operations):
                with self.subTest(operation=index):
                    with self.assertRaisesRegex(ValueError, 'boyut'):
                        operation()
                    self.assertEqual(path.read_bytes(), original)
                    self.assertEqual(len(profiles.list_profiles(strict=True)), 12)
            profiles.remove(ids[0])
            self.assertEqual(len(profiles.list_profiles(strict=True)), 11)

    def test_exact_utf8_limit_is_readable_and_one_more_byte_is_rejected(self):
        identity = profiles.save('a')
        path = library.root() / 'profiles.json'
        data = profiles.list_profiles(strict=True)
        data[identity]['name'] = '\U0001f600'
        expected = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
        with patch.object(library, 'MAX_INDEX_BYTES', len(expected)):
            profiles.rename(identity, '\U0001f600')
            self.assertEqual(path.read_bytes(), expected)
            self.assertEqual(profiles.list_profiles(strict=True)[identity]['name'], '\U0001f600')
            with self.assertRaises(ValueError):
                profiles.rename(identity, '\U0001f600a')
            self.assertEqual(path.read_bytes(), expected)
