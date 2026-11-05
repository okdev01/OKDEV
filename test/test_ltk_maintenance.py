import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import requests
import okdev_ltk_update as update


class MaintenanceUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.tools=Path(self.temp.name)/'app/_internal/injection/tools';self.tools.mkdir(parents=True)
        for name in update.NAMES:(self.tools/name).write_bytes(b'keep')
        self.asset={'name':'official','digest':'sha256:'+'a'*64}
        self.mocks={}
        targets={
            'okdev_ltk_compat.resolve_verified':None,'okdev_ltk_compat.release_qualified':False,
            'okdev_ltk_delivery.select_cached':None,'okdev_ltk_delivery.sync_official':None,
            'okdev_ltk_update.require_idle':None,'okdev_ltk_update.read_game_build':101,
            'okdev_ltk_update.latest_asset':self.asset,
            'okdev_ltk_update.download_official':None,
            'okdev_ltk_update.check_ltk_patcher':SimpleNamespace(missing=[],eol=100,game_build=101,expired=True)}
        for target,value in targets.items():
            patched=patch(target,return_value=value)
            self.mocks[target]=patched.start();self.addCleanup(patched.stop)
        patched=patch.object(update,'extract_pair',side_effect=update.MissingArchivePair('separate delivery'))
        patched.start();self.addCleanup(patched.stop)

    def test_separate_dll_failure_is_backed_off_without_replacing_pair(self):
        for _ in range(2):
            with self.assertRaises(update.PatcherUnavailable):update.ensure_patcher(self.tools,Path('game'))
        self.assertEqual(self.mocks['okdev_ltk_update.download_official'].call_count,1)
        for name in update.NAMES:self.assertEqual((self.tools/name).read_bytes(),b'keep')

    def test_explicit_repair_bypasses_transient_backoff(self):
        for force in (False,True):
            with self.assertRaises(update.PatcherUnavailable):update.ensure_patcher(self.tools,Path('game'),force=force)
        self.assertEqual(self.mocks['okdev_ltk_update.download_official'].call_count,2)

    def test_new_release_ignores_old_transient_backoff(self):
        with self.assertRaises(update.PatcherUnavailable):update.ensure_patcher(self.tools,Path('game'))
        self.asset['digest']='sha256:'+'b'*64
        with self.assertRaises(update.PatcherUnavailable):update.ensure_patcher(self.tools,Path('game'))
        self.assertEqual(self.mocks['okdev_ltk_update.download_official'].call_count,2)

    def test_network_failure_is_library_safe(self):
        self.mocks['okdev_ltk_update.latest_asset'].side_effect=requests.ConnectionError('offline')
        with self.assertRaises(update.PatcherUnavailable):update.ensure_patcher(self.tools,Path('game'))
        self.mocks['okdev_ltk_update.download_official'].assert_not_called()

    def test_backoff_expiry_and_damaged_records_do_not_lock_out_updates(self):
        record=self.tools/'.ltk-delivery-retry.json'
        for content in ('[]','null','broken',json.dumps({'digest':self.asset['digest'],'game_build':101,'at':0})):
            record.write_text(content)
            self.assertFalse(update._delivery_backoff(self.tools,self.asset,101))


if __name__=='__main__':unittest.main()
