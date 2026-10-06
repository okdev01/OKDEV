from unittest.mock import patch

from hub import library
from hub.desktop import Api
from hub.tests.test_library import LibraryFixture


class SnapshotTests(LibraryFixture):
    def test_snapshot_reads_installed_index_once_and_never_loads_images(self):
        library.import_archive(self.archive(), self.item())
        api = Api()
        self.addCleanup(lambda: api._downloads().close())
        with patch('hub.library.installed', wraps=library.installed) as read, patch('hub.covers.preview') as image:
            value = api.snapshot()
        self.assertEqual(read.call_count, 1)
        image.assert_not_called()
        self.assertTrue(value['installed']['sample']['files_available'])

    def test_thumbnail_bridge_limits_and_validates_requested_ids(self):
        library.import_archive(self.archive(), self.item())
        api = Api()
        with patch('hub.covers.preview', return_value='preview') as preview:
            for value in (None, 'sample', ['../file'], ['sample'] * 49):
                self.assertEqual(api.cover_previews(value), {})
            preview.assert_not_called()
            self.assertEqual(set(api.cover_previews(['sample', 'unknown', 'sample'])), {'sample'})
            preview.assert_called_once()

    def test_corrupt_index_remains_readable_with_warning_and_no_overwrite(self):
        path = library.root() / 'installed.json'
        path.write_bytes(b'{broken')
        api = Api()
        self.addCleanup(lambda: api._downloads().close())
        value = api.snapshot()
        self.assertEqual(value['installed'], {})
        self.assertTrue(value['warning'])
        self.assertEqual(path.read_bytes(), b'{broken')

    def test_project_links_only_open_fixed_destinations(self):
        api = Api()
        with patch('hub.desktop.webbrowser.open', return_value=True) as open_page:
            for value in ('https://elsewhere.test', '../file', None, [], '__class__'):
                self.assertFalse(api.open_project_page(value)['ok'])
            open_page.assert_not_called()
            self.assertTrue(api.open_project_page('releases')['ok'])
            open_page.assert_called_once_with('https://github.com/okdev01/OKDEV/releases')

    def test_project_link_browser_failure_is_explained(self):
        with patch('hub.desktop.webbrowser.open', return_value=False):
            result = Api().open_project_page('support')
        self.assertFalse(result['ok'])
        self.assertIn('Tarayıcı', result['error'])
