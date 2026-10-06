import json
from unittest.mock import Mock, patch

from hub import guides, preferences
from hub.tests.test_library import LibraryFixture
from hub.tests.test_guides import session
from pengu.communication.message_handler import MessageHandler


class GuideBridgeTests(LibraryFixture):
    def setUp(self):
        super().setUp()
        self.handler = MessageHandler.__new__(MessageHandler)
        self.handler._send_response = Mock()

    def message(self, kind, **fields):
        self.handler._route(kind, dict(type=kind, **fields))
        return json.loads(self.handler._send_response.call_args[0][0])

    def test_status_exposes_only_guide_preferences_and_context(self):
        value = self.message('guide-request')
        self.assertEqual(set(value), {'type', 'guide', 'companion', 'enabled', 'hotkey', 'error'})
        self.assertFalse(value['enabled'])

    def test_toggle_is_shared_with_desktop(self):
        self.assertTrue(self.message('guide-toggle', enabled=True)['enabled'])
        self.assertTrue(preferences.get()['mobalytics_enabled'])

    def test_non_boolean_cannot_enable(self):
        value = self.message('guide-toggle', enabled='true')
        self.assertTrue(value['error'])
        self.assertFalse(preferences.get()['mobalytics_enabled'])

    def test_show_without_lock_has_helpful_error(self):
        preferences.update({'mobalytics_enabled': True})
        with patch('hub.companion.ensure_running') as start:
            value = self.message('guide-show', url='https://untrusted.example')
            self.assertIn('şampiyon', value['error'])
            start.assert_not_called()

    def test_show_uses_locked_champion_not_payload_url(self):
        preferences.update({'mobalytics_enabled': True})
        guides.GuideTracker().update('ChampSelect', session())
        with patch('hub.companion.ensure_running'):
            value = self.message('guide-show', url='https://untrusted.example')
        self.assertEqual(value['error'], '')
        self.assertEqual(value['guide']['pick']['champion']['id'], 11)
