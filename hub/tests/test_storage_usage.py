import json
from pathlib import Path
import stat
from types import SimpleNamespace
from unittest.mock import patch

from hub import library, storage_usage
from hub.tests.test_library import LibraryFixture


class StorageUsageTests(LibraryFixture):
    def test_categories_count_nested_bytes_without_returning_private_paths(self):
        root = library.root()
        files = [(self.root / 'mods/private-name/file.wad', b'123'),
                 (root / 'removed/backup/file.wad', b'12345'),
                 (root / 'covers/cover.jpg', b'12'),
                 (root / 'download-active/archive.part', b'1234'),
                 (root / 'webview/cache', b'123456'),
                 (root / 'guide-webview/cache', b'1234567'),
                 (root / 'settings.json', b'not part of these categories')]
        for path, content in files:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        before = {path: path.read_bytes() for path, _ in files}
        report = storage_usage.collect()
        self.assertEqual([c['bytes'] for c in report], [3, 5, 2, 4, 6, 7])
        self.assertTrue(all(c['files'] == 1 and c['complete'] for c in report))
        self.assertNotIn('private-name', json.dumps(report))
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertEqual(before, {path: path.read_bytes() for path, _ in files})

    def test_absent_directory_is_complete_empty_result(self):
        self.assertEqual(storage_usage.scan(self.root / 'missing'), {'bytes': 0, 'files': 0, 'complete': True})

    def test_entry_budget_is_a_visible_lower_bound(self):
        for i in range(20):
            (self.root / str(i)).write_bytes(b'1234')
        result = storage_usage.scan(self.root, max_entries=5)
        self.assertFalse(result['complete'])
        self.assertEqual(result['bytes'], result['files'] * 4)
        self.assertLessEqual(result['files'], 4)

    def test_expired_budget_does_not_start_io(self):
        with patch.object(Path, 'lstat') as inspect:
            self.assertFalse(storage_usage.scan(self.root, seconds=0)['complete'])
        inspect.assert_not_called()

    def test_permission_failure_is_partial_not_zero_complete(self):
        with patch.object(storage_usage.os, 'scandir', side_effect=PermissionError()):
            self.assertFalse(storage_usage.scan(self.root)['complete'])

    def test_reparse_point_and_symlink_are_never_enumerated(self):
        for mode, attributes in [(stat.S_IFDIR, 0x400), (stat.S_IFLNK, 0)]:
            metadata = SimpleNamespace(st_mode=mode, st_file_attributes=attributes)
            with patch.object(Path, 'lstat', return_value=metadata), patch.object(storage_usage.os, 'scandir') as scan:
                result = storage_usage.scan(self.root)
            self.assertEqual(result, {'bytes': 0, 'files': 0, 'complete': False})
            scan.assert_not_called()

    def test_download_filter_does_not_scan_unrelated_hub_children(self):
        root = library.root()
        for name in ['download-one', 'download-two', 'removed']:
            folder = root / name
            folder.mkdir()
            (folder / 'file').write_bytes(b'1234')
        result = storage_usage.scan(root, children_prefix='download-')
        self.assertEqual(result, {'bytes': 8, 'files': 2, 'complete': True})
