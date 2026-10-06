import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile
import okdev_repair as repair


class RepairTests(unittest.TestCase):
    def fixture(self, root):
        install = root/'install'; install.mkdir()
        (install/'OKDEV.exe').write_bytes(b'old')
        (install/'okdev-install.json').write_text(json.dumps({'install_id':'friend-install','version':'1.1.2'}))
        (install/'config.ini').write_text('keep-settings')
        archive = root/'OKDEV_Update_1.2.1.zip'
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('OKDEV.exe',b'new')
            z.writestr('okdev-update.json',json.dumps({'app':'OKDEV','version':'1.2.1'}))
        return install, hashlib.sha256(archive.read_bytes()).hexdigest()

    def test_independent_install_id_and_settings_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); install,digest=self.fixture(root)
            with patch.object(repair,'RESOURCES',root), patch.object(repair,'DIGEST',digest), patch('psutil.process_iter',return_value=[]), patch('okdev_branding.refresh_shortcut'):
                backup=repair.repair(install)
            self.assertEqual((backup/'OKDEV.exe').read_bytes(),b'old')
            self.assertEqual((install/'OKDEV.exe').read_bytes(),b'new')
            self.assertEqual((install/'config.ini').read_text(),'keep-settings')
            self.assertEqual(json.loads((install/'okdev-install.json').read_text())['install_id'],'friend-install')

    def test_game_open_stops_before_any_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); install,digest=self.fixture(root)
            game=SimpleNamespace(info={'name':'League of Legends.exe'})
            with patch.object(repair,'RESOURCES',root), patch.object(repair,'DIGEST',digest), patch('psutil.process_iter',return_value=[game]):
                with self.assertRaisesRegex(ValueError,'League'): repair.repair(install)
            self.assertEqual((install/'OKDEV.exe').read_bytes(),b'old')

    def test_refuses_downgrade(self):
        with tempfile.TemporaryDirectory() as temp:
            install,_=self.fixture(Path(temp))
            (install/'okdev-install.json').write_text(json.dumps({'install_id':'x','version':'1.3.0'}))
            with self.assertRaisesRegex(ValueError,'daha yeni'): repair.validate_install(install)
