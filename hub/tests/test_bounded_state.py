"""Corrupt local state remains recoverable and cannot cause unbounded reads."""
import io
from types import SimpleNamespace
from unittest.mock import Mock, patch

from hub import activity, diagnostics, library, profiles
from hub.downloads import DownloadQueue
from hub.tests.test_library import LibraryFixture


class BoundedStateTests(LibraryFixture):
    def test_unicode_and_exact_byte_boundary(self):
        path = library.root() / 'state.json'
        content = '{"name":"Türkçe 世界 🎮"}'.encode('utf-8')
        path.write_bytes(content)
        self.assertEqual(library.load_json(path, len(content))['name'], 'Türkçe 世界 🎮')
        with self.assertRaisesRegex(ValueError, 'boyut'):
            library.load_json(path, len(content) - 1)
        self.assertEqual(path.read_bytes(), content)

    def test_growth_after_stat_still_has_a_bounded_read(self):
        path = Mock()
        path.stat.return_value = SimpleNamespace(st_size=2)
        stream = Mock(wraps=io.BytesIO(b' ' * 10000))
        stream.__enter__ = Mock(return_value=stream)
        stream.__exit__ = Mock(return_value=False)
        path.open.return_value = stream
        with self.assertRaisesRegex(ValueError, 'boyut'):
            library.load_json(path, 256)
        stream.read.assert_called_once_with(257)

    def test_oversized_settings_cannot_be_overwritten_by_an_action(self):
        path = library.root() / 'settings.json'
        original = b'{"favorites":[]}' + b' ' * library.MAX_SETTINGS_BYTES
        path.write_bytes(original)
        self.assertEqual(library.settings()['favorites'], [])
        with self.assertRaisesRegex(ValueError, 'korunuyor'):
            library.set_favorite('sample', True)
        self.assertEqual(path.read_bytes(), original)
        report = diagnostics.collect()
        self.assertEqual(next(c for c in report['checks'] if c['name'] == 'Tercihler')['status'], 'warning')

    def test_oversized_index_blocks_mutation_before_moving_mod_files(self):
        item = library.import_archive(self.archive(), self.item())
        path = library.root() / 'installed.json'
        original = path.read_bytes()
        with patch.object(library, 'MAX_INDEX_BYTES', len(original) - 1):
            self.assertEqual(library.installed(), {})
            with self.assertRaisesRegex(ValueError, 'korunuyor'):
                library.remove('sample')
        self.assertEqual(path.read_bytes(), original)
        self.assertTrue(library.mod_folder(item).is_dir())

    def test_deeply_nested_state_has_fallbacks_and_preserves_originals(self):
        content = '[' * 3000 + '0' + ']' * 3000
        for filename in ('settings.json', 'installed.json', 'profiles.json', 'activity.json', 'downloads.json', 'catalog.json'):
            (library.root() / filename).write_text(content, encoding='utf-8')
        self.assertEqual(library.settings()['favorites'], [])
        self.assertEqual(library.installed(), {})
        self.assertEqual(profiles.list_profiles(), {})
        self.assertTrue(activity.read()['warning'])
        queue = DownloadQueue()
        self.addCleanup(queue.close)
        self.assertTrue(queue.snapshot()['warning'])
        self.assertEqual(library.catalog(allow_network=False)[0]['mods'], [])
        self.assertGreaterEqual(sum(c['status'] == 'warning' for c in diagnostics.collect()['checks']), 4)
        for callback in (lambda: library.set_auto_accept(True), lambda: profiles.save('New')):
            with self.assertRaises(ValueError):
                callback()
        for filename in ('settings.json', 'installed.json', 'profiles.json', 'activity.json', 'downloads.json', 'catalog.json'):
            self.assertEqual((library.root() / filename).read_text(encoding='utf-8'), content)

    def test_deep_remote_catalog_keeps_good_cache_and_closes_response(self):
        cached = {'schema': 1, 'mods': []}
        library.write_json(library.root() / 'catalog.json', cached)
        response = Mock(status_code=200, headers={})
        response.iter_content.return_value = [b'[' * 3000 + b'0' + b']' * 3000]
        with patch.object(library.requests, 'get', return_value=response):
            value, warning = library.catalog(refresh=True)
        self.assertEqual(value, cached)
        self.assertTrue(warning)
        response.close.assert_called_once()

    def test_duplicate_folder_records_block_file_moves_and_preserve_index(self):
        item = library.import_archive(self.archive(), self.item())
        folder = library.mod_folder(item)
        duplicate = dict(item, id='duplicate')
        library.write_json(library.root() / 'installed.json', {'sample':item, 'duplicate':duplicate})
        original = (library.root() / 'installed.json').read_bytes()
        self.assertEqual(set(library.installed()), {'sample'})
        with self.assertRaisesRegex(ValueError, 'korunuyor'):
            library.remove('sample')
        self.assertEqual((library.root() / 'installed.json').read_bytes(), original)
        self.assertEqual((folder / 'WAD/Ahri.wad.client').read_bytes(), b'fixture-wad-data')

    def test_windows_folder_case_alias_cannot_be_registered_twice(self):
        import os
        if os.name != 'nt':
            self.skipTest('Windows path comparison')
        item = library.import_archive(self.archive(), self.item())
        duplicate = dict(item, id='duplicate', folder_name=item['folder_name'].upper(),
                         relative_path=item['relative_path'].rsplit('/',1)[0] + '/' + item['folder_name'].upper())
        library.write_json(library.root() / 'installed.json', {'sample':item, 'duplicate':duplicate})
        with self.assertRaises(ValueError):
            library.installed(strict=True)
        self.assertTrue(library.mod_folder(item).is_dir())
