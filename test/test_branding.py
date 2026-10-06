import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from okdev_branding import retire_legacy_plugins, refresh_shortcut


class BrandingTests(unittest.TestCase):
    def test_replaced_plugins_are_archived_and_custom_plugins_remain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('ROSE-UI', 'OKDEV-UI', 'ROSE-CustomUserPlugin', 'OtherPlugin'):
                folder = root / 'plugins' / name
                folder.mkdir(parents=True)
                (folder / 'index.js').write_text(name)
            self.assertEqual(retire_legacy_plugins(root), ['ROSE-UI'])
            self.assertTrue((root / 'plugins/ROSE-CustomUserPlugin/index.js').exists())
            self.assertTrue((root / 'plugins/OtherPlugin/index.js').exists())
            saved = list((root / 'legacy-plugin-backups').rglob('index.js'))
            self.assertEqual(saved[0].read_text(), 'ROSE-UI')
            self.assertEqual(retire_legacy_plugins(root), [])

    def test_shortcut_uses_content_specific_icon_path(self):
        with tempfile.TemporaryDirectory() as tmp, patch('okdev_branding.subprocess.run') as run:
            root = Path(tmp)
            (root / 'icon.ico').write_bytes(b'first-icon')
            refresh_shortcut(root)
            first = Path(run.call_args.kwargs['env']['OKDEV_SETUP_ICON'])
            self.assertEqual(first.read_bytes(), b'first-icon')
            (root / 'icon.ico').write_bytes(b'new-icon')
            refresh_shortcut(root)
            second = Path(run.call_args.kwargs['env']['OKDEV_SETUP_ICON'])
            self.assertNotEqual(first, second)
            self.assertEqual(second.read_bytes(), b'new-icon')
