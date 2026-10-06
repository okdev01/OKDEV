from unittest.mock import patch

from hub import companion, guides, preferences
from hub.tests.test_library import LibraryFixture
from hub.tests.test_guides import session


class CompanionTests(LibraryFixture):
    def setUp(self):
        super().setUp()
        self.machine = companion.WindowState()
        self.pick = guides.locked_pick(session())

    def value(self, action='show', identity='one', **extra):
        return dict(id=identity, action=action, pick=self.pick, created_at=1000, **extra)

    def test_first_show_navigates_and_then_shows(self):
        self.assertEqual(self.machine.apply(self.value(), now=1000), [
            ('navigate', 'https://mobalytics.gg/lol/champions/masteryi/build/jungle'), ('show', None)])

    def test_hotkey_hide_does_not_replay_previous_disk_show(self):
        disk = self.value()
        self.machine.apply(disk, now=1000)
        self.machine.apply(self.value('hide', 'hotkey'), now=1001)
        self.assertEqual(self.machine.apply(disk, now=1002), [])
        self.assertFalse(self.machine.visible)

    def test_prepare_keeps_window_hidden(self):
        self.assertEqual(len(self.machine.apply(self.value('prepare'), now=1000)), 1)
        self.assertFalse(self.machine.visible)

    def test_same_build_reopens_without_reloading(self):
        self.machine.apply(self.value(), now=1000)
        self.machine.apply(self.value('hide', 'two'), now=1000)
        self.assertEqual(self.machine.apply(self.value(identity='three'), now=1000), [('show', None)])

    def test_stale_or_future_command_does_not_show(self):
        for now in (900, 1031):
            self.assertEqual(companion.WindowState().apply(self.value(), now=now), [])

    def test_untrusted_url_is_reconstructed(self):
        self.pick['url'] = 'file:///C:/private'
        events = self.machine.apply(self.value(), now=1000)
        self.assertTrue(events[0][1].startswith('https://mobalytics.gg/'))

    def test_invalid_pick_is_ignored(self):
        for pick in (None, {}, {'champion': {'id': True}}, {'champion': {'id': 999999}}):
            value = self.value()
            value['pick'] = pick
            self.assertEqual(companion.WindowState().apply(value, now=1000), [])

    def test_disabled_feature_cannot_launch(self):
        with patch.object(companion.subprocess, 'Popen') as launch:
            self.assertFalse(companion.ensure_running())
            with self.assertRaises(ValueError):
                companion.command('show', self.pick)
            launch.assert_not_called()

    def test_enabled_command_is_written_without_running_gui_in_test(self):
        preferences.update({'mobalytics_enabled': True})
        with patch.object(companion, 'ensure_running') as launch:
            companion.command('show', self.pick)
            launch.assert_called_once()
        value = companion.library.read_json(companion.library.root() / 'companion-command.json', {})
        self.assertEqual(value['pick']['champion']['id'], 11)

    def test_hide_does_not_launch_process(self):
        with patch.object(companion, 'ensure_running') as launch:
            companion.command('hide')
            launch.assert_not_called()

    def test_panel_fits_secondary_monitor_with_negative_coordinates(self):
        x, y, w, h = companion.window_rectangle((-1920, 0, 0, 1040), 'right')
        self.assertEqual((x, w), (-486, 470))
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(y + h, 1040)
        self.assertEqual(companion.window_rectangle((-1920, 0, 0, 1040), 'left')[0], -1904)

    def test_panel_fits_small_work_area(self):
        x, y, w, h = companion.window_rectangle((0, 40, 800, 640), 'right')
        self.assertEqual(h, 568)
        self.assertGreaterEqual(y, 40)
        self.assertLessEqual(y + h, 640)

    def test_user_can_choose_compact_or_wide_panel(self):
        self.assertEqual(companion.window_rectangle((0, 0, 1920, 1040), 'right', 'compact')[2:], (400, 560))
        self.assertEqual(companion.window_rectangle((0, 0, 1920, 1040), 'right', 'wide')[2:], (600, 800))
        self.assertEqual(companion.window_rectangle((0, 0, 1920, 1040), 'right', 'unknown')[2:], (470, 720))
