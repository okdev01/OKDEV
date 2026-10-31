from unittest.mock import Mock

from hub.desktop import Api, build_html
from hub.tests.test_library import LibraryFixture


class DesignImportTests(LibraryFixture):
    def test_invalid_drop_preserves_previous_selected_file(self):
        api = Api()
        selected = self.archive()
        api.select_mod(str(selected))
        wrong_extension = self.archive('wrong.rar')
        with self.assertRaisesRegex(ValueError, 'Yalnızca'):
            api.select_mod(str(wrong_extension))
        self.assertEqual(api._selected, selected)
        with self.assertRaisesRegex(ValueError, 'bulunamadı'):
            api.select_mod(str(self.root / 'missing.zip'))
        self.assertEqual(api._selected, selected)

    def test_dropped_source_still_enforces_champion_contract(self):
        api = Api()
        api._source = {'champion_id': 18}
        with self.assertRaisesRegex(ValueError, 'eşleşmiyor'):
            api.select_mod(str(self.archive()))
        self.assertIsNone(api._selected)

    def test_native_drop_registration_is_idempotent_and_quotes_paths(self):
        api = Api()
        api._window = Mock()
        api.bind_dropzones()
        self.assertEqual(api._window.dom.get_element.call_count, 2)
        api.bind_dropzones()
        self.assertEqual(api._window.dom.get_element.call_count, 2)
        handler = api._window.dom.get_element.return_value.on.call_args.args[1]
        self.assertTrue(handler.prevent_default)
        handler.callback({'dataTransfer': {'files': [{'pywebviewFullPath': 'C:\\örnek " mod.fantome'}]}})
        script = api._window.evaluate_js.call_args.args[0]
        self.assertIn('okdev-file-drop', script)
        self.assertIn('\\"', script)

    def test_embedded_shell_artwork_is_offline_and_bounded(self):
        html = build_html()
        self.assertNotIn('asset:hero-warrior', html)
        self.assertNotIn('asset:guide-fortress', html)
        self.assertEqual(html.count('data:image/webp;base64,'), 2)
        self.assertLess(len(html.encode('utf-8')), 2 * 1024 * 1024)
