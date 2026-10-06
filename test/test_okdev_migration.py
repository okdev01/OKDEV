import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from utils.core.data_migration import migrate_legacy_data
from okdev_update_helper import apply_update
from launcher.update.github_client import GitHubClient
from launcher.update.update_installer import UpdateInstaller
from launcher.update.update_sequence import UpdateSequence
from party.protocol.token_codec import PartyToken


class MigrationTests(unittest.TestCase):
    def test_data_copied_original_retained_and_existing_target_untouched(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            old = base/'Rose';old.mkdir()
            (old/'config.ini').write_text('[General]\ninstalled_version=1.4.4\nupdate_retry_count=2\nlanguage=tr\n', encoding='utf-8')
            (old/'party_keys.json').write_text('{"123":"secret"}')
            (old/'rose.lock').write_text('active')
            plugins=old/'Pengu Loader/plugins/ROSE-UI';plugins.mkdir(parents=True)
            (plugins/'index.js_').write_text('disabled')
            new=base/'OKDEV'
            migrate_legacy_data(new)
            self.assertTrue((old/'config.ini').exists())
            self.assertEqual((new/'party_keys.json').read_text(), '{"123":"secret"}')
            migrated = (new/'config.ini').read_text(encoding='utf-16' if os.name == 'nt' else 'utf-8')
            self.assertNotIn('installed_version', migrated)
            self.assertIn('language = tr', migrated)
            self.assertFalse((new/'rose.lock').exists())
            self.assertTrue((new/'Pengu Loader/plugins/OKDEV-UI/index.js_').exists())
            (new/'party_keys.json').write_text('new-user-state')
            migrate_legacy_data(new)
            self.assertEqual((new/'party_keys.json').read_text(), 'new-user-state')

    def test_legacy_party_token_remains_valid(self):
        token = PartyToken(summoner_id=123, encryption_key=b'x'*32, timestamp=1)
        encoded=token.encode()
        self.assertTrue(encoded.startswith('OKDEV:'))
        self.assertEqual(PartyToken.decode('ROSE:'+encoded.split(':',1)[1]).summoner_id,123)

    def test_unicode_legacy_paths_survive_migration(self):
        with tempfile.TemporaryDirectory() as temp:
            old = Path(temp) / 'Rose'
            old.mkdir()
            original = '[General]\nleaguepath=C:\\测试\\Игрок\\Çağrı\nloaderpath=old-loader\n'
            (old / 'config.ini').write_text(original, encoding='utf-16')
            new = Path(temp) / 'OKDEV'
            migrate_legacy_data(new)
            migrated = (new / 'config.ini').read_text(encoding='utf-16' if os.name == 'nt' else 'utf-8')
            self.assertIn('C:\\测试\\Игрок\\Çağrı', migrated)
            self.assertNotIn('loaderpath', migrated)
            self.assertEqual((old / 'config.ini').read_text(encoding='utf-16'), original)


class UpdateTests(unittest.TestCase):
    def fixture(self, root):
        install=root/'OKDEV';install.mkdir()
        (install/'OKDEV.exe').write_bytes(b'old')
        (install/'okdev-install.json').write_text(json.dumps({'install_id':'fixed-id','version':'1.0.0'}))
        tools=install/'_internal/injection/tools';tools.mkdir(parents=True)
        (tools/'ltk_patcher_dll.dll').write_bytes(b'user-patcher')
        (install/'config.ini').write_text('user-settings')
        payload=root/'payload';payload.mkdir()
        (payload/'OKDEV.exe').write_bytes(b'new')
        (payload/'okdev-update.json').write_text(json.dumps({'app':'OKDEV','version':'1.1.0'}))
        return install,payload

    def test_transaction_preserves_patcher_settings_and_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            install,payload=self.fixture(Path(temp))
            (payload/'config.ini').write_text('bad-defaults')
            old_plugin = install/'_internal/Pengu Loader/plugins/ROSE-UI'
            old_plugin.mkdir(parents=True)
            (old_plugin/'index.js').write_text('legacy rose icon')
            new_plugin = payload/'_internal/Pengu Loader/plugins/OKDEV-UI'
            new_plugin.mkdir(parents=True)
            (new_plugin/'index.js').write_text('new OK icon')
            backup=apply_update(install,payload)
            self.assertFalse(old_plugin.exists())
            self.assertTrue((backup/'_internal/Pengu Loader/plugins/ROSE-UI/index.js').exists())
            self.assertTrue((install/'_internal/Pengu Loader/plugins/OKDEV-UI/index.js').exists())
            self.assertEqual((install/'OKDEV.exe').read_bytes(),b'new')
            self.assertEqual((backup/'OKDEV.exe').read_bytes(),b'old')
            self.assertEqual((install/'_internal/injection/tools/ltk_patcher_dll.dll').read_bytes(),b'user-patcher')
            self.assertEqual((install/'config.ini').read_text(),'user-settings')
            self.assertEqual(json.loads((install/'okdev-install.json').read_text())['install_id'],'fixed-id')

    def test_failed_commit_restores_previous_installation(self):
        with tempfile.TemporaryDirectory() as temp:
            install,payload=self.fixture(Path(temp))
            rename=Path.rename
            def fail_commit(path,target):
                if path.name.startswith('.okdev-update-'):
                    raise OSError('simulated filesystem lock')
                return rename(path,target)
            with patch.object(Path,'rename',fail_commit), self.assertRaises(OSError):
                apply_update(install,payload)
            self.assertEqual((install/'OKDEV.exe').read_bytes(),b'old')

    def test_only_named_okdev_asset_on_owned_release_is_accepted(self):
        client=GitHubClient()
        asset={'name':'OKDEV_Update_1.2.0.zip','browser_download_url':'https://github.com/okdev01/OKDEV/releases/download/v1.2.0/OKDEV_Update_1.2.0.zip'}
        release={'tag_name':'v1.2.0','assets':[asset]}
        self.assertEqual(client.get_zip_asset(release),asset)
        for url in ('http://github.com/okdev01/OKDEV/releases/download/x','https://github.com/Alban1911/Rose/releases/download/x','https://github.com.evil.test/okdev01/OKDEV/releases/download/x'):
            asset['browser_download_url']=url
            self.assertIsNone(client.get_zip_asset(release))

    def test_unsafe_archives_rejected_before_extraction(self):
        for name in ('../outside','C:/outside','dir\\..\\..\\outside','ltk_patcher_host.exe'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);archive=root/'update.zip'
                with zipfile.ZipFile(archive,'w') as z:z.writestr(name,'unsafe')
                self.assertIsNone(UpdateInstaller().extract_update(archive,root/'staging',lambda _:None,lambda _:None))
                self.assertEqual(list((root/'staging').iterdir()),[])

    def test_tampered_download_never_reaches_installer(self):
        with tempfile.TemporaryDirectory() as temp:
            sequence=UpdateSequence()
            asset={'name':'OKDEV_Update_9.0.0.zip','browser_download_url':'https://github.com/okdev01/OKDEV/releases/download/9.0.0/OKDEV_Update_9.0.0.zip','digest':'sha256:'+hashlib.sha256(b'good').hexdigest()}
            release={'tag_name':'9.0.0','assets':[asset]}
            def download(url,path,*args):path.write_bytes(b'tampered');return True
            with patch.object(sequence.github_client,'get_latest_release',return_value=release), patch('launcher.update.update_sequence.get_config_file_path',return_value=Path(temp)/'config.ini'), patch('psutil.process_iter',return_value=[]), patch.object(sequence.downloader,'download_update',side_effect=download), patch.object(sequence.installer,'extract_update') as extract:
                with self.assertRaises(ValueError): sequence._perform(lambda _:None,lambda _:None,None,lambda *args:True)
                extract.assert_not_called()


if __name__=='__main__':unittest.main()
