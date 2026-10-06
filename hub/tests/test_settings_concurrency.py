"""Exercise separate writers sharing the same actual settings file."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class SettingsConcurrencyTests(unittest.TestCase):
    def test_favorites_and_preferences_survive_concurrent_processes(self):
        from hub import library
        code = '''
import sys, time
from pathlib import Path
from utils.core import paths
paths._cached_user_data_dir = Path(sys.argv[1])
paths._migration_checked = True
from hub import library, preferences
name = sys.argv[2]
for i in range(20):
    library.set_favorite(name + str(i), True)
    preferences.update({'theme': 'light' if i % 2 else 'dark'})
    time.sleep(.002)
'''
        with tempfile.TemporaryDirectory() as tmp:
            children = [subprocess.Popen([sys.executable, '-c', code, tmp, name],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)) for name in ('left', 'right', 'third')]
            for child in children:
                _, err = child.communicate(timeout=30)
                self.assertEqual(child.returncode, 0, err.decode(errors='replace'))
            files = list(Path(tmp).rglob('settings.json'))
            self.assertEqual(len(files), 1)
            data = library.read_json(files[0], {})
            self.assertEqual(set(data['favorites']), {name + str(i) for name in ('left','right','third') for i in range(20)})
            self.assertEqual(data['theme'], 'light')
