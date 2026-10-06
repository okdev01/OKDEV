"""User preferences must survive concurrent desktop and launcher writers."""
import configparser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import config


class ConfigConcurrencyTests(unittest.TestCase):
    def test_threads_preserve_independent_changes_and_failed_edit(self):
        with tempfile.TemporaryDirectory(prefix='okdev-settings-') as temporary:
            target = Path(temporary) / 'config.ini'
            def update(index):
                with config.edit_config_file(target) as parser:
                    if not parser.has_section('General'):
                        parser.add_section('General')
                    time.sleep(0.002)
                    parser.set('General', 'key' + str(index), 'value%测试' + str(index))
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(update, range(24)))
            original = target.read_bytes()
            with self.assertRaises(RuntimeError):
                with config.edit_config_file(target) as parser:
                    parser.clear()
                    raise RuntimeError('cancel this edit')
            self.assertEqual(target.read_bytes(), original)
            parser = configparser.ConfigParser(interpolation=None)
            config.read_config_file(parser, target)
            self.assertEqual(dict(parser['General']), {'key' + str(i): 'value%测试' + str(i) for i in range(24)})

    def test_independent_processes_preserve_each_others_settings(self):
        code = '''
import sys, time
from pathlib import Path
from utils.core import paths
paths._cached_user_data_dir = Path(sys.argv[1])
paths._migration_checked = True
import config
target = Path(sys.argv[1]) / 'config.ini'
for i in range(12):
    with config.edit_config_file(target) as parser:
        if not parser.has_section('General'):
            parser.add_section('General')
        time.sleep(.003)
        parser.set('General', sys.argv[2] + str(i), 'kept')
'''
        with tempfile.TemporaryDirectory(prefix='okdev-settings-processes-') as temporary:
            children = [subprocess.Popen([sys.executable, '-c', code, temporary, name],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                for name in ('launcher', 'desktop', 'integration')]
            try:
                for child in children:
                    _, error = child.communicate(timeout=20)
                    self.assertEqual(child.returncode, 0, error.decode(errors='replace'))
            finally:
                for child in children:
                    if child.poll() is None:
                        child.kill()
                        child.communicate()
            parser = configparser.ConfigParser(interpolation=None)
            config.read_config_file(parser, Path(temporary) / 'config.ini')
            expected = {name + str(i): 'kept' for name in ('launcher', 'desktop', 'integration') for i in range(12)}
            self.assertEqual(dict(parser['General']), expected)

    def test_corrupt_file_is_not_replaced_with_one_setting(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'config.ini'
            original = b'not-an-ini-file'
            target.write_bytes(original)
            with patch.object(config, 'get_config_file_path', return_value=target):
                config.set_config_option('General', 'language', 'tr')
            self.assertEqual(target.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
