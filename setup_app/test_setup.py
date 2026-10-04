import importlib.util
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent))
import setup as installer


class SetupTests(unittest.TestCase):
    def test_missing_dependencies_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                installer.find_patcher(directory)
            with self.assertRaises(ValueError):
                installer.find_game(directory)

    def test_archive_rejects_unsafe_members_and_bundled_patcher(self):
        for filename in ('../escape', '/absolute', 'C:/outside', 'dir\\escape', 'ltk_patcher_host.exe'):
            with self.subTest(filename=filename):
                archive = SimpleNamespace(infolist=lambda: [SimpleNamespace(filename=filename)])
                with self.assertRaises(ValueError):
                    list(installer.safe_members(archive))

    def test_install_is_complete_and_existing_folder_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            patcher = root / 'ltk'
            patcher.mkdir()
            for name in installer.PATCHER_NAMES:
                (patcher / name).write_bytes(b'MZ-test')
            game = root / 'League/Game'
            game.mkdir(parents=True)
            (game / 'League of Legends.exe').write_bytes(b'MZ-game')
            with zipfile.ZipFile(root / 'payload.zip', 'w') as archive:
                archive.writestr('OKDEV.exe', b'MZ-app')
                archive.writestr('_internal/example.txt', b'example')
            with patch.object(installer, 'RESOURCES', root), patch.object(installer, 'read_dll_eol', return_value=100), patch.object(installer, 'read_game_build', return_value=99):
                destination, warning = installer.install(patcher, game, root / 'OKDEV', make_shortcut=False)
                self.assertFalse(warning)
                self.assertEqual((destination / 'OKDEV.exe').read_bytes(), b'MZ-app')
                self.assertEqual(json.loads((destination / 'okdev-install.json').read_text())['game_dir'], str(game))
                self.assertTrue((destination / '_internal/injection/tools/ltk_patcher_dll.dll').exists())
                with self.assertRaises(ValueError):
                    installer.install(patcher, game, destination, make_shortcut=False)
                self.assertEqual((destination / 'OKDEV.exe').read_bytes(), b'MZ-app')
                with patch.object(installer, 'read_game_build', return_value=101):
                    with self.assertRaises(ValueError):
                        installer.validate(patcher, game, root / 'TooNew')

    def test_failed_install_rolls_back_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / 'OKDEV'
            with zipfile.ZipFile(root / 'payload.zip', 'w') as archive:
                archive.writestr('other.txt', b'missing exe')
            with patch.object(installer, 'RESOURCES', root), patch.object(installer, 'validate', return_value=(root, root, destination)):
                with self.assertRaises(ValueError):
                    installer.install(root, root, destination, make_shortcut=False)
            self.assertFalse(destination.exists())
            self.assertFalse(list(root.glob('.okdev-install-*')))


if __name__ == '__main__':
    unittest.main()
