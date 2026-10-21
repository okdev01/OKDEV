import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from launcher.update.update_sequence import UpdateSequence
from launcher.update import pending


class PendingUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.install=self.root/'install';self.install.mkdir()
        (self.install/'okdev-install.json').write_text('{"install_id":"fixture"}')
        source=self.root/'source.zip'
        with zipfile.ZipFile(source,'w') as z:
            z.writestr('OKDEV.exe',b'fixture')
            z.writestr('OKDEV-Updater.exe',b'helper')
            z.writestr('okdev-update.json',json.dumps({'app':'OKDEV','version':'9.0.0'}))
        self.contents=source.read_bytes();self.digest=hashlib.sha256(self.contents).hexdigest()
        self.sequence=UpdateSequence()
        self.sequence.github_client=Mock()
        asset={'name':'OKDEV_Update_9.0.0.zip','size':len(self.contents),'digest':'sha256:'+self.digest,'browser_download_url':'https://github.com/okdev01/OKDEV/releases/download/v9.0.0/OKDEV_Update_9.0.0.zip'}
        self.sequence.github_client.get_latest_release.return_value={'tag_name':'v9.0.0'}
        self.sequence.github_client.get_release_version.return_value='9.0.0'
        self.sequence.github_client.get_zip_asset.return_value=asset
        def download(url,path,*args):path.write_bytes(self.contents);return True
        self.sequence.downloader.download_update=Mock(side_effect=download)
        for target,value in [('launcher.update.update_sequence.get_config_file_path',self.root/'config.ini'),('launcher.update.pending.get_config_file_path',self.root/'config.ini')]:
            patcher=patch(target,return_value=value);patcher.start();self.addCleanup(patcher.stop)
        executable=patch('sys.executable',str(self.install/'OKDEV.exe'));executable.start();self.addCleanup(executable.stop)

    def stage_busy(self):
        confirm=Mock(return_value=True)
        with patch('okdev_client_update.safe_to_update',return_value=False),patch('launcher.update.update_installer.UpdateInstaller.launch_updater') as launch:
            self.assertFalse(self.sequence._perform(lambda _:None,lambda _:None,None,confirm))
            launch.assert_not_called()
        self.assertTrue(pending.location().exists())
        return confirm

    def test_downloads_during_busy_phase_then_launches_when_safe(self):
        self.stage_busy()
        with patch('okdev_client_update.safe_to_update',return_value=True),patch('launcher.update.update_installer.UpdateInstaller.launch_updater',return_value=True) as launch:
            self.assertTrue(pending.launch_pending())
            self.assertTrue(launch.call_args.args[0]['restart_client'])

    def test_reuses_approved_download_without_second_prompt(self):
        self.stage_busy()
        confirm=Mock(return_value=False)
        with patch('okdev_client_update.safe_to_update',return_value=False):
            self.assertFalse(self.sequence._perform(lambda _:None,lambda _:None,None,confirm))
        confirm.assert_not_called()
        self.sequence.downloader.download_update.assert_called_once()

    def test_tampered_pending_archive_cannot_launch(self):
        self.stage_busy()
        (pending.location().parent/'9.0.0/OKDEV_Update_9.0.0.zip').write_bytes(b'tampered')
        with patch('okdev_client_update.safe_to_update',return_value=True),patch('launcher.update.update_installer.UpdateInstaller.launch_updater') as launch:
            with self.assertRaises(ValueError):pending.launch_pending()
            launch.assert_not_called()

    def test_queue_starting_during_extraction_defers_launch(self):
        self.stage_busy()
        with patch('okdev_client_update.safe_to_update',side_effect=[True,False]),patch('launcher.update.update_installer.UpdateInstaller.launch_updater') as launch:
            self.assertFalse(pending.launch_pending())
            launch.assert_not_called()

    def test_wrong_installation_does_not_receive_pending_update(self):
        self.stage_busy()
        with patch('sys.executable',str(self.root/'other/OKDEV.exe')),patch('launcher.update.update_installer.UpdateInstaller.launch_updater') as launch:
            self.assertFalse(pending.launch_pending())
            launch.assert_not_called()


if __name__=='__main__':unittest.main()
