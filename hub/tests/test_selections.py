from unittest.mock import patch

from hub import library, selections
from hub.tests.test_library import LibraryFixture


class SelectionTests(LibraryFixture):
    def two(self):
        library.import_archive(self.archive(), self.item())
        library.import_archive(self.archive('second.zip'), self.item('second'))
        library.enable('sample', True)

    def test_preview_explains_replaced_selection_without_writing(self):
        self.two()
        plan = selections.preview(['second'])
        self.assertEqual([m['id'] for m in plan['enable']], ['second'])
        self.assertEqual([m['id'] for m in plan['disable']], ['sample'])
        self.assertTrue(library.installed()['sample']['enabled'])
        self.assertFalse(selections.undo_status()['available'])

    def test_apply_then_undo_restores_whole_previous_selection(self):
        self.two()
        plan = selections.preview(['second'])
        selections.apply(['second'], expected_revision=plan['revision'])
        self.assertTrue(library.installed()['second']['enabled'])
        self.assertTrue(selections.undo_status()['available'])
        selections.undo()
        self.assertTrue(library.installed()['sample']['enabled'])
        self.assertFalse(library.installed()['second']['enabled'])
        self.assertFalse(selections.undo_status()['available'])

    def test_stale_preview_does_not_override_newer_changes(self):
        self.two()
        plan = selections.preview(['second'])
        library.enable('sample', False)
        with self.assertRaisesRegex(ValueError, 'listesi değişti'):
            selections.apply(['second'], expected_revision=plan['revision'])
        self.assertFalse(library.installed()['second']['enabled'])

    def test_conflicting_bulk_set_is_rejected_atomically(self):
        self.two()
        with self.assertRaisesRegex(ValueError, 'tek mod'):
            selections.apply(['sample', 'second'])
        self.assertTrue(library.installed()['sample']['enabled'])

    def test_missing_files_prevent_undo_without_touching_current_selection(self):
        self.two()
        selections.apply(['second'])
        first = library.mod_folder(library.installed()['sample'])
        first.rename(first.with_name('moved-fixture'))
        with self.assertRaisesRegex(ValueError, 'bulunamadı'):
            selections.undo()
        self.assertTrue(library.installed()['second']['enabled'])

    def test_failed_index_write_does_not_offer_invalid_undo(self):
        self.two()
        writer = library.write_json
        def fail_index(path, value):
            if path.name == 'installed.json':
                raise OSError('disk full')
            return writer(path, value)
        with patch('hub.library.write_json', side_effect=fail_index):
            with self.assertRaises(OSError):
                selections.apply(['second'])
        self.assertTrue(library.installed()['sample']['enabled'])
        self.assertFalse(selections.undo_status()['available'])

    def test_bulk_disable_and_empty_replace_are_reversible(self):
        self.two()
        selections.apply([], 'replace')
        self.assertFalse(any(m['enabled'] for m in library.installed().values()))
        selections.undo()
        self.assertTrue(library.installed()['sample']['enabled'])

    def test_no_op_preserves_last_undo(self):
        self.two()
        selections.apply(['second'])
        self.assertFalse(selections.apply(['second'])['changed'])
        selections.undo()
        self.assertTrue(library.installed()['sample']['enabled'])

    def test_replacing_mod_clears_its_history(self):
        self.two()
        with patch('hub.library._clear_history') as clear:
            selections.apply(['second'])
        self.assertEqual(clear.call_args.args[0]['id'], 'sample')
