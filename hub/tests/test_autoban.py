from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch
from hub import preferences
from hub.autoban import AutoBan
from hub.tests.test_library import LibraryFixture


class AutoBanTests(LibraryFixture):
    def setUp(self):
        super().setUp()
        preferences.update({'auto_ban_priority': [103, 11, 22], 'auto_ban_enabled': True})
        self.session = {'gameId': 42, 'localPlayerCellId': 0, 'actions': [[{
            'id': 7, 'actorCellId': 0, 'type': 'ban', 'championId': 0,
            'completed': False, 'isInProgress': True}]],
            'myTeam': [{'championPickIntent': 103}], 'theirTeam': [], 'bans': {}}
        self.lcu = SimpleNamespace(base='https://mock.invalid', s=Mock())
        self.lcu.s.patch.return_value.ok = True
        self.ban = AutoBan()

    def run_tick(self, second=None, available=None):
        with patch.object(self.ban, 'read', side_effect=[self.session, [103, 11, 22] if available is None else available,
                                                       self.session if second is None else second]):
            return self.ban.tick(self.lcu, 'ChampSelect')

    def test_first_available_priority_and_teammate_protection(self):
        self.assertTrue(self.run_tick())
        self.assertEqual(self.lcu.s.patch.call_args.kwargs['json'], {'championId': 11, 'completed': True})

    def test_negative_unselected_champion_is_eligible(self):
        self.session['actions'][0][0]['championId'] = -1
        self.assertTrue(self.run_tick())
        self.assertEqual(self.lcu.s.patch.call_args.kwargs['json'], {'championId': 11, 'completed': True})
        self.assertEqual(self.ban.status, 'ban-completed')

    def test_completed_empty_ban_is_never_changed(self):
        self.session['actions'][0][0].update(championId=-1, completed=True, isInProgress=False)
        self.assertFalse(self.run_tick())
        self.lcu.s.patch.assert_not_called()

    def test_rejected_request_is_reported_and_not_retried(self):
        self.lcu.s.patch.return_value.ok = False
        self.lcu.s.patch.return_value.status_code = 400
        self.assertFalse(self.run_tick())
        self.assertEqual(self.ban.status, 'request-rejected-400')
        self.assertFalse(self.run_tick())
        self.assertEqual(self.lcu.s.patch.call_count, 1)

    def test_late_hover_uses_next_candidate(self):
        second = deepcopy(self.session)
        second['myTeam'].append({'championPickIntent': 11})
        self.assertTrue(self.run_tick(second))
        self.assertEqual(self.lcu.s.patch.call_args.kwargs['json']['championId'], 22)

    def test_manual_selection_is_not_overwritten(self):
        second = deepcopy(self.session)
        second['actions'][0][0]['championId'] = 22
        self.assertFalse(self.run_tick(second))
        self.lcu.s.patch.assert_not_called()

    def test_wrong_actor_phase_completed_and_inactive_never_write(self):
        for field, value in [('actorCellId', 1), ('type', 'pick'), ('completed', True), ('isInProgress', False)]:
            original = self.session['actions'][0][0][field]
            self.session['actions'][0][0][field] = value
            self.assertFalse(self.run_tick())
            self.session['actions'][0][0][field] = original
        self.assertFalse(self.ban.tick(self.lcu, 'InProgress'))
        self.lcu.s.patch.assert_not_called()

    def test_unavailable_and_banned_are_skipped(self):
        self.session['bans'] = {'theirTeamBans': [11]}
        self.assertTrue(self.run_tick(available=[11, 22]))
        self.assertEqual(self.lcu.s.patch.call_args.kwargs['json']['championId'], 22)

    def test_no_candidate_does_nothing(self):
        self.assertFalse(self.run_tick(available=[103]))
        self.lcu.s.patch.assert_not_called()

    def test_duplicate_and_timeout_are_not_retried_after_disconnect(self):
        self.lcu.s.patch.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            self.run_tick()
        self.ban.tick(self.lcu, None)
        self.assertFalse(self.run_tick())
        self.assertEqual(self.lcu.s.patch.call_count, 1)

    def test_new_game_can_ban_again(self):
        self.run_tick()
        self.session['gameId'] = 43
        self.assertTrue(self.run_tick())
        self.assertEqual(self.lcu.s.patch.call_count, 2)

    def test_disable_between_reads_cancels(self):
        prefs = preferences.get()
        with patch.object(preferences, 'get', side_effect=[prefs, dict(prefs, auto_ban_enabled=False)]):
            self.assertFalse(self.run_tick())
        self.lcu.s.patch.assert_not_called()

    def test_defaults_and_invalid_preferences(self):
        preferences.update({'auto_ban_enabled': False, 'auto_ban_priority': []})
        for values in ([103, 103], [True], [999999], [103] * 11, 'Ahri'):
            with self.assertRaises(ValueError):
                preferences.update({'auto_ban_priority': values})
        with self.assertRaises(ValueError):
            preferences.update({'auto_ban_enabled': True})
        self.assertFalse(preferences.get()['auto_ban_enabled'])
