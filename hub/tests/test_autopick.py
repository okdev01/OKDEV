from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

from hub import preferences, draft
from hub.autoban import AutoBan
from hub.autopick import AutoPick
from hub.tests.test_library import LibraryFixture


class LaneDraftTests(LibraryFixture):
    def setUp(self):
        super().setUp()
        self.profiles = deepcopy(preferences.DEFAULTS['lane_profiles'])
        self.profiles['mid'] = {'pick': [103, 99, 11], 'ban': [238, 25]}
        self.profiles['support'] = {'pick': [25, 89], 'ban': [11]}
        preferences.update({'lane_profiles': self.profiles, 'lane_automation': True,
                            'auto_pick_enabled': True, 'auto_ban_enabled': True})
        self.session = {'gameId': 1, 'localPlayerCellId': 0,
                        'myTeam': [{'cellId': 0, 'championId': 0, 'assignedPosition': 'middle', 'championPickIntent': 0}],
                        'theirTeam': [], 'bans': {}, 'actions': [[{'id': 4, 'actorCellId': 0,
                        'type': 'pick', 'championId': -1, 'isInProgress': True, 'completed': False}]]}
        self.lcu = SimpleNamespace(base='https://mock.invalid', s=Mock())
        self.lcu.s.patch.return_value.ok = True
        self.pick = AutoPick()

    def tick(self, second=None, available=None):
        available = [103, 99, 11] if available is None else available
        with patch.object(self.pick, 'read', side_effect=[self.session, [103, 99, 11], available,
                                                       self.session if second is None else second]):
            return self.pick.tick(self.lcu, 'ChampSelect')

    def test_assigned_lane_picks_and_locks_first_available(self):
        self.assertTrue(self.tick())
        self.assertEqual(self.lcu.s.patch.call_args.kwargs['json'], {'championId': 103, 'completed': True})

    def test_unavailable_or_recently_taken_champion_uses_next(self):
        self.assertTrue(self.tick(available=[99, 11]))
        self.assertEqual(self.lcu.s.patch.call_args.kwargs['json']['championId'], 99)

    def test_teammate_hover_and_enemy_pick_are_protected(self):
        self.session['myTeam'].append({'cellId': 1, 'championPickIntent': 103})
        self.session['theirTeam'].append({'championId': 99})
        self.assertTrue(self.tick())
        self.assertEqual(self.lcu.s.patch.call_args.kwargs['json']['championId'], 11)

    def test_late_manual_pick_never_gets_overwritten(self):
        second = deepcopy(self.session)
        second['actions'][0][0]['championId'] = 99
        self.assertFalse(self.tick(second))
        self.lcu.s.patch.assert_not_called()

    def test_no_role_aram_empty_role_list_or_not_our_turn_do_nothing(self):
        original = deepcopy(self.session)
        for change in ('unknown', 'aram', 'empty', 'other-turn', 'completed'):
            self.session = deepcopy(original)
            if change == 'unknown': self.session['myTeam'][0]['assignedPosition'] = ''
            if change == 'aram': self.session['benchEnabled'] = True
            if change == 'empty': self.session['myTeam'][0]['assignedPosition'] = 'top'
            if change == 'other-turn': self.session['actions'][0][0]['actorCellId'] = 1
            if change == 'completed': self.session['actions'][0][0]['completed'] = True
            self.assertFalse(self.tick())
        self.lcu.s.patch.assert_not_called()

    def test_role_or_match_change_before_patch_waits_for_next_tick(self):
        for field in ('role', 'game'):
            second = deepcopy(self.session)
            if field == 'role': second['myTeam'][0]['assignedPosition'] = 'utility'
            else: second['gameId'] = 2
            self.assertFalse(self.tick(second))
        self.lcu.s.patch.assert_not_called()

    def test_disable_between_reads_cancels_request(self):
        prefs = preferences.get()
        with patch.object(preferences, 'get', side_effect=[prefs, dict(prefs, auto_pick_enabled=False)]):
            self.assertFalse(self.tick())
        self.lcu.s.patch.assert_not_called()

    def test_timeout_does_not_repeat_after_disconnect(self):
        self.lcu.s.patch.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError): self.tick()
        self.pick.tick(self.lcu, None)
        self.assertFalse(self.tick())
        self.assertEqual(self.lcu.s.patch.call_count, 1)

    def test_next_match_can_pick_again(self):
        self.assertTrue(self.tick())
        self.pick.tick(self.lcu, 'Lobby')
        self.assertTrue(self.tick())
        self.assertEqual(self.lcu.s.patch.call_count, 2)

    def test_lane_ban_uses_its_list_and_unknown_role_never_uses_general(self):
        preferences.update({'auto_ban_priority': [11]})
        self.session['actions'][0][0]['type'] = 'ban'
        ban = AutoBan()
        with patch.object(ban, 'read', side_effect=[self.session, [238, 25, 11], self.session]):
            self.assertTrue(ban.tick(self.lcu, 'ChampSelect'))
        self.assertEqual(self.lcu.s.patch.call_args.kwargs['json']['championId'], 238)
        self.lcu.s.patch.reset_mock()
        self.session['myTeam'][0]['assignedPosition'] = ''
        with patch.object(ban, 'read', return_value=self.session):
            self.assertFalse(ban.tick(self.lcu, 'ChampSelect'))
        self.lcu.s.patch.assert_not_called()

    def test_lane_aliases(self):
        for raw, expected in [('TOP','top'),('jungle','jungle'),('middle','mid'),('bottom','adc'),('utility','support'),('','')]:
            self.session['myTeam'][0]['assignedPosition'] = raw
            self.assertEqual(draft.assigned_lane(self.session) or '', expected)

    def test_unknown_role_does_not_use_legacy_general_ban_list(self):
        preferences.update({'lane_automation': False, 'auto_ban_priority': [11]})
        self.session['myTeam'][0]['assignedPosition'] = ''
        self.assertEqual(draft.priority_for(preferences.get(), self.session, 'ban'), [])

    def test_planned_pick_pool_is_protected_even_without_a_hover(self):
        self.profiles['mid']['ban'] = [103, 238]
        preferences.update({'lane_profiles': self.profiles})
        self.assertEqual(draft.priority_for(preferences.get(), self.session, 'ban'), [238])
        preferences.update({'auto_pick_enabled': False})
        self.assertEqual(draft.priority_for(preferences.get(), self.session, 'ban'), [103, 238])

    def test_invalid_profiles_rejected_without_losing_saved_preferences(self):
        before = preferences.get()
        for profiles in ({}, {'top': []}, {**self.profiles, 'unknown': {'pick': [], 'ban': []}},
                         {**self.profiles, 'top': {'pick': [True], 'ban': []}}):
            with self.assertRaises(ValueError): preferences.update({'lane_profiles': profiles})
            self.assertEqual(preferences.get(), before)

    def test_defaults_do_not_share_mutable_profiles(self):
        first = preferences.get()
        first['lane_profiles']['top']['pick'].append(99)
        self.assertEqual(preferences.get()['lane_profiles']['top']['pick'], [])
