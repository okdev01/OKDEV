from hub import guides, library, preferences
from hub.tests.test_library import LibraryFixture


def session(champion=11, completed=True, role='jungle', cell=1):
    return {'localPlayerCellId': cell, 'myTeam': [{'cellId': cell, 'championId': champion, 'assignedPosition': role}],
            'actions': [[{'actorCellId': cell, 'type': 'pick', 'completed': completed, 'championId': champion}]]}


class GuideTests(LibraryFixture):
    def setUp(self):
        super().setUp()
        self.now = 1000
        self.tracker = guides.GuideTracker(clock=lambda: self.now)
        self.prefs = dict(preferences.DEFAULTS, mobalytics_enabled=True)

    def update(self, phase='ChampSelect', value=None, connected=True):
        return self.tracker.update(phase, value, connected, self.prefs)

    def test_master_yi_lock_build_has_correct_role(self):
        data, actions = self.update(value=session())
        self.assertEqual(actions, ['show'])
        self.assertEqual(data['pick']['url'], 'https://mobalytics.gg/lol/champions/masteryi/build/jungle')

    def test_hover_never_opens_a_guide(self):
        data, actions = self.update(value=session(completed=False))
        self.assertIsNone(data['pick'])
        self.assertEqual(actions, [])

    def test_aram_assignment_uses_aram_build_instead_of_summoners_rift(self):
        value = session()
        value.update(actions=[], benchEnabled=True)
        data, actions = self.update(value=value)
        self.assertEqual(data['pick']['role'], 'aram')
        self.assertEqual(data['pick']['role_label'], 'ARAM')
        self.assertEqual(data['pick']['url'], 'https://mobalytics.gg/lol/champions/masteryi/aram-builds')
        self.assertEqual(actions, ['show'])

    def test_aram_bench_swap_prepares_the_new_champion(self):
        value = session()
        value.update(actions=[], benchEnabled=True)
        self.update(value=value)
        value['myTeam'][0]['championId'] = 99
        data, actions = self.update(value=value)
        self.assertEqual(data['pick']['url'], 'https://mobalytics.gg/lol/champions/lux/aram-builds')
        self.assertEqual(actions, ['show'])

    def test_team_mate_lock_is_not_own_lock(self):
        value = session()
        value['actions'][0][0]['actorCellId'] = 2
        self.assertIsNone(guides.locked_pick(value))

    def test_same_champion_does_not_reopen_each_poll(self):
        self.update(value=session())
        for _ in range(5):
            self.assertEqual(self.update(value=session())[1], [])

    def test_trade_uses_current_owned_champion(self):
        self.update(value=session())
        value = session()
        value['myTeam'][0]['championId'] = 99
        data, actions = self.update(value=value)
        self.assertEqual(data['pick']['champion']['name'], 'Lux')
        self.assertEqual(actions, ['show'])

    def test_in_game_hides_once_and_keeps_correct_guide(self):
        self.update(value=session())
        data, actions = self.update('InProgress')
        self.assertEqual(actions, ['hide'])
        self.assertEqual(data['pick']['champion']['id'], 11)
        self.assertEqual(self.update('InProgress')[1], [])

    def test_next_game_same_champion_opens_again(self):
        self.update(value=session())
        self.update('InProgress')
        self.update('Lobby')
        self.assertEqual(self.update(value=session())[1], ['show'])

    def test_disabling_prevents_opening_and_reenabling_can_show(self):
        self.prefs['mobalytics_enabled'] = False
        self.assertEqual(self.update(value=session())[1], ['disable'])
        self.prefs['mobalytics_enabled'] = True
        self.assertEqual(self.update(value=session())[1], ['show'])

    def test_manual_only_prepares_without_showing(self):
        self.prefs['mobalytics_auto_show'] = False
        self.assertEqual(self.update(value=session())[1], ['prepare'])

    def test_transient_session_error_does_not_clear_immediately(self):
        self.update(value=session())
        self.assertIsNotNone(self.update()[0]['pick'])
        self.update()
        self.assertIsNone(self.update()[0]['pick'])

    def test_disconnect_clears_previous_player_context(self):
        self.update(value=session())
        data, actions = self.update(None, connected=False)
        self.assertIsNone(data['pick'])
        self.assertEqual(actions, ['hide'])

    def test_stale_disk_context_is_not_used_for_next_game(self):
        self.update(value=session())
        self.assertIsNotNone(guides.read_state(now=self.now)['pick'])
        self.assertIsNone(guides.read_state(now=self.now + 21)['pick'])

    def test_aram_assigned_champion_has_aram_page(self):
        value = session(role='')
        value.update(actions=[], benchEnabled=True)
        self.assertEqual(guides.locked_pick(value)['url'], 'https://mobalytics.gg/lol/champions/masteryi/aram-builds')

    def test_unknown_and_malformed_sessions_are_ignored(self):
        for value in (None, [], {}, session(999999), dict(session(), actions='bad'), dict(session(), localPlayerCellId=-1)):
            self.assertIsNone(guides.locked_pick(value))

    def test_public_site_aliases(self):
        for champion_id, slug in ((62, 'monkeyking'), (20, 'nunu'), (888, 'renata'), (145, 'kaisa')):
            self.assertIn('/' + slug + '/', guides.build_url(champion_id))

    def test_tampered_persisted_url_is_rebuilt(self):
        data, _ = self.update(value=session())
        data['pick']['url'] = 'https://example.invalid'
        library.write_json(library.root() / 'guide.json', data)
        self.assertIn('https://mobalytics.gg/', guides.read_state(now=self.now)['pick']['url'])

    def test_preferences_preserve_favorites_and_existing_settings(self):
        library.set_favorite('sample', True)
        library.set_auto_accept(True)
        preferences.update({'mobalytics_enabled': True, 'theme': 'light'})
        self.assertEqual(library.settings(), {'favorites': ['sample'], 'auto_accept': True})
        self.assertTrue(preferences.get()['mobalytics_enabled'])

    def test_invalid_preference_update_is_atomic(self):
        with self.assertRaises(ValueError):
            preferences.update({'mobalytics_enabled': True, 'mobalytics_hotkey': 'invalid'})
        self.assertFalse(preferences.get()['mobalytics_enabled'])
