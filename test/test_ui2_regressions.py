"""UI persistence and acknowledgements with real boundaries, isolated storage."""
import json
import re
from types import SimpleNamespace
from unittest.mock import Mock, patch

from hub import preferences
from hub.tests.test_library import LibraryFixture


class UI2Regressions(LibraryFixture):
    def test_list_view_survives_other_preference_changes(self):
        preferences.update({'mod_view': 'list'})
        preferences.update({'theme': 'light'})
        self.assertEqual(preferences.get()['mod_view'], 'list')
        with self.assertRaises(ValueError):
            preferences.update({'mod_view': 'unknown', 'theme': 'dark'})
        self.assertEqual(preferences.get()['theme'], 'light')
        self.assertEqual(preferences.get()['mod_view'], 'list')

    def test_bootstrap_appearance_matches_persisted_preferences_without_other_settings(self):
        from hub.desktop import build_html
        preferences.update({'theme':'light', 'mod_view':'list', 'reduce_motion':True})
        html=build_html()
        bootstrap=json.loads(re.search(r'window.HUB_DATA=(.*?);</script>',html,re.S).group(1))
        self.assertEqual(bootstrap['appearance'], {
            'theme':'light', 'mod_view':'list', 'compact_cards':False, 'reduce_motion':True, 'data_saver':True,
        })

    def test_damaged_preferences_do_not_block_the_desktop_window(self):
        from hub.desktop import build_html
        with patch('hub.preferences.get',side_effect=ValueError('QA invalid settings')):
            html=build_html()
        self.assertIn('"appearance": {}', html)
        self.assertIn('id="main"', html)

    def test_settings_failure_acknowledges_the_originating_request(self):
        from pengu.communication.message_handler import MessageHandler
        sent=[]
        fake=SimpleNamespace(_is_valid_local_league_path=lambda _:False,
                             _send_settings_save_error=lambda error, request_id=None: sent.append((error,request_id)))
        with patch('config.set_config_options') as write:
            MessageHandler._handle_settings_save(fake,{'gamePath':'Q:/missing','requestId':'settings-qa-1'})
        write.assert_not_called()
        self.assertEqual(sent[0][1],'settings-qa-1')

    def test_settings_success_acknowledges_the_originating_request(self):
        from pengu.communication.message_handler import MessageHandler
        fake=SimpleNamespace(_send_settings_save_success=Mock(),_send_settings_save_error=Mock())
        with patch('config.set_config_options') as write, patch('pengu.communication.message_handler.is_registered_for_autostart',return_value=False):
            MessageHandler._handle_settings_save(fake,{'requestId':'settings-qa-2','threshold':.7})
        write.assert_called_once()
        fake._send_settings_save_success.assert_called_once_with('settings-qa-2')
        fake._send_settings_save_error.assert_not_called()

    def test_broadcast_ack_retains_request_identity_and_legacy_shape(self):
        from pengu.communication.message_handler import MessageHandler
        fake=SimpleNamespace(_send_response=Mock())
        MessageHandler._send_settings_save_success(fake,'settings-qa-3')
        self.assertEqual(json.loads(fake._send_response.call_args.args[0]), {'type':'settings-saved','success':True,'requestId':'settings-qa-3'})
        MessageHandler._send_settings_save_error(fake,'Disk full','settings-qa-4')
        self.assertEqual(json.loads(fake._send_response.call_args.args[0])['requestId'],'settings-qa-4')
        MessageHandler._send_settings_save_success(fake)
        self.assertNotIn('requestId',json.loads(fake._send_response.call_args.args[0]))
