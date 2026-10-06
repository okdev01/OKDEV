import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from okdev_update_helper import wait_for_install_exit
from launcher.update.update_installer import UpdateInstaller
import tempfile


class ShutdownTests(unittest.TestCase):
    def test_verified_package_helper_replaces_old_helper(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            install, payload, updates = [root/name for name in ('install', 'payload', 'updates')]
            for folder in (install, payload, updates):
                folder.mkdir()
            (install/'okdev-install.json').write_text('{}')
            (install/'OKDEV-Updater.exe').write_bytes(b'old')
            (payload/'OKDEV-Updater.exe').write_bytes(b'fixed')
            result = UpdateInstaller().prepare_updater_launch(payload, install, updates, None, None, lambda _: None)
            self.assertEqual(result['helper'].read_bytes(), b'fixed')

    def test_helper_launch_uses_external_working_directory(self):
        params = {'helper': Path('updates/helper.exe'), 'pid': 123, 'install': Path('install'),
                  'payload': Path('payload'), 'log': Path('updates/log')}
        with patch('launcher.update.update_installer.subprocess.Popen') as launch:
            self.assertTrue(UpdateInstaller().launch_updater(params, Path('install'), Path('updates'), None, None, lambda _: None))
            self.assertEqual(launch.call_args.kwargs['cwd'], Path('updates'))

    def process(self, name, exe):
        return SimpleNamespace(pid=123, info={'name': name, 'exe': str(exe)})

    def test_waits_for_install_process_to_exit(self):
        root = Path('installation').resolve()
        with patch('psutil.process_iter', side_effect=[[self.process('OKDEV.exe', root/'OKDEV.exe')], []]), patch('time.sleep') as sleep:
            wait_for_install_exit(root)
            sleep.assert_called_once()

    def test_reports_remaining_process_without_terminating_it(self):
        root = Path('installation').resolve()
        with patch('psutil.process_iter', return_value=[self.process('OKDEV.exe', root/'OKDEV.exe')]):
            with self.assertRaisesRegex(RuntimeError, 'PID 123'):
                wait_for_install_exit(root, timeout=0)

    def test_league_blocks_even_outside_installation(self):
        with patch('psutil.process_iter', return_value=[self.process('LeagueClientUx.exe', Path('game/LeagueClientUx.exe').resolve())]):
            with self.assertRaisesRegex(RuntimeError, 'League of Legends'):
                wait_for_install_exit(Path('installation'), timeout=0)

    def test_unrelated_okdev_location_does_not_block(self):
        with patch('psutil.process_iter', return_value=[self.process('OKDEV.exe', Path('other/OKDEV.exe').resolve())]):
            wait_for_install_exit(Path('installation'), timeout=0)
