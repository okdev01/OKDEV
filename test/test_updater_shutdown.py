import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from okdev_update_helper import wait_for_install_exit
from okdev_update_helper import request_auxiliary_exit, claim_update_lock
from launcher.update.update_installer import UpdateInstaller, other_main_running
import tempfile


class ShutdownTests(unittest.TestCase):
    def test_duplicate_main_is_detected_but_own_ui_children_are_not(self):
        root = Path('installation').resolve()
        def process(pid, arguments):
            return SimpleNamespace(pid=pid,info={'exe':str(root/'OKDEV.exe'),'cmdline':['OKDEV.exe',*arguments]})
        with patch('os.getpid',return_value=1),patch('psutil.process_iter',return_value=[process(1,[]),process(2,['--hub']),process(3,['--guide-companion'])]):
            self.assertFalse(other_main_running(root))
        with patch('os.getpid',return_value=1),patch('psutil.process_iter',return_value=[process(2,[])]):
            self.assertTrue(other_main_running(root))
    def test_only_one_helper_can_own_update_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'apply.lock'
            first = claim_update_lock(path)
            self.assertIsNotNone(first)
            try:
                self.assertIsNone(claim_update_lock(path))
            finally:
                first.close()
            second = claim_update_lock(path)
            self.assertIsNotNone(second)
            second.close()

    def test_auxiliary_exit_is_cooperative_and_scoped_to_install(self):
        root = Path('installation').resolve()
        guide = SimpleNamespace(pid=11, info={'exe':str(root/'OKDEV.exe'), 'cmdline':['OKDEV.exe','--guide-companion']})
        hub = SimpleNamespace(pid=12, info={'exe':str(root/'OKDEV.exe'), 'cmdline':['OKDEV.exe','--hub']})
        unrelated = SimpleNamespace(pid=13, info={'exe':str(root.parent/'other/OKDEV.exe'), 'cmdline':['OKDEV.exe','--hub']})
        with patch('psutil.process_iter',return_value=[guide,hub,unrelated]),patch('hub.companion.command') as quit_guide,patch('hub.lifecycle.request_shutdown') as quit_hub:
            request_auxiliary_exit(root)
            quit_guide.assert_called_once_with('quit')
            quit_hub.assert_called_once_with(12)

    def test_other_main_app_prevents_auxiliary_exit(self):
        root = Path('installation').resolve()
        processes = [SimpleNamespace(pid=11, info={'exe':str(root/'OKDEV.exe'), 'cmdline':['OKDEV.exe','--guide-companion']}),
                     SimpleNamespace(pid=12, info={'exe':str(root/'OKDEV.exe'), 'cmdline':['OKDEV.exe']})]
        with patch('psutil.process_iter',return_value=processes),patch('hub.companion.command') as quit_guide:
            request_auxiliary_exit(root)
            quit_guide.assert_not_called()
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
