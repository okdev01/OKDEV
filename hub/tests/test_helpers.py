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

    def test_lcu_failure_clears_stale_connection_state(self):
        self.lcu.refresh_if_needed.side_effect = OSError()
        helpers.tick_helpers(self.lcu, self.accept, self.tracker, self.log)
        self.assertFalse(self.tracker.update.call_args.kwargs['connected'])
        self.assertIsNone(self.tracker.update.call_args.args[0])
