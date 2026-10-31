import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from .prepare import prepare
from .selection import Selection
from .test_wad import fixture


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.library, self.game, self.output = root/'library', root/'game', root/'output'
        original = self.game/'DATA/FINAL/Champions/Kayn.wad.client'
        original.parent.mkdir(parents=True)
        original.write_bytes(fixture())
        package = self.library/'141/141032/141032.fantome'
        package.parent.mkdir(parents=True)
        with zipfile.ZipFile(package, 'w') as archive:
            archive.writestr('META/info.json', '{"Name":"Kayn fixture"}')
            archive.writestr('WAD/Kayn.wad.client', fixture()[:-3]+b'xyz')
        self.selection = Selection('game-1', 141, 141032)

    def test_selected_skin_prepares_manifest_and_preserves_game(self):
        directory, manifest = prepare(self.selection, self.library, self.game, self.output)
        self.assertFalse(manifest['applied'])
        self.assertFalse(manifest['runtime_available'])
        self.assertEqual(manifest['selection']['skin_id'], 141032)
        self.assertEqual(manifest['base_skin_id'], 141000)
        self.assertEqual(manifest['archives'][0]['verified_payloads'], 1)
        self.assertEqual(json.loads((directory/'manifest.json').read_text()), manifest)
        self.assertEqual((self.game/'DATA/FINAL/Champions/Kayn.wad.client').read_bytes(), fixture())

    def test_changed_output_or_game_invalidates_preparation(self):
        from .validate import validate
        directory, manifest = prepare(self.selection,self.library,self.game,self.output)
        self.assertEqual(validate(directory,expected_selection=self.selection,game=self.game)['validated_archives'],1)
        with self.assertRaises(ValueError):
            validate(directory,expected_selection=Selection('next-game',141,141032))
        original = self.game/'DATA/FINAL/Champions/Kayn.wad.client'
        original.write_bytes(fixture()[:-3]+b'new')
        with self.assertRaises(ValueError):
            validate(directory,game=self.game)
        output = directory/'DATA/FINAL/Champions/Kayn.wad.client'
        output.write_bytes(output.read_bytes()[:-1]+b'X')
        with self.assertRaises(ValueError):
            validate(directory)

    def test_superseded_or_traversing_manifest_is_rejected(self):
        from .validate import validate
        directory, manifest = prepare(self.selection,self.library,self.game,self.output)
        manifest['state']='superseded'
        (directory/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            validate(directory)
        manifest['state']='prepared_offline'
        manifest['archives'][0]['path']='DATA/FINAL/../../../outside.wad.client'
        (directory/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            validate(directory)

    def test_failure_removes_incomplete_build(self):
        with patch('engine.prepare.build', side_effect=ValueError('broken payload')):
            with self.assertRaises(ValueError):
                prepare(self.selection, self.library, self.game, self.output)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_manifest_failure_does_not_publish_a_prepared_build(self):
        with patch('engine.prepare.write_manifest',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                prepare(self.selection,self.library,self.game,self.output)
        self.assertEqual(list(self.output.iterdir()),[])

    def test_output_inside_sources_rejected(self):
        for output in (self.game/'out', self.library/'out'):
            with self.subTest(output=output), self.assertRaises(ValueError):
                prepare(self.selection, self.library, self.game, output)
            self.assertFalse(output.exists())

    def test_missing_package_does_not_create_output(self):
        with self.assertRaises(ValueError):
            prepare(Selection('game-1', 141, 141099), self.library, self.game, self.output)
        self.assertFalse(self.output.exists())

    def test_nested_chroma_uses_selected_chroma_package(self):
        source = self.library/'141/141032/141032.fantome'
        nested = self.library/'141/141032/141033/141033.fantome'
        nested.parent.mkdir()
        nested.write_bytes(source.read_bytes())
        _, manifest = prepare(Selection('game-1',141,141033),self.library,self.game,self.output)
        self.assertEqual(manifest['selection']['skin_id'],141033)

    def test_missing_optional_voice_locale_does_not_break_visual_archive(self):
        package = self.library/'141/141032/141032.fantome'
        with zipfile.ZipFile(package,'a') as archive:
            archive.writestr('WAD/Kayn.en_US.wad.client',fixture())
        _, manifest = prepare(self.selection,self.library,self.game,self.output)
        self.assertEqual(len(manifest['archives']),1)
        self.assertEqual(manifest['skipped_optional_archives'],[
            {'archive':'WAD/Kayn.en_US.wad.client','reason':'locale_not_installed'}])

    def test_missing_non_locale_archive_aborts_entire_preparation(self):
        package = self.library/'141/141032/141032.fantome'
        with zipfile.ZipFile(package,'a') as archive:
            archive.writestr('WAD/NoSuchChampion.wad.client',fixture())
        with self.assertRaises(ValueError):
            prepare(self.selection,self.library,self.game,self.output)
        self.assertEqual(list(self.output.iterdir()),[])

    def test_ambiguous_nested_package_is_rejected(self):
        from .prepare import resolve_package
        for folder in ('one','two'):
            path = self.library/f'141/{folder}/141033.fantome'
            path.parent.mkdir()
            path.write_bytes(b'placeholder')
        with self.assertRaises(ValueError):
            resolve_package(self.library,Selection('game-1',141,141033))

    def test_base_skin_requires_no_package_or_modified_archive(self):
        _, manifest = prepare(Selection('game-1', 141, 141000), self.library, self.game, self.output)
        self.assertEqual(manifest['state'], 'base_selected')
        self.assertEqual(manifest['archives'], [])

    def test_request_identity_validation(self):
        for champion, skin in ((True, 1000), (141, True), (141, 238058), (-1, -1000)):
            with self.subTest(champion=champion, skin=skin), self.assertRaises(ValueError):
                Selection('game-1', champion, skin)
        with self.assertRaises(ValueError):
            Selection('', 141, 141032)
        for session, champion in (('game-2', 141), ('game-1', 238)):
            with self.assertRaises(ValueError):
                self.selection.require_current(session, champion)


if __name__ == '__main__':
    unittest.main()
