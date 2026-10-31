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
            'myTeam': [{'cellId': 0, 'assignedPosition': 'middle', 'championPickIntent': 103}], 'theirTeam': [], 'bans': {}}
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

    def test_empty_ui_list_uses_matching_backend_session(self):
        with patch.object(self.ban, 'read', side_effect=[
                self.session, [], self.session, [103, 11, 22], self.session]) as read:
            self.assertTrue(self.ban.tick(self.lcu, 'ChampSelect'))
        self.assertIn('lol-lobby-team-builder', read.call_args_list[3].args[1])
        self.assertEqual(self.lcu.s.patch.call_args.kwargs['json']['championId'], 11)

    def test_empty_backend_waits_without_guessing_from_priority(self):
        with patch.object(self.ban, 'read', side_effect=[self.session, [], self.session, []]):
            self.assertFalse(self.ban.tick(self.lcu, 'ChampSelect'))
        self.assertEqual(self.ban.status, 'bannable-champions-not-ready')
        self.lcu.s.patch.assert_not_called()

    def test_fallback_rejects_other_session_or_cell(self):
        for backend in (dict(self.session, gameId=99), dict(self.session, localPlayerCellId=5), None):
            with self.subTest(backend=backend):
                with patch.object(self.ban, 'read', side_effect=[self.session, [], backend]):
                    self.assertFalse(self.ban.tick(self.lcu, 'ChampSelect'))
        self.lcu.s.patch.assert_not_called()

    def test_fallback_still_respects_late_manual_selection(self):
        changed = deepcopy(self.session)
        changed['actions'][0][0]['championId'] = 22
        with patch.object(self.ban, 'read', side_effect=[self.session, [], self.session, [11, 22], changed]):
            self.assertFalse(self.ban.tick(self.lcu, 'ChampSelect'))
        self.lcu.s.patch.assert_not_called()

    def test_malformed_backend_list_never_bans(self):
        for available in ([True], ['11'], [0], {}):
            with self.subTest(available=available):
                with patch.object(self.ban, 'read', side_effect=[self.session, [], self.session, available]):
                    self.assertFalse(self.ban.tick(self.lcu, 'ChampSelect'))
        self.lcu.s.patch.assert_not_called()

    def test_each_pick_position_on_both_teams_targets_own_ban_action(self):
        for side in (0, 5):
            for position in range(5):
                with self.subTest(side=side, position=position):
                    cell = side + position
                    self.ban = AutoBan()
                    self.lcu.s.patch.reset_mock()
                    self.session = {'gameId': 42, 'localPlayerCellId': cell,
                        'myTeam': [{'cellId': i, 'assignedPosition': 'middle', 'championPickIntent': 0}
                                   for i in reversed(range(side, side + 5))],
                        'theirTeam': [], 'bans': {},
                        'actions': [[{'id': 100 + i, 'actorCellId': i, 'type': 'ban',
                                      'championId': 0, 'completed': False, 'isInProgress': True}
                                     for i in reversed(range(10))]]}
                    self.assertTrue(self.run_tick())
                    self.assertTrue(self.lcu.s.patch.call_args.args[0].endswith('/' + str(100 + cell)))
                    self.assertEqual(self.lcu.s.patch.call_count, 1)

    def test_negative_unselected_champion_is_eligible(self):
        self.session['actions'][0][0]['championId'] = -1
        self.assertTrue(self.run_tick())
        self.assertEqual(self.lcu.s.patch.call_args.kwargs['json'], {'championId': 11, 'completed': True})
        self.assertEqual(self.ban.status, 'ban-completed')

    def test_simultaneous_ban_group_works_for_every_position_when_only_first_is_flagged(self):
        for cell in range(10):
            with self.subTest(cell=cell):
                self.ban = AutoBan()
                self.lcu.s.patch.reset_mock()
                self.session = {'gameId': 42, 'localPlayerCellId': cell,
                    'hasSimultaneousBans': True, 'timer': {'phase': 'BAN_PICK'},
                    'myTeam': [{'cellId': cell, 'assignedPosition': 'middle'}],
                    'theirTeam': [], 'bans': {}, 'actions': [[{
                    'id': i + 100, 'actorCellId': i, 'type': 'ban', 'championId': 0,
                    'completed': False, 'isInProgress': i == 0} for i in range(10)]]}
                self.assertTrue(self.run_tick())
                self.assertTrue(self.lcu.s.patch.call_args.args[0].endswith('/' + str(cell + 100)))

    def test_group_fallback_does_not_ban_in_planning_or_sequential_draft(self):
        self.session['actions'][0][0]['isInProgress'] = False
        self.session['actions'][0].append({'id': 8, 'actorCellId': 1, 'type': 'ban',
                                         'isInProgress': True, 'completed': False, 'championId': 0})
        for simultaneous, phase in ((False, 'BAN_PICK'), (True, 'PLANNING'), (True, 'FINALIZATION')):
            self.session.update(hasSimultaneousBans=simultaneous, timer={'phase': phase})
            self.assertFalse(self.run_tick())
        self.lcu.s.patch.assert_not_called()

    def test_swap_after_success_or_timeout_never_bans_again_in_same_match(self):
        for timeout in (False, True):
            with self.subTest(timeout=timeout):
                self.ban = AutoBan()
                self.lcu.s.patch.reset_mock()
                self.lcu.s.patch.side_effect = TimeoutError() if timeout else None
                if timeout:
                    with self.assertRaises(TimeoutError): self.run_tick()
                else:
                    self.assertTrue(self.run_tick())
                self.session['actions'][0][0]['id'] += 10
                self.session['localPlayerCellId'] += 1
                self.session['myTeam'][0]['cellId'] = self.session['localPlayerCellId']
                self.session['actions'][0][0]['actorCellId'] = self.session['localPlayerCellId']
                self.ban.tick(self.lcu, None)
                self.assertFalse(self.run_tick())
                self.assertEqual(self.lcu.s.patch.call_count, 1)

    def test_waiting_reason_records_own_action_flags_without_player_names(self):
        self.session['actions'][0][0]['isInProgress'] = False
        self.session['myTeam'][0]['summonerName'] = 'private-name'
        self.assertFalse(self.run_tick())
        self.assertIn('cell=0', self.ban.status)
        self.assertIn('active=False', self.ban.status)
        self.assertNotIn('private-name', self.ban.status)

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
