import tempfile
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from hub import backups, library, package_info
from hub.desktop import Api
from hub.tests.test_library import LibraryFixture


class BackupTests(LibraryFixture):
    def make_backup(self):
        library.import_archive(self.archive(), self.item())
        library.remove('sample')
        return library.removed()[0]['backup_id']

    def test_export_round_trip_preserves_payload_and_original_backup(self):
        backup_id = self.make_backup()
        info = backups.inspect(backup_id)
        self.assertGreater(info['bytes'], 0)
        self.assertFalse(info['installed'])
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'export.fantome'
            backups.export(backup_id, output)
            library.validate_archive(output)
            self.assertEqual(package_info.inspect(output)['suggested']['name'], 'Test mod')
            restored = library.import_archive(output, self.item('round-trip'))
            self.assertEqual((library.mod_folder(restored) / 'WAD/Ahri.wad.client').read_bytes(), b'fixture-wad-data')
            with zipfile.ZipFile(output) as archive:
                note = archive.read('META/okdev-backup.json').decode('utf-8')
                self.assertNotIn('relative_path', note)
                self.assertNotIn('enabled', note)
                self.assertNotIn(str(self.root), note)
        self.assertEqual(library.removed()[0]['backup_id'], backup_id)

    def test_destination_inside_runtime_data_is_rejected_without_overwrite(self):
        backup_id = self.make_backup()
        output = library.root() / 'existing.fantome'
        output.write_bytes(b'original package')
        original = output.read_bytes()
        with self.assertRaisesRegex(ValueError, 'dışında'):
            backups.export(backup_id, output)
        self.assertEqual(output.read_bytes(), original)

    def test_export_cannot_overwrite_a_non_package_file(self):
        backup_id = self.make_backup()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'settings.json'
            output.write_bytes(b'original settings')
            with self.assertRaisesRegex(ValueError, 'uzantısıyla'):
                backups.export(backup_id, output)
            self.assertEqual(output.read_bytes(), b'original settings')

    def test_failed_export_keeps_existing_destination(self):
        backup_id = self.make_backup()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'export.fantome'
            output.write_bytes(b'previous export')
            with patch('hub.backups.zipfile.ZipFile.write', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    backups.export(backup_id, output)
            self.assertEqual(output.read_bytes(), b'previous export')
            self.assertEqual(list(Path(tmp).iterdir()), [output])
        self.assertEqual(len(library.removed()), 1)

    def test_externally_modified_backup_is_validated_before_replacing_export(self):
        backup_id = self.make_backup()
        folder = library.root() / 'removed' / backup_id / 'mod'
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'export.fantome'
            output.write_bytes(b'previous valid export')
            bad_file = folder / 'run.exe'
            bad_file.write_bytes(b'not a game asset')
            with self.assertRaisesRegex(ValueError, 'yalnızca oyun verisi'):
                backups.export(backup_id, output)
            self.assertEqual(output.read_bytes(), b'previous valid export')
            self.assertEqual(bad_file.read_bytes(), b'not a game asset')
            bad_file.unlink()
            (folder / 'WAD/Ahri.wad.client').unlink()
            with self.assertRaisesRegex(ValueError, 'WAD oyun dosyaları'):
                backups.export(backup_id, output)
            self.assertEqual(output.read_bytes(), b'previous valid export')
            self.assertEqual(list(Path(tmp).iterdir()), [output])

    def test_invalid_backup_ids_never_access_arbitrary_paths(self):
        for backup_id in ('../other', 'not-a-uuid', None, True):
            with self.assertRaises(ValueError):
                backups.inspect(backup_id)

    def test_payload_reparse_point_is_rejected(self):
        backup_id = self.make_backup()
        with patch('pathlib.Path.is_symlink', return_value=True):
            with self.assertRaises(ValueError):
                backups.inspect(backup_id)

    def test_cancelled_save_dialog_keeps_backup_and_creates_no_export(self):
        backup_id = self.make_backup()
        api = Api()
        api._window = Mock()
        api._window.create_file_dialog.return_value = None
        self.assertEqual(api.export_backup(backup_id), {'ok': True, 'result': {'saved': False}})
        self.assertEqual(len(library.removed()), 1)

    def test_backup_inspection_reports_current_version_conflict(self):
        backup_id = self.make_backup()
        library.import_archive(self.archive(), self.item())
        self.assertTrue(backups.inspect(backup_id)['installed'])

    def test_reused_folder_reports_export_route_without_touching_either_payload(self):
        backup_id = self.make_backup()
        other = library.import_archive(self.archive(), self.item('other'))
        info = backups.inspect(backup_id)
        self.assertFalse(info['installed'])
        self.assertEqual(info['restore_conflict'], 'folder')
        with self.assertRaisesRegex(ValueError, 'Paket olarak kaydet'):
            library.restore(backup_id)
        self.assertEqual((library.mod_folder(other) / 'WAD/Ahri.wad.client').read_bytes(), b'fixture-wad-data')
        self.assertEqual(len(library.removed()), 1)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'restored.fantome'
            backups.export(backup_id, output)
            restored = library.import_archive(output, self.item())
        self.assertNotEqual(restored['relative_path'], other['relative_path'])
        self.assertEqual(len(library.installed()), 2)
