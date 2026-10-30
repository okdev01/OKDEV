"""Progress must describe package preparation after the download has finished."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, call, patch
import zipfile

from launcher.update.update_installer import UpdateInstaller


class UpdatePreparationProgressTests(unittest.TestCase):
    def package(self, folder, app='OKDEV'):
        archive = folder / 'update.zip'
        with zipfile.ZipFile(archive, 'w') as bundle:
            bundle.writestr('OKDEV.exe', b'isolated application fixture')
            for n in range(3):
                bundle.writestr(f'_internal/part-{n}.bin', bytes([n]) * 8192)
            bundle.writestr('okdev-update.json', json.dumps({'app': app, 'version': '2.0.0'}))
        return archive

    def test_preparation_reports_monotonic_progress_and_preserves_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self.package(root)
            progress, status = [], []
            result = UpdateInstaller().extract_update(archive, root/'staging', progress.append, status.append)
            self.assertEqual(result, root/'staging')
            self.assertEqual(progress[0], 0)
            self.assertEqual(progress[-1], 100)
            self.assertEqual(progress, sorted(set(progress)))
            self.assertTrue(any(0 < value < 100 for value in progress))
            self.assertTrue(all(0 <= value <= 100 for value in progress))
            for n in range(3):
                self.assertEqual((result/f'_internal/part-{n}.bin').read_bytes(), bytes([n]) * 8192)
            self.assertIn('doğrulanıyor', status[-1])

    def test_rejected_package_never_reports_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress, status = [], []
            result = UpdateInstaller().extract_update(self.package(root, app='Other'), root/'staging', progress.append, status.append)
            self.assertIsNone(result)
            self.assertNotIn(100, progress)
            self.assertIn('doğrulanamadı', status[-1])

    def test_launcher_replaces_completed_transfer_with_preparation_progress(self):
        from launcher.core.launcher import _perform_update
        dialog = MagicMock()
        def run(status, progress, bytes_callback, **kwargs):
            bytes_callback(1000, 1000)
            progress(0)
            status('Preparing fixture')
            progress(50)
            progress(100)
            return False  # No updater is launched by this presentation test.
        with patch('launcher.core.launcher.UpdateSequence') as sequence:
            sequence.return_value.perform_update.side_effect = run
            self.assertFalse(_perform_update(dialog))
        history = dialog.mock_calls
        transfer = history.index(call.update_transfer_progress(1000, 1000))
        cleared = history.index(call.clear_transfer_text(), transfer)
        prepared = history.index(call.set_detail('Güncelleme paketi hazırlanıyor…'), transfer)
        halfway = history.index(call.set_progress(50))
        self.assertLess(transfer, cleared)
        self.assertLess(cleared, prepared)
        self.assertLess(prepared, halfway)


if __name__ == '__main__': unittest.main()
