import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import okdev_ltk_update as update


class LtkUpdateTests(unittest.TestCase):
    def asset_release(self):
        return {'tag_name': 'v1.28.1', 'assets': [{
            'name': 'LTK.Manager_1.28.1_x64-setup.exe', 'size': 10,
            'digest': 'sha256:' + 'a'*64,
            'browser_download_url': 'https://github.com/LeagueToolkit/ltk-manager/releases/download/v1.28.1/LTK.Manager_1.28.1_x64-setup.exe'}]}

    def test_only_official_stable_hashed_asset_is_accepted(self):
        good = self.asset_release()
        self.assertEqual(update.release_asset(good)['size'], 10)
        for change in ('url', 'digest', 'size', 'prerelease'):
            bad = copy.deepcopy(good)
            if change == 'url':
                bad['assets'][0]['browser_download_url'] += '?redirect=elsewhere'
            elif change == 'digest':
                bad['assets'][0]['digest'] = None
            elif change == 'size':
                bad['assets'][0]['size'] = 1024**3
            else:
                bad['prerelease'] = True
            with self.subTest(change=change), self.assertRaises(ValueError):
                update.release_asset(bad)

    def test_healthy_install_does_not_download(self):
        with tempfile.TemporaryDirectory() as folder:
            tools = Path(folder)/'app/_internal/injection/tools'
            tools.mkdir(parents=True)
            healthy = SimpleNamespace(missing=[], eol=100, expired=False)
            with patch.object(update, 'check_ltk_patcher', return_value=healthy), patch.object(update, 'download_official') as download:
                self.assertFalse(update.ensure_patcher(tools, Path('game.exe')))
                download.assert_not_called()

    def test_unknown_game_does_not_replace_or_download(self):
        with tempfile.TemporaryDirectory() as folder:
            tools = Path(folder)/'app/_internal/injection/tools'
            tools.mkdir(parents=True)
            missing = SimpleNamespace(missing=['dll'], eol=None, expired=False)
            with patch.object(update, 'check_ltk_patcher', return_value=missing), patch.object(update, 'download_official') as download:
                with self.assertRaisesRegex(ValueError, 'Oyun derlemesi'):
                    update.ensure_patcher(tools, Path('missing-game.exe'))
                download.assert_not_called()

    def pair_fixture(self, folder):
        tools, source = Path(folder)/'tools', Path(folder)/'source'
        tools.mkdir()
        source.mkdir()
        for name in update.NAMES:
            (tools/name).write_bytes(b'old-'+name.encode())
            (source/name).write_bytes(b'new-'+name.encode())
        return tools, source

    def test_pair_replacement_and_durable_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            tools, source = self.pair_fixture(folder)
            valid = SimpleNamespace(missing=[], eol=100, game_build=99, expired=False)
            with patch.object(update, 'require_idle'), patch.object(update, 'check_ltk_patcher', return_value=valid):
                update.install_pair(source, tools, Path('game'), {'name': 'official'})
            for name in update.NAMES:
                self.assertEqual((tools/name).read_bytes(), (source/name).read_bytes())
                self.assertEqual(next(tools.glob('ltk-backup-*/'+name)).read_bytes(), b'old-'+name.encode())
            self.assertFalse((tools/'.ltk-update.json').exists())

    def test_second_file_failure_restores_first(self):
        with tempfile.TemporaryDirectory() as folder:
            tools, source = self.pair_fixture(folder)
            valid = SimpleNamespace(missing=[], eol=100, game_build=99, expired=False)
            real_atomic = update.atomic_write
            failed = False
            def fail_once(path, *args, **kwargs):
                nonlocal failed
                if Path(path).name == update.NAMES[1] and not failed:
                    failed = True
                    raise OSError('disk full')
                return real_atomic(path, *args, **kwargs)
            with patch.object(update, 'require_idle'), patch.object(update, 'check_ltk_patcher', return_value=valid), patch.object(update, 'atomic_write', side_effect=fail_once):
                with self.assertRaisesRegex(OSError, 'disk full'):
                    update.install_pair(source, tools, Path('game'), {})
            for name in update.NAMES:
                self.assertEqual((tools/name).read_bytes(), b'old-'+name.encode())

    def test_crash_recovery_restores_original_pair(self):
        with tempfile.TemporaryDirectory() as folder:
            tools, source = self.pair_fixture(folder)
            backup = tools/('ltk-backup-'+'a'*32)
            backup.mkdir()
            old = {}
            for name in update.NAMES:
                (backup/name).write_bytes((tools/name).read_bytes())
                old[name] = update.digest(tools/name)
                (tools/name).write_bytes(b'partial')
            (tools/'.ltk-update.json').write_text(json.dumps({'backup': backup.name, 'old': old}))
            update.recover_pair(tools)
            for name in update.NAMES:
                self.assertEqual(update.digest(tools/name), old[name])

    def test_latest_incompatible_pair_does_not_touch_original(self):
        with tempfile.TemporaryDirectory() as folder:
            tools, source = self.pair_fixture(folder)
            expired = SimpleNamespace(missing=[], eol=100, game_build=101, expired=True)
            with patch.object(update, 'require_idle'), patch.object(update, 'check_ltk_patcher', return_value=expired):
                with self.assertRaisesRegex(ValueError, 'desteklemiyor'):
                    update.install_pair(source, tools, Path('game'), {})
            self.assertEqual((tools/update.NAMES[0]).read_bytes(), b'old-'+update.NAMES[0].encode())
            self.assertEqual(list(tools.glob('ltk-backup-*')), [])

    def test_active_game_blocks_repair(self):
        with patch('psutil.process_iter', return_value=[SimpleNamespace(info={'name': 'League of Legends.exe'})]):
            with self.assertRaises(RuntimeError):
                update.require_idle()

    def test_app_updater_precedes_dependency_gate(self):
        import ast
        tree = ast.parse((Path(__file__).parents[1]/'main/__init__.py').read_text(encoding='utf-8'))
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        calls = {n.func.id: n.lineno for n in ast.walk(main) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertLess(calls['run_launcher'], calls['_check_dll_present'])


if __name__ == '__main__':
    unittest.main()
