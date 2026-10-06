"""Real independent processes mutate one library; no lost index/profile writes."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class LibraryConcurrencyTests(unittest.TestCase):
    def test_parallel_import_enable_remove_restore_and_profile_writers(self):
        code = '''
import sys, zipfile
from pathlib import Path
from utils.core import paths
paths._cached_user_data_dir = Path(sys.argv[1])
paths._migration_checked = True
from hub import library, profiles
name = sys.argv[2]
archive = Path(sys.argv[1]) / (name + '.fantome')
with zipfile.ZipFile(archive, 'w') as bundle:
    bundle.writestr('WAD/Ahri.wad.client', name.encode())
for i in range(8):
    mod_id = name + '-' + str(i)
    library.import_archive(archive, dict(id=mod_id, name=mod_id, champion='Ahri', champion_id=103, version='1.0.0', description='Isolated concurrency fixture'))
    library.enable(mod_id, True)
    profiles.save(mod_id)
    library.remove(mod_id)
    backup = next(item for item in library.removed() if item['name'] == mod_id)
    library.restore(backup['backup_id'])
'''
        with tempfile.TemporaryDirectory(prefix='okdev-library-concurrency-') as tmp:
            children = [subprocess.Popen([sys.executable, '-c', code, tmp, name],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                        for name in ('left', 'right', 'third')]
            try:
                for child in children:
                    _, error = child.communicate(timeout=45)
                    self.assertEqual(child.returncode, 0, error.decode(errors='replace'))
            finally:
                for child in children:
                    if child.poll() is None:
                        child.kill()
                        child.communicate()
            data = Path(tmp)
            installed = json.loads((data / 'hub/installed.json').read_text(encoding='utf-8'))
            profiles = json.loads((data / 'hub/profiles.json').read_text(encoding='utf-8'))
            expected = {name + '-' + str(i) for name in ('left', 'right', 'third') for i in range(8)}
            self.assertEqual(set(installed), expected)
            self.assertEqual({profile['name'] for profile in profiles.values()}, expected)
            self.assertLessEqual(sum(item['enabled'] for item in installed.values()), 1)
            for mod_id, item in installed.items():
                payload = data / 'mods' / item['relative_path'] / 'WAD/Ahri.wad.client'
                self.assertEqual(payload.read_bytes(), mod_id.split('-')[0].encode())
            self.assertEqual(list((data / 'hub/pending').glob('*.json')), [])
