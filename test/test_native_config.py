"""Exercise the actual C# INI adapter without activation or a running game."""
import configparser
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import config


@unittest.skipUnless(os.name == 'nt', 'Windows native loader configuration')
class NativeConfigTests(unittest.TestCase):
    def test_compiled_loader_adapter_preserves_unicode_and_other_settings(self):
        compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        if not compiler.is_file():
            self.skipTest('.NET Framework compiler unavailable')
        with tempfile.TemporaryDirectory(prefix='okdev-native-ini-') as temporary:
            root = Path(temporary)
            loader = root / '测试-Игрок-Çağrı-%100'
            loader.mkdir()
            executable = loader / 'ConfigAdapter.exe'
            harness = root / 'Harness.cs'
            harness.write_text(
                'class Harness { static void Main(string[] args) { '
                'PenguLoader.Main.OKDEVConfig.SetLoaderState(args[0] == "active"); } }',
                encoding='utf-8')
            adapter = Path(__file__).resolve().parents[1] / 'vendor/PenguLoader-1.1.6/loader/Main/OKDEVConfig.cs'
            result = subprocess.run([str(compiler), '/nologo', '/target:exe',
                '/out:' + str(executable), str(adapter), str(harness)],
                capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(result.returncode, 0, result.stdout.decode(errors='replace'))
            target = root / 'user-data/config.ini'
            environment = dict(os.environ, OKDEV_CONFIG_PATH=str(target))
            def invoke(state):
                subprocess.run([str(executable), state], env=environment, check=True,
                    capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
                parser = configparser.ConfigParser(interpolation=None)
                config.read_config_file(parser, target)
                return parser
            first = invoke('active')
            self.assertTrue(target.read_bytes().startswith(b'\xff\xfe'))
            self.assertEqual(first['General']['loaderpath'], str(loader))
            self.assertEqual(first['General']['disabled'], '0')
            first['General']['clientpath'] = 'D:\\游戏\\100%\\League'
            config.write_config_file(first, target)
            second = invoke('inactive')
            self.assertEqual(second['General']['loaderpath'], '')
            self.assertEqual(second['General']['disabled'], '1')
            self.assertEqual(second['General']['clientpath'], first['General']['clientpath'])
            third = invoke('active')
            self.assertEqual(third['General']['loaderpath'], str(loader))
            self.assertEqual(third['General']['clientpath'], first['General']['clientpath'])


if __name__ == '__main__':
    unittest.main()
