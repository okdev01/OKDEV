import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from nacl.exceptions import BadSignatureError
import okdev_ltk_compat as compat


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.game=self.root/'game.exe';self.game.write_bytes(b'game')
        self.target=self.root/'runtime/compat-candidate-1.29.1';self.target.mkdir(parents=True)
        pins={}
        for name in compat.FILES:
            data=name.encode();(self.target/name).write_bytes(data);pins[name]=hashlib.sha256(data).hexdigest()
        patches=[patch.object(compat,'_root',return_value=self.root/'runtime'),
                 patch.object(compat,'FILES',pins),patch.object(compat,'GAME_SHA256',hashlib.sha256(b'game').hexdigest()),
                 patch.object(compat,'read_game_build',return_value=100),patch.object(compat,'read_dll_eol',return_value=101),
                 patch('okdev_ltk_delivery.delivery_root',return_value=self.root/'delivery')]
        for item in patches:item.start();self.addCleanup(item.stop)

    def test_valid_candidate_is_not_automatically_enabled_before_visual_test(self):
        self.assertEqual(compat.candidate(self.game),self.target)
        self.assertIsNone(compat.resolve_verified(self.game))

    def test_release_tested_build_needs_no_machine_local_visual_marker(self):
        with patch.object(compat,'RELEASE_TESTED_GAME_SHA256',compat.GAME_SHA256):
            self.assertTrue(compat.release_qualified(self.game))
            self.assertEqual(compat.resolve_verified(self.game),self.target)
            self.assertFalse((self.root/'runtime/compat-visual-qa.json').exists())
            (self.target/'ltk_patcher_dll.dll').write_bytes(b'corrupt')
            self.assertIsNone(compat.resolve_verified(self.game))

    def test_release_qa_cannot_transfer_to_new_game(self):
        with patch.object(compat,'RELEASE_TESTED_GAME_SHA256',compat.GAME_SHA256):
            self.game.write_bytes(b'new patch')
            self.assertFalse(compat.release_qualified(self.game))
            self.assertIsNone(compat.resolve_verified(self.game))

    def test_fresh_install_prepares_tested_pair_before_latest_runtime(self):
        import okdev_ltk_update as update
        from types import SimpleNamespace
        tools=self.root/'app/_internal/injection/tools';tools.mkdir(parents=True)
        missing=SimpleNamespace(missing=['dll'],eol=None,expired=False)
        with patch.object(compat,'RELEASE_TESTED_GAME_SHA256',compat.GAME_SHA256), \
             patch.object(update,'check_ltk_patcher',return_value=missing), \
             patch.object(compat,'resolve_verified',side_effect=[None,self.target]), \
             patch.object(compat,'prepare_candidate',return_value=self.target) as prepare, \
             patch('okdev_ltk_delivery.select_cached') as latest:
            self.assertTrue(update.ensure_patcher(tools,self.game))
            prepare.assert_called_once()
            latest.assert_not_called()

    def test_preparation_failure_never_falls_back_to_incompatible_latest(self):
        import okdev_ltk_update as update
        from types import SimpleNamespace
        tools=self.root/'app/_internal/injection/tools';tools.mkdir(parents=True)
        missing=SimpleNamespace(missing=['dll'],eol=None,expired=False)
        with patch.object(compat,'RELEASE_TESTED_GAME_SHA256',compat.GAME_SHA256), \
             patch.object(update,'check_ltk_patcher',return_value=missing), \
             patch.object(compat,'resolve_verified',return_value=None), \
             patch.object(compat,'prepare_candidate',side_effect=ValueError('download failed')), \
             patch('okdev_ltk_delivery.select_cached') as latest:
            with self.assertRaisesRegex(ValueError,'download failed'):
                update.ensure_patcher(tools,self.game)
            latest.assert_not_called()

    def test_verified_pair_takes_priority_over_incompatible_latest_cache(self):
        from okdev_ltk_delivery import resolve_patcher_dir
        compat.record_visual_qa(self.game)
        with patch('okdev_ltk_delivery.select_cached') as latest:
            self.assertEqual(resolve_patcher_dir(self.root/'fallback',self.game),self.target)
            latest.assert_not_called()

    def test_injection_detector_passes_actual_game_to_compatibility_selection(self):
        from injection.tools.tools_manager import ToolsManager
        with patch('okdev_ltk_delivery.resolve_patcher_dir',return_value=self.target) as resolve:
            fallback=self.root/'fallback'
            self.assertEqual(ToolsManager(fallback,self.game).detect_ltk_patcher(),self.target/'ltk_patcher_host.exe')
            resolve.assert_called_once_with(fallback,self.game)

    def test_explicit_visual_record_selects_only_exact_game_and_pair(self):
        compat.record_visual_qa(self.game)
        self.assertEqual(compat.resolve_verified(self.game),self.target)
        self.game.write_bytes(b'updated game')
        self.assertIsNone(compat.resolve_verified(self.game))

    def test_tampered_pair_cannot_be_selected(self):
        compat.record_visual_qa(self.game)
        (self.target/'ltk_patcher_dll.dll').write_bytes(b'tampered')
        self.assertIsNone(compat.resolve_verified(self.game))

    def test_game_build_cutoff_remains_enforced(self):
        with patch.object(compat,'read_game_build',return_value=102):
            self.assertIsNone(compat.candidate(self.game))
            with self.assertRaises(ValueError):compat.record_visual_qa(self.game)

    def test_revocation_and_bad_manifest_fail_closed(self):
        delivery=self.root/'delivery';delivery.mkdir()
        (delivery/'delivery.json').write_text(json.dumps({'channels':{'stable':{'envelope':{}}}}))
        with patch('okdev_ltk_delivery.verify_manifest',return_value={'revoked':[compat.FILES['ltk_patcher_dll.dll']]}):
            self.assertIsNone(compat.candidate(self.game))
        with patch('okdev_ltk_delivery.verify_manifest',side_effect=BadSignatureError('bad signature')):
            self.assertIsNone(compat.candidate(self.game))


if __name__=='__main__':unittest.main()
