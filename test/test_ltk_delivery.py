import base64
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nacl.signing import SigningKey
from nacl.exceptions import BadSignatureError
import okdev_ltk_delivery as delivery


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.envelope = json.loads((Path(__file__).parent / 'fixtures/ltk-delivery-envelope.json').read_text())

    def test_actual_upstream_manifest_verifies_without_credentials(self):
        result = delivery.verify_manifest(self.envelope)
        self.assertEqual(result['release']['digest'], 'dd68fa8e3f9ad9efa47ddb54222b544fc02be2b29b902234aaca47b19f1097a6')
        self.assertEqual(result['release']['protocol'], 3)
        self.assertNotIn('token', self.envelope)

    def test_forged_body_or_trusted_comment_is_rejected(self):
        forged = copy.deepcopy(self.envelope)
        raw = bytearray(base64.b64decode(forged['manifest']))
        raw[10] ^= 1
        forged['manifest'] = base64.b64encode(raw).decode()
        with self.assertRaises((BadSignatureError, ValueError)):
            delivery.verify_manifest(forged)
        forged = copy.deepcopy(self.envelope)
        forged['signature'] = forged['signature'].replace('stable 1 ', 'stable 2 ')
        with self.assertRaises((BadSignatureError, ValueError)):
            delivery.verify_manifest(forged)

    def fixture(self, root, key, *, revoked=False, protocol=3):
        dll, host = b'test dll', b'test host'
        digest = hashlib.sha256(dll).hexdigest()
        manifest = {'schema': 1, 'channel': 'stable', 'sequence': 1,
                    'release': {'version': 'ltk_patcher-25', 'digest': digest, 'size': len(dll),
                                'eol': 102, 'protocol': protocol, 'managers': '>=1.30.0'},
                    'revoked': [digest] if revoked else []}
        raw = json.dumps(manifest).encode()
        sig = key.sign(hashlib.blake2b(raw).digest()).signature
        comment = 'stable 1 ltk_patcher-25'
        encoded = base64.b64encode(b'ED' + b'12345678' + sig).decode()
        envelope = {'manifest': base64.b64encode(raw).decode(), 'signature':
                    'untrusted comment: fixture\n' + encoded + '\ntrusted comment: ' + comment + '\n' +
                    base64.b64encode(key.sign(sig + comment.encode()).signature).decode() + '\n'}
        cache = root / 'cache'
        directory = cache / digest
        directory.mkdir(parents=True, exist_ok=True)
        (directory / delivery.DLL).write_bytes(dll)
        (cache / 'delivery.json').write_text(json.dumps({'channels': {'stable': {'envelope': envelope}}}))
        manager = root / 'manager'; manager.mkdir(exist_ok=True)
        (manager / delivery.HOST).write_bytes(host)
        return cache, manager, digest, hashlib.sha256(host).hexdigest()

    def test_signed_selection_rechecks_dll_host_game_and_revocations(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            key = SigningKey.generate()
            cache, manager, digest, host_hash = self.fixture(root, key)
            public = base64.b64encode(b'Ed' + b'12345678' + key.verify_key.encode()).decode()
            with patch.object(delivery, 'PUBLIC_KEY', public), patch.object(delivery, 'HOST_SHA256', host_hash), \
                 patch.object(delivery, 'delivery_root', return_value=cache), \
                 patch.object(delivery, 'manager_dir', return_value=manager), \
                 patch.object(delivery, 'runtime_root', return_value=root / 'runtime'), \
                 patch.object(delivery, 'read_dll_eol', return_value=102), \
                 patch.object(delivery, 'read_game_build', return_value=101) as build:
                selected = delivery.select_cached(Path('game'), stage=True)
                self.assertEqual(selected, root/'runtime'/digest)
                self.assertEqual(delivery.select_cached(Path('game')), selected)
                (selected / delivery.DLL).write_bytes(b'tampered')
                self.assertIsNone(delivery.select_cached(Path('game')))
                self.assertEqual(delivery.select_cached(Path('game'), stage=True), selected)
                build.return_value = 103
                self.assertIsNone(delivery.select_cached(Path('game')))
                build.return_value = 101
                self.fixture(root, key, revoked=True)
                self.assertIsNone(delivery.select_cached(Path('game')))
                self.fixture(root, key, protocol=4)
                self.assertIsNone(delivery.select_cached(Path('game')))
                self.fixture(root, key)
                (manager / delivery.HOST).write_bytes(b'unknown host')
                self.assertIsNone(delivery.select_cached(Path('game')))

    def test_cached_healthy_delivery_never_installs_or_starts_manager(self):
        with patch.object(delivery, 'select_cached', return_value=Path('cached')), \
             patch.object(delivery.subprocess, 'run') as install:
            self.assertEqual(delivery.sync_official(Path('game'), installer=Path('setup')), Path('cached'))
            install.assert_not_called()

    def test_healthy_delivery_bypasses_legacy_download(self):
        import okdev_ltk_update as update
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temp:
            tools = Path(temp) / 'app/_internal/injection/tools';tools.mkdir(parents=True)
            with patch.object(delivery, 'select_cached', return_value=Path('cached')), \
                 patch.object(update, 'check_ltk_patcher', return_value=SimpleNamespace(missing=['dll'],eol=None)), \
                 patch.object(update, 'latest_asset') as api:
                self.assertFalse(update.ensure_patcher(tools, Path('game')))
                api.assert_not_called()

    def test_signed_eol_survives_compiler_changes_and_never_downgrades_on_tampering(self):
        from injection.tools.patcher import check_ltk_patcher
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);key=SigningKey.generate()
            cache,manager,digest,host_hash=self.fixture(root,key)
            public=base64.b64encode(b'Ed'+b'12345678'+key.verify_key.encode()).decode()
            with patch.object(delivery,'PUBLIC_KEY',public), patch.object(delivery,'HOST_SHA256',host_hash), \
                 patch.object(delivery,'delivery_root',return_value=cache), \
                 patch.object(delivery,'manager_dir',return_value=manager), \
                 patch.object(delivery,'runtime_root',return_value=root/'runtime'), \
                 patch.object(delivery,'read_game_build',return_value=101), \
                 patch('injection.tools.patcher.read_game_build',return_value=101), \
                 patch('injection.tools.patcher.read_dll_eol',return_value=None) as legacy:
                selected=delivery.select_cached(Path('game'),stage=True)
                self.assertIsNotNone(selected)
                self.assertEqual(check_ltk_patcher(selected,Path('game')).eol,102)
                legacy.assert_not_called()
                (selected/delivery.DLL).write_bytes(b'tampered')
                legacy.return_value=99999999
                self.assertIsNone(check_ltk_patcher(selected,Path('game')).eol)
                legacy.assert_not_called()


if __name__ == '__main__':
    unittest.main()
