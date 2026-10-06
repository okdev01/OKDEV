from pathlib import Path
import tempfile
from unittest.mock import Mock

from hub import library
from hub.desktop import Api
from hub.tests.test_library import LibraryFixture


class SupportExportTests(LibraryFixture):
    def test_export_contains_checks_but_not_private_settings(self):
        library.write_json(library.root() / 'settings.json', {'secret_fixture': 'do-not-export', 'auto_accept': False})
        export_dir = tempfile.TemporaryDirectory()
        self.addCleanup(export_dir.cleanup)
        output = Path(export_dir.name) / 'report.json'
        api = Api()
        api._window = Mock()
        api._window.create_file_dialog.return_value = (str(output),)
        result = api.export_diagnostics()
        self.assertTrue(result['ok'])
        self.assertTrue(result['result']['saved'])
        text = output.read_text(encoding='utf-8')
        self.assertNotIn('do-not-export', text)
        self.assertNotIn(str(self.root), text)
        self.assertGreater(len(library.read_json(output, {})['checks']), 7)

    def test_cancel_saves_nothing(self):
        api = Api()
        api._window = Mock()
        api._window.create_file_dialog.return_value = None
        result = api.export_diagnostics()
        self.assertEqual(result, {'ok': True, 'result': {'saved': False}})
        self.assertEqual(list(self.root.glob('*.json')), [])

    def test_export_never_overwrites_live_settings(self):
        target = library.root() / 'settings.json'
        original = {'auto_accept': True, 'favorites': ['sample']}
        library.write_json(target, original)
        api = Api()
        api._window = Mock()
        api._window.create_file_dialog.return_value = (str(target),)
        result = api.export_diagnostics()
        self.assertFalse(result['ok'])
        self.assertEqual(library.read_json(target, {}), original)

    def test_profile_export_keeps_local_profile_store_intact(self):
        from hub import profiles
        profile_id = profiles.save('Profile fixture')
        target = library.root() / 'profiles.json'
        original = target.read_bytes()
        api = Api()
        api._window = Mock()
        api._window.create_file_dialog.return_value = (str(target),)
        self.assertFalse(api.export_profile(profile_id)['ok'])
        self.assertEqual(target.read_bytes(), original)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'portable.json'
            api._window.create_file_dialog.return_value = (str(target),)
            self.assertTrue(api.export_profile(profile_id)['result']['saved'])
            self.assertEqual(library.read_json(target, {})['type'], 'okdev-profile')

    def test_json_export_rejects_other_file_types_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'notes.txt'
            target.write_text('personal notes')
            api = Api()
            api._window = Mock()
            api._window.create_file_dialog.return_value = (str(target),)
            self.assertFalse(api.export_diagnostics()['ok'])
            self.assertEqual(target.read_text(), 'personal notes')
