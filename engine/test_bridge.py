from types import SimpleNamespace
import unittest
from .bridge import capture_selection


class BridgeTests(unittest.TestCase):
    def state(self, **changes):
        values = dict(phase='ChampSelect',locked_champ_id=141,ui_skin_id=141032,
                      champ_select_generation=3,ui_last_text_generation=3,
                      ui_last_text_champion_id=141,is_swiftplay_mode=False,
                      independent_selection='old')
        values.update(changes)
        return SimpleNamespace(**values)

    def test_normal_skin_choice_is_captured_without_lcu_or_runtime(self):
        state = self.state()
        choice = capture_selection(state)
        self.assertEqual(choice.skin_id,141032)
        self.assertEqual(choice.session_id,'champselect:3')
        self.assertIs(state.independent_selection,choice)

    def test_stale_or_incompatible_choice_clears_previous_request(self):
        for changes in ({'phase':'Lobby'},{'ui_skin_id':238058},
                        {'ui_last_text_generation':2},{'ui_last_text_champion_id':238},
                        {'locked_champ_id':None},{'is_swiftplay_mode':True},
                        {'champ_select_generation':True}):
            state = self.state(**changes)
            with self.subTest(changes=changes):
                self.assertIsNone(capture_selection(state))
                self.assertIsNone(state.independent_selection)

    def test_chroma_is_preserved(self):
        self.assertEqual(capture_selection(self.state(ui_skin_id=141033)).skin_id,141033)


if __name__ == '__main__':
    unittest.main()
