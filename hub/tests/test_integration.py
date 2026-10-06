from types import SimpleNamespace

from hub import library
from hub.integration import apply_category_selections
from hub.tests.test_library import LibraryFixture
from utils.core import mod_historic


class CategoryIntegrationTests(LibraryFixture):
    def add(self, category, mod_id):
        metadata = dict(self.item(mod_id), category=category, champion='', champion_id=None)
        return library.import_archive(self.archive(mod_id + '.fantome'), metadata)

    def test_single_selection_categories_reach_game_preparation(self):
        state = SimpleNamespace()
        for category, attr in [('maps', 'selected_map_mod'), ('fonts', 'selected_font_mod'), ('announcers', 'selected_announcer_mod')]:
            item = self.add(category, category + '-first')
            library.enable(item['id'], True)
            apply_category_selections(state)
            self.assertEqual(getattr(state, attr)['relative_path'], item['relative_path'])
            library.enable(item['id'], False)
            apply_category_selections(state)
            self.assertIsNone(getattr(state, attr))

    def test_disabled_hub_mod_preserves_external_category_selection(self):
        self.add('fonts', 'my-font')
        external = {'relative_path': 'fonts/external', 'mod_name': 'External'}
        state = SimpleNamespace(selected_font_mod=external)
        apply_category_selections(state)
        self.assertIs(state.selected_font_mod, external)

    def test_repeated_reconciliation_does_not_duplicate_hud(self):
        self.add('ui', 'my-hud')
        library.enable('my-hud', True)
        external = {'relative_path': 'vfx/external'}
        state = SimpleNamespace(selected_other_mod=external)
        for _ in range(3):
            apply_category_selections(state)
        self.assertEqual(len(state.selected_other_mods), 2)
        self.assertIs(state.selected_other_mods[0], external)

    def test_missing_hub_files_drop_stale_selection(self):
        item = self.add('fonts', 'my-font')
        library.enable('my-font', True)
        state = SimpleNamespace()
        apply_category_selections(state)
        folder = library.mod_folder(item)
        folder.rename(folder.with_name('temporarily-moved'))
        apply_category_selections(state)
        self.assertIsNone(state.selected_font_mod)

    def test_disabling_hud_clears_legacy_history_but_keeps_external_mods(self):
        item = self.add('ui', 'my-hud')
        mod_historic.write_historic_mod('other', [item['relative_path'], 'vfx/external'])
        library.enable('my-hud', False)
        self.assertNotIn(item['relative_path'], mod_historic.get_historic_mod('other'))
        self.assertIn('vfx/external', mod_historic.get_historic_mod('other'))

    def test_removing_hub_mod_clears_its_game_preparation_selection(self):
        self.add('ui', 'my-hud')
        library.enable('my-hud', True)
        state = SimpleNamespace()
        apply_category_selections(state)
        library.remove('my-hud')
        apply_category_selections(state)
        self.assertEqual(state.selected_other_mods, [])
        self.assertIsNone(state.selected_other_mod)

    def test_old_duplicate_history_is_normalized_before_disabling(self):
        item = self.add('ui', 'my-hud')
        library.write_json(self.root / 'mod_historic.json', {
            'ui': [item['relative_path']], 'others': [item['relative_path'], 'vfx/external'], 'font': 'fonts/external'})
        library.enable('my-hud', False)
        self.assertNotIn(item['relative_path'], mod_historic.get_historic_mod('other'))
        self.assertEqual(mod_historic.get_historic_mod('vfx'), ['vfx/external'])
        self.assertEqual(mod_historic.get_historic_mod('font'), 'fonts/external')

    def test_legacy_combined_write_replaces_categories_without_duplicates(self):
        mod_historic.write_historic_mod('other', ['ui/old-hud', 'vfx/effect'])
        mod_historic.write_historic_mod('other', ['vfx/effect'])
        self.assertIsNone(mod_historic.get_historic_mod('ui'))
        self.assertIsNone(mod_historic.get_historic_mod('others'))
        self.assertEqual(mod_historic.get_historic_mod('other'), ['vfx/effect'])
        mod_historic.write_historic_mod('other', [])
        self.assertIsNone(mod_historic.get_historic_mod('other'))
