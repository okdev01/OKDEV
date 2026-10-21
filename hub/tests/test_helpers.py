from types import SimpleNamespace
from unittest.mock import Mock, patch

from hub import companion, guides, helpers, preferences
from hub.tests.test_library import LibraryFixture


class HelperIsolationTests(LibraryFixture):
    def setUp(self):
        super().setUp()
        self.lcu = SimpleNamespace(ok=True, phase='ReadyCheck', refresh_if_needed=Mock())
        self.accept, self.tracker, self.log = Mock(), Mock(), Mock()
        self.tracker.update.return_value = ({'pick': None}, [])

    def test_companion_start_failure_does_not_prevent_ready_check_or_state(self):
        preferences.update({'mobalytics_enabled': True})
        with patch.object(companion, 'ensure_running', side_effect=OSError()):
            helpers.tick_helpers(self.lcu, self.accept, self.tracker, self.log)
        self.accept.tick.assert_called_once()
        self.tracker.update.assert_called_once()
        self.assertIsNone(self.tracker.shown_key)

    def test_startup_cooldown_keeps_locked_pick_eligible_for_retry(self):
        preferences.update({'mobalytics_enabled': True})
        self.tracker.shown_key = (11, 'jungle')
        with patch.object(companion, 'ensure_running', return_value=False):
            helpers.tick_helpers(self.lcu, self.accept, self.tracker, self.log)
        self.assertIsNone(self.tracker.shown_key)

    def test_failed_ready_check_does_not_prevent_guide_state(self):
        self.accept.tick.side_effect = OSError()
        helpers.tick_helpers(self.lcu, self.accept, self.tracker, self.log)
        self.tracker.update.assert_called_once()

    def test_failed_ban_does_not_prevent_other_helpers(self):
        ban = Mock()
        ban.tick.side_effect = TimeoutError()
        helpers.tick_helpers(self.lcu, self.accept, self.tracker, self.log, ban)
        self.accept.tick.assert_called_once()
        self.tracker.update.assert_called_once()

    def test_lcu_failure_clears_stale_connection_state(self):
        self.lcu.refresh_if_needed.side_effect = OSError()
        helpers.tick_helpers(self.lcu, self.accept, self.tracker, self.log)
        self.assertFalse(self.tracker.update.call_args.kwargs['connected'])
        self.assertIsNone(self.tracker.update.call_args.args[0])

    def test_midgame_start_recovers_champion_without_show_command(self):
        preferences.update({'mobalytics_enabled': True})
        self.lcu.phase = 'InProgress'
        self.lcu.current_summoner = {'summonerId': 8}
        self.lcu.game_session = {'gameData': {'teamOne': [{'summonerId': 8, 'championId': 11}]}}
        tracker = guides.GuideTracker()
        with patch.object(companion, 'ensure_running', return_value=True), patch.object(companion, 'command') as command:
            helpers.tick_helpers(self.lcu, self.accept, tracker, self.log)
        self.assertEqual(tracker.pick['champion']['id'], 11)
        self.assertEqual([c.args[0] for c in command.call_args_list], ['hide'])
