"""Replay an actual DLL refusal without starting a patcher or touching a game."""
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from injection.overlay.overlay_manager import OverlayManager


class HostRejectionTests(unittest.TestCase):
    def test_official_runtime_skin_rejection_is_not_reported_as_update_advice(self):
        reason = ('overlay verification failed, disabling overlay: wad '
                  'data/final/champions/kayn.wad.client: base-skin check: '
                  "skin0 skeleton is one of kayn's other skins' meshes")
        with patch('injection.overlay.overlay_manager.report_issue') as report:
            OverlayManager._report_ltk_patcher_failure(reason)
        self.assertEqual(report.call_args.args[0], 'LTK_SKIN_REJECTED')
        self.assertIn('Skin uygulanmadı', report.call_args.args[2])

    def test_host_refusal_reaches_the_user_diagnostics_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'diagnostics.txt'
            with patch('utils.core.issue_reporter._issues_path', return_value=path), \
                    patch('utils.core.issue_reporter._LAST', {}):
                OverlayManager._report_ltk_patcher_failure('host verification failed, refusing overlay: [VRF00000008]')
            message = path.read_text(encoding='utf-8')
            self.assertIn('Skin uygulanmadı', message)
            self.assertIn('entegrasyon', message)

    def test_dll_refusal_is_failure_even_when_host_reports_attached_and_waiting(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manager = OverlayManager(root / 'tools', root / 'mods', root / 'game')
            proc = Mock(stdin=io.StringIO(), stdout=io.StringIO(
                'status 1 injected dll attached\n'
                'status 2 waiting awaiting game exit\n'
                'dll 3 ERROR ltk_patcher_dll::verify: host verification failed, refusing overlay: [VRF00000008]\n'
                'status 4 waiting awaiting game exit\n'))
            proc.poll.return_value = None
            with patch('injection.overlay.overlay_manager.subprocess.Popen', return_value=proc), \
                    patch.object(manager, '_open_runoverlay_log', return_value=None):
                session = manager._start_ltk_patcher(root / 'host.exe', root / 'overlay')
            session['reader'].join(timeout=2)
            self.assertIn('host verification failed', session['session']['error'])
            self.assertEqual(session['session']['state'], 'waiting')
            with patch.object(manager, '_stop_ltk_patcher') as stop, \
                    patch.object(manager, '_wipe_overlay_dir'), \
                    patch('injection.overlay.overlay_manager.report_issue') as report, \
                    patch('injection.overlay.overlay_manager.time.sleep', side_effect=AssertionError('must not wait for game exit')):
                self.assertEqual(manager._run_ltk_patcher(session, root / 'overlay'), 1)
            stop.assert_called_once_with(proc)
            self.assertEqual(report.call_args.args[0], 'LTK_HOST_REJECTED')

    def test_wait_for_game_exit_returns_immediately_on_dll_failure(self):
        game, proc = Mock(), Mock()
        proc.poll.return_value = None
        OverlayManager._wait_for_game_exit(game, proc, {'state': 'waiting', 'error': 'refusing overlay'})
        game.wait.assert_not_called()
