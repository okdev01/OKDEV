import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from utils.download.bundled_skins import install_bundled_skins


class BundledSkinsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / 'bundle'
        self.target = self.root / 'data'
        self.bundle.mkdir()
        self.relative = '141/141032/141034/141034.fantome'
        source = self.bundle / self.relative
        source.parent.mkdir(parents=True)
        source.write_bytes(b'verified fixture')
        self.manifest = {'packages': [{'path': self.relative, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}],
                         'names': {'en': {'141034': 'Rose Quartz'}}}
        self.mapping = self.target / 'resources/en/skin_ids.json'
        self.mapping.parent.mkdir(parents=True)
        self.mapping.write_text('{"141000":"Kayn"}')
        self.save()

    def save(self):
        (self.bundle / 'manifest.json').write_text(json.dumps(self.manifest))

    def test_missing_package_and_name_installed_idempotently(self):
        self.assertEqual(install_bundled_skins(self.bundle, self.target), 1)
        self.assertEqual(install_bundled_skins(self.bundle, self.target), 0)
        self.assertEqual(json.loads(self.mapping.read_text()), {'141000': 'Kayn', '141034': 'Rose Quartz'})

    def test_upstream_package_and_translation_win(self):
        dest = self.target / 'skins' / self.relative
        dest.parent.mkdir(parents=True)
        dest.write_bytes(b'new upstream package')
        self.mapping.write_text('{"141034":"upstream name"}')
        self.assertEqual(install_bundled_skins(self.bundle, self.target), 0)
        self.assertEqual(dest.read_bytes(), b'new upstream package')
        self.assertEqual(json.loads(self.mapping.read_text())['141034'], 'upstream name')

    def test_corrupt_bundle_does_not_change_user_files(self):
        (self.bundle / self.relative).write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            install_bundled_skins(self.bundle, self.target)
        self.assertFalse((self.target / 'skins').exists())
        self.assertEqual(json.loads(self.mapping.read_text()), {'141000': 'Kayn'})

    def test_traversal_is_rejected(self):
        self.manifest['packages'][0]['path'] = '../escape.fantome'
        self.save()
        with self.assertRaises(ValueError):
            install_bundled_skins(self.bundle, self.target)
        self.assertFalse((self.target / 'skins').exists())


if __name__ == '__main__':
    unittest.main()
