from pathlib import Path
import tempfile
from unittest.mock import Mock, patch
import unittest

import okdev_update_helper as helper


class HelperClientTests(unittest.TestCase):
    def run_helper(self, fail=False):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);install=root/'install';install.mkdir()
            (install/'OKDEV.exe').write_bytes(b'fixture')
            updates=root/'updates/9.0.0';updates.mkdir(parents=True)
            events=[]
            guard=Mock(resume_needed=True)
            guard.pause.side_effect=lambda:events.append('pause')
            guard.require_safe.side_effect=lambda:events.append('recheck')
            guard.resume.side_effect=lambda:events.append('resume')
            def apply(*args):
                events.append('apply')
                if fail:raise OSError('locked payload')
                return root/'backup'
            argv=['updater','--pid','123','--install-dir',str(install),'--staging-dir',str(root/'staging'),
                  '--log-file',str(updates/'updater.log'),'--restart-client-ux']
            with patch('sys.argv',argv),patch('psutil.Process'),patch('os.chdir'),patch.object(helper,'wait_for_install_exit'),patch.object(helper,'apply_update',side_effect=apply),patch('okdev_client_update.ClientPause',return_value=guard),patch('okdev_client_update.sync_runtime',side_effect=lambda _:events.append('runtime')),patch('okdev_branding.refresh_shortcut'),patch('subprocess.Popen',side_effect=lambda *a,**k:events.append('app')),patch('ctypes.windll.user32.MessageBoxW'):
                helper.main()
            text=(updates/'updater.log').read_text(encoding='utf-8')
            return events,text

    def test_runtime_is_synced_before_ux_and_app_resume(self):
        events,text=self.run_helper()
        self.assertEqual(events,['pause','recheck','apply','runtime','resume','app'])
        self.assertIn('Update installed.',text)

    def test_failed_update_restores_ux_and_reopens_original_app(self):
        events,text=self.run_helper(fail=True)
        self.assertEqual(events,['pause','recheck','apply','resume','app'])
        self.assertIn('previous installation retained',text)


if __name__=='__main__':unittest.main()
