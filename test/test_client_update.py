from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import okdev_client_update as client_update


class ClientUpdateTests(unittest.TestCase):
    def client(self, phase='Lobby'):
        session = Mock()
        session.get.return_value = SimpleNamespace(status_code=200, json=lambda: phase)
        session.post.return_value = SimpleNamespace(status_code=204)
        return SimpleNamespace(ok=True, base='https://127.0.0.1:12345', session=session)

    def test_only_idle_lobby_and_end_of_game_are_safe(self):
        for phase in ['None', 'Lobby', 'EndOfGame', 'Matchmaking', 'ReadyCheck', 'ChampSelect', 'InProgress', 'Reconnect', 'Unknown']:
            client = self.client(phase)
            with self.subTest(phase=phase), patch.object(client_update, 'process_names', return_value={'leagueclient.exe','leagueclientux.exe'}), patch.object(client_update, 'connection', return_value=client):
                self.assertEqual(client_update.safe_to_update(), phase in client_update.SAFE_PHASES)
                client.session.post.assert_not_called()

    def test_game_process_overrides_safe_lobby_phase(self):
        for name in client_update.GAME_NAMES:
            with self.subTest(name=name), patch.object(client_update, 'process_names', return_value={name}), patch.object(client_update, 'connection') as connect:
                self.assertFalse(client_update.safe_to_update())
                connect.assert_not_called()

    def test_closed_client_needs_no_lcu(self):
        with patch.object(client_update, 'process_names', return_value=set()), patch.object(client_update, 'connection') as connect:
            self.assertTrue(client_update.safe_to_update())
            connect.assert_not_called()

    def test_unknown_client_state_is_deferred(self):
        with patch.object(client_update, 'process_names', return_value={'leagueclientux.exe'}), patch.object(client_update, 'connection', return_value=SimpleNamespace(ok=False,session=Mock())):
            self.assertFalse(client_update.safe_to_update())

    def test_pause_and_resume_keep_backend_alive(self):
        with tempfile.TemporaryDirectory() as folder:
            marker=Path(folder)/'resume.json'
            names={'leagueclient.exe','leagueclientux.exe','leagueclientuxrender.exe'}
            client=self.client()
            def post(url,**kwargs):
                if url.endswith('/kill-ux'):
                    self.assertTrue(marker.exists())
                    names.difference_update(client_update.UX_NAMES)
                elif url.endswith('/launch-ux'):
                    names.add('leagueclientux.exe')
                return SimpleNamespace(status_code=204)
            client.session.post.side_effect=post
            with patch.object(client_update,'process_names',side_effect=lambda:set(names)), patch.object(client_update,'connection',return_value=client):
                guard=client_update.ClientPause(marker)
                guard.pause()
                self.assertEqual(names,{'leagueclient.exe'})
                guard.resume()
            self.assertFalse(marker.exists())
            self.assertIn('leagueclient.exe',names)
            self.assertEqual([c.args[0].split('/')[-1] for c in client.session.post.call_args_list],['kill-ux','launch-ux'])

    def test_phase_change_prevents_pausing(self):
        with tempfile.TemporaryDirectory() as folder:
            client=self.client('ChampSelect')
            with patch.object(client_update,'process_names',return_value={'leagueclientux.exe'}), patch.object(client_update,'connection',return_value=client):
                with self.assertRaises(RuntimeError):
                    client_update.ClientPause(Path(folder)/'resume.json').pause()
            client.session.post.assert_not_called()

    def test_failed_close_request_still_recovers_closed_ux(self):
        with tempfile.TemporaryDirectory() as folder:
            marker=Path(folder)/'resume.json'
            names={'leagueclient.exe','leagueclientux.exe'}
            client=self.client()
            def post(url,**kwargs):
                if url.endswith('kill-ux'):
                    names.discard('leagueclientux.exe')
                    raise TimeoutError('reply lost after UX closed')
                names.add('leagueclientux.exe')
                return SimpleNamespace(status_code=204)
            client.session.post.side_effect=post
            with patch.object(client_update,'process_names',side_effect=lambda:set(names)), patch.object(client_update,'connection',return_value=client):
                guard=client_update.ClientPause(marker)
                with self.assertRaises(TimeoutError):guard.pause()
                guard.resume()
            self.assertFalse(marker.exists())
            self.assertIn('leagueclientux.exe',names)

    def test_recovery_launches_only_missing_ux(self):
        with tempfile.TemporaryDirectory() as folder:
            marker=Path(folder)/'resume.json';marker.write_text('{"resume_ux":true}')
            with patch.object(client_update,'process_names',return_value={'leagueclientux.exe'}),patch.object(client_update,'connection') as connect:
                client_update.recover_client(marker)
                connect.assert_not_called()
            self.assertFalse(marker.exists())

    def test_runtime_sync_preserves_user_settings_and_plugin_switches(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);bundled=root/'install/_internal/Pengu Loader';runtime=root/'data/Pengu Loader'
            (bundled/'plugins/Disabled').mkdir(parents=True);(runtime/'plugins/Disabled').mkdir(parents=True)
            (bundled/'core.dll').write_bytes(b'new core')
            (bundled/'config').write_text('bundled config')
            (bundled/'datastore').write_text('bundled settings')
            (runtime/'config').write_text('user config')
            (runtime/'datastore').write_text('user settings')
            (runtime/'plugins/Disabled/index.js_').write_text('disabled')
            (bundled/'plugins/Disabled/index.js').write_text('new plugin')
            with patch('utils.core.paths.get_user_data_dir',return_value=root/'data'):
                client_update.sync_runtime(root/'install')
            self.assertEqual((runtime/'config').read_text(),'user config')
            self.assertEqual((runtime/'datastore').read_text(),'user settings')
            self.assertEqual((runtime/'core.dll').read_bytes(),b'new core')
            self.assertFalse((runtime/'plugins/Disabled/index.js').exists())
            self.assertTrue((runtime/'plugins/Disabled/index.js_').exists())


if __name__=='__main__':unittest.main()
