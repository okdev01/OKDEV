import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from hub import library
from hub.helpers import AutoAccept


class LibraryFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('hub.library.get_user_data_dir', 'injection.mods.storage.get_user_data_dir', 'utils.core.historic.get_user_data_dir', 'utils.core.mod_historic.get_user_data_dir'):
            patcher = patch(name, return_value=self.root)
            patcher.start()
            self.addCleanup(patcher.stop)

    def archive(self, name='sample.fantome', files=None):
        p = self.root / name
        with zipfile.ZipFile(p, 'w') as z:
            for filename, data in (files or {'WAD/Ahri.wad.client': b'fixture-wad-data'}).items():
                z.writestr(filename, data)
        return p

    def item(self, mod_id='sample', **extra):
        return dict(id=mod_id, name='Test mod', champion='Ahri', champion_id=103,
                    description='Fixture only', version='1.0.0', **extra)


class LibraryTests(LibraryFixture):
    def test_import_enable_switch_disable_and_recoverable_remove(self):
        first = library.import_archive(self.archive(), self.item())
        library.enable('sample', True)
        self.assertEqual(library.active_mod(103)['relative_path'], first['relative_path'])
        self.assertIsNone(library.active_mod(18))
        second = library.import_archive(self.archive('second.zip'), self.item('second'))
        library.enable('second', True)
        self.assertFalse(library.installed()['sample']['enabled'])
        self.assertEqual(library.active_mod(103)['relative_path'], second['relative_path'])
        library.enable('second', False)
        self.assertIsNone(library.active_mod(103))
        library.remove('sample')
        self.assertNotIn('sample', library.installed())
        self.assertTrue(list((library.root() / 'removed').rglob('Ahri.wad.client')))

    def test_bad_archives_do_not_install(self):
        for name in ('../outside', 'WAD/../../outside', 'C:/outside', 'WAD/run.exe'):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    library.import_archive(self.archive(files={name: b'bad'}), self.item())
        self.assertEqual(library.installed(), {})

    def test_catalog_rejects_foreign_source_and_duplicate_ids(self):
        item = self.item(sha256='a'*64, url='https://github.com/okdev01/OKDEV/releases/download/mod-a/test.fantome')
        library.validate_catalog({'schema': 1, 'mods': [item]})
        with self.assertRaises(ValueError):
            library.validate_catalog({'schema': 1, 'mods': [item, item]})
        item['url'] = 'https://evil.example/mod.fantome'
        with self.assertRaises(ValueError):
            library.validate_catalog({'schema': 1, 'mods': [item]})

    def test_bad_hash_is_rejected_without_installing(self):
        item = self.item(sha256='0'*64, url='https://github.com/okdev01/OKDEV/releases/download/mod-a/test.fantome')
        library.write_json(library.root()/'catalog.json', {'schema': 1, 'mods': [item]})
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_content.return_value = [b'corrupted']
        with patch.object(library.requests, 'get', return_value=response), self.assertRaisesRegex(ValueError, 'doğrulanamadı'):
            library.download('sample')
        self.assertEqual(library.installed(), {})
        self.assertFalse(list(library.root().glob('*.partial')))

    def test_verified_download_imports_actual_archive(self):
        content = self.archive().read_bytes()
        item = self.item(sha256=hashlib.sha256(content).hexdigest(), url='https://github.com/okdev01/OKDEV/releases/download/mod-a/test.fantome')
        library.write_json(library.root()/'catalog.json', {'schema': 1, 'mods': [item]})
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_content.return_value = [content]
        with patch.object(library.requests, 'get', return_value=response):
            result = library.download('sample')
        self.assertTrue((self.root/'mods'/result['relative_path']/'WAD/Ahri.wad.client').is_file())

    def test_auto_accept_defaults_off_and_persists(self):
        self.assertFalse(library.settings()['auto_accept'])
        library.set_auto_accept(True)
        self.assertTrue(library.settings()['auto_accept'])


class AutoAcceptTests(unittest.TestCase):
    def test_only_pending_ready_check_is_accepted_once(self):
        lcu = SimpleNamespace(phase='Lobby', base='https://127.0.0.1:1', s=Mock(), get=Mock())
        lcu.s.post.return_value.ok = True
        accept = AutoAccept()
        self.assertFalse(accept.tick(lcu, True))
        lcu.phase = 'ReadyCheck'
        lcu.get.return_value = {'state': 'InProgress', 'playerResponse': 'None'}
        self.assertFalse(accept.tick(lcu, False))
        self.assertTrue(accept.tick(lcu, True))
        self.assertFalse(accept.tick(lcu, True))
        lcu.s.post.assert_called_once()
        lcu.phase = 'ChampSelect'
        accept.tick(lcu, True)
        lcu.phase = 'ReadyCheck'
        lcu.get.return_value['playerResponse'] = 'Declined'
        self.assertFalse(accept.tick(lcu, True))
