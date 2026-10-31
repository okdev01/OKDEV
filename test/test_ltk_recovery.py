import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import okdev_ltk_update as update


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        for name in ('select_cached', 'sync_official'):
            mock = patch('okdev_ltk_delivery.' + name, return_value=None)
            mock.start()
            self.addCleanup(mock.stop)

    def test_incompatible_release_downloads_once_and_new_release_is_retried(self):
        with tempfile.TemporaryDirectory() as temp:
            tools = Path(temp) / 'app/_internal/injection/tools'
            tools.mkdir(parents=True)
            for name in update.NAMES:
                (tools / name).write_bytes(b'original')
            bad = SimpleNamespace(missing=[], eol=100, game_build=101, expired=True)
            asset = {'name': 'LTK.Manager_1.32.0_x64-setup.exe', 'digest': 'sha256:' + 'a' * 64}
            with patch.object(update, 'check_ltk_patcher', return_value=bad), \
                 patch.object(update, 'read_game_build', return_value=101) as game, \
                 patch.object(update, 'require_idle'), \
                 patch.object(update, 'latest_asset', return_value=asset) as latest, \
                 patch.object(update, 'download_official') as download, \
                 patch.object(update, 'extract_pair'), \
                 patch.object(update, 'install_pair') as install:
                for _ in range(2):
                    with self.assertRaisesRegex(update.PatcherUnavailable, 'yeniden indirilmeyecek'):
                        update.ensure_patcher(tools, Path('game.exe'))
                self.assertEqual(download.call_count, 1)
                self.assertEqual(latest.call_count, 2)
                install.assert_not_called()
                asset['digest'] = 'sha256:' + 'b' * 64
                with self.assertRaises(update.PatcherUnavailable):
                    update.ensure_patcher(tools, Path('game.exe'))
                self.assertEqual(download.call_count, 2)
                game.return_value = 102
                with self.assertRaises(update.PatcherUnavailable):
                    update.ensure_patcher(tools, Path('game.exe'))
                self.assertEqual(download.call_count, 3)
                for name in update.NAMES:
                    self.assertEqual((tools / name).read_bytes(), b'original')

    def test_damaged_cache_does_not_block_new_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            tools = Path(temp)
            asset = {'digest': 'sha256:' + 'a' * 64}
            for body in ('[', '[]', 'null', 'x' * 9000):
                (tools / '.ltk-unavailable.json').write_text(body)
                self.assertFalse(update._rejected_release(tools, asset, 101))

    def test_compatible_update_clears_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            tools = Path(temp) / 'app/_internal/injection/tools'
            tools.mkdir(parents=True)
            cache = tools / '.ltk-unavailable.json'
            cache.write_text(json.dumps({'schema': 1, 'digest': 'old', 'game_build': 101}))
            old = SimpleNamespace(missing=[], eol=100, game_build=101, expired=True)
            new = SimpleNamespace(missing=[], eol=102, game_build=101, expired=False)
            with patch.object(update, 'check_ltk_patcher', side_effect=[old, new]), \
                 patch.object(update, 'read_game_build', return_value=101), \
                 patch.object(update, 'require_idle'), \
                 patch.object(update, 'latest_asset', return_value={'name': 'new', 'digest': 'new'}), \
                 patch.object(update, 'download_official'), patch.object(update, 'extract_pair'), \
                 patch.object(update, 'install_pair') as install:
                self.assertTrue(update.ensure_patcher(tools, Path('game.exe')))
                install.assert_called_once()
                self.assertFalse(cache.exists())

    def run_entry(self, ready):
        # Execute the actual entry function while isolating windows, game threads
        # and installation state. No textual assertions about its implementation.
        source = Path(__file__).parents[1] / 'main/__init__.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        core = Mock()
        env = {'sys': SimpleNamespace(platform='win32'),
               'setup_arguments': lambda: SimpleNamespace(dev=False),
               '_check_dll_present': Mock(return_value=ready), 'run_league_unlock': core}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), env)
        with patch('okdev_install_paths.apply_install_paths'), \
             patch('hub.desktop.run') as library, \
             patch.dict(sys.modules, {'launcher': SimpleNamespace(run_launcher=Mock(
                 side_effect=None if ready else update.PatcherUnavailable('unsupported')))}):
            env['main']()
            if ready:
                core.assert_called_once()
                library.assert_not_called()
            else:
                library.assert_called_once()
                core.assert_not_called()

    def test_missing_dependency_opens_library_without_game_threads(self):
        self.run_entry(False)

    def test_supported_dependency_starts_game_integration(self):
        self.run_entry(True)

    def test_diagnostics_do_not_call_existing_but_expired_files_ready(self):
        from hub.patcher_status import collect
        for reason, missing, eol, game_build, expired in [
            ('expired', [], 100, 101, True), ('ready', [], 102, 101, False),
            ('missing', ['dll'], None, 101, False), ('invalid', [], None, 101, False),
            ('unknown_game', [], 100, None, False),
        ]:
            with self.subTest(reason=reason), \
                 patch('injection.config.config_manager.ConfigManager.load_league_path', return_value=None), \
                 patch('hub.patcher_status.check_ltk_patcher', return_value=SimpleNamespace(
                     missing=missing, eol=eol, game_build=game_build, expired=expired)):
                result = collect()
                self.assertEqual(result['reason'], reason)
                self.assertEqual(result['ready'], reason == 'ready')


if __name__ == '__main__':
    unittest.main()
