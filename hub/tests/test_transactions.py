import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from hub import library, transactions
from hub.desktop import Api
from hub.tests.test_library import LibraryFixture


class PowerLoss(BaseException):
    """Skip normal exception rollback, like a terminated process."""


class TransactionRecoveryTests(LibraryFixture):
    def crash_process(self, operation, after_commit=False):
        code = '''
import os, sys
from pathlib import Path
from utils.core import paths
paths._cached_user_data_dir = Path(sys.argv[1])
paths._migration_checked = True
from hub import library
original = library.write_json
def crash(path, value):
    if path.name == 'installed.json':
        if sys.argv[3] == 'after':
            original(path, value)
        os._exit(73)
    return original(path, value)
library.write_json = crash
if sys.argv[2] == 'update':
    library.import_archive(Path(sys.argv[1]) / 'next.zip', dict(id='sample',name='Next',champion='Ahri',champion_id=103,version='2.0.0',description='fixture'))
elif sys.argv[2] == 'remove':
    library.remove('sample')
elif sys.argv[2] == 'restore':
    library.restore(library.removed()[0]['backup_id'])
'''
        result = subprocess.run([sys.executable, '-c', code, str(self.root), operation, 'after' if after_commit else 'before'],
            cwd=Path(__file__).resolve().parents[2], capture_output=True, timeout=10,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual(result.returncode, 73, result.stderr.decode(errors='replace'))

    def interrupt_index(self):
        original = library.write_json
        def interrupted(path, value):
            if path.name == 'installed.json':
                raise PowerLoss()
            return original(path, value)
        return patch('hub.library.write_json', side_effect=interrupted)

    def recover(self):
        snapshot = Api().snapshot()
        self.assertEqual(snapshot['warning'], '')
        self.assertEqual(transactions.status()['pending'], 0)
        return snapshot

    def test_interrupted_first_import_is_retained_as_a_recoverable_backup(self):
        with self.interrupt_index(), self.assertRaises(PowerLoss):
            library.import_archive(self.archive(), self.item())
        self.assertEqual(transactions.status()['pending'], 1)
        self.recover()
        self.assertEqual(library.installed(), {})
        backups = library.removed()
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0]['reason'], 'interrupted')
        restored = library.restore(backups[0]['backup_id'])
        self.assertEqual((library.mod_folder(restored) / 'WAD/Ahri.wad.client').read_bytes(), b'fixture-wad-data')

    def test_interrupted_update_restores_old_selection_and_retains_new_payload(self):
        old = library.import_archive(self.archive(), self.item())
        library.enable('sample', True)
        new = self.archive('next.fantome', {'WAD/Ahri.wad.client': b'new payload'})
        with self.interrupt_index(), self.assertRaises(PowerLoss):
            library.import_archive(new, dict(self.item(), version='2.0.0'))
        self.assertFalse(library.mod_folder(old).exists())
        self.recover()
        current = library.installed()['sample']
        self.assertEqual(current['version'], '1.0.0')
        self.assertTrue(current['enabled'])
        self.assertEqual((library.mod_folder(current) / 'WAD/Ahri.wad.client').read_bytes(), b'fixture-wad-data')
        self.assertEqual([(b['version'], b['reason']) for b in library.removed()], [('2.0.0', 'interrupted')])

    def test_interrupted_remove_restores_original_files(self):
        item = library.import_archive(self.archive(), self.item())
        with self.interrupt_index(), self.assertRaises(PowerLoss):
            library.remove('sample')
        self.assertFalse(library.mod_folder(item).exists())
        self.recover()
        self.assertTrue(library.mod_folder(item).is_dir())
        self.assertIn('sample', library.installed())
        self.assertEqual(library.removed(), [])

    def test_interrupted_restore_returns_payload_to_its_backup(self):
        library.import_archive(self.archive(), self.item())
        library.remove('sample')
        backup_id = library.removed()[0]['backup_id']
        with self.interrupt_index(), self.assertRaises(PowerLoss):
            library.restore(backup_id)
        self.assertEqual(library.removed(), [])
        self.recover()
        self.assertEqual(library.installed(), {})
        self.assertEqual(library.removed()[0]['backup_id'], backup_id)

    def test_interruption_after_commit_keeps_new_version(self):
        library.import_archive(self.archive(), self.item())
        with patch('hub.transactions.finish', side_effect=PowerLoss), self.assertRaises(PowerLoss):
            library.import_archive(self.archive('next.zip'), dict(self.item(), version='2.0.0'))
        self.assertEqual(library.installed()['sample']['version'], '2.0.0')
        self.recover()
        self.assertEqual(library.installed()['sample']['version'], '2.0.0')
        self.assertEqual(library.removed()[0]['version'], '1.0.0')

    def test_interruption_after_remove_commit_keeps_recoverable_removal(self):
        library.import_archive(self.archive(), self.item())
        with patch('hub.transactions.finish', side_effect=PowerLoss), self.assertRaises(PowerLoss):
            library.remove('sample')
        self.recover()
        self.assertEqual(library.installed(), {})
        self.assertEqual(len(library.removed()), 1)

    def test_external_index_change_blocks_recovery_without_overwriting(self):
        library.import_archive(self.archive(), self.item())
        with self.interrupt_index(), self.assertRaises(PowerLoss):
            library.remove('sample')
        data = library.installed()
        data['sample']['name'] = 'Externally changed name'
        library.write_json(library.root() / 'installed.json', data)
        snapshot = Api().snapshot()
        self.assertIn('kurtarılamadı', snapshot['warning'])
        self.assertEqual(library.installed()['sample']['name'], 'Externally changed name')
        self.assertEqual(transactions.status()['pending'], 1)

    def test_invalid_journal_preserved_and_new_writes_blocked(self):
        path = library.root() / 'pending' / ('a' * 32 + '.json')
        path.parent.mkdir()
        path.write_text('{invalid', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'kurtarılamadı'):
            library.import_archive(self.archive(), self.item())
        self.assertEqual(path.read_text(), '{invalid')
        self.assertEqual(library.installed(), {})

    def test_recovery_is_idempotent(self):
        with self.interrupt_index(), self.assertRaises(PowerLoss):
            library.import_archive(self.archive(), self.item())
        self.recover()
        backups = library.removed()
        self.recover()
        self.assertEqual(backups, library.removed())

    def test_regular_write_failure_rolls_back_then_preserves_new_payload(self):
        library.import_archive(self.archive(), self.item())
        original = library.write_json
        def fail(path, value):
            if path.name == 'installed.json':
                raise OSError('disk full')
            return original(path, value)
        with patch('hub.library.write_json', side_effect=fail), self.assertRaises(OSError):
            library.import_archive(self.archive('next.zip'), dict(self.item(), version='2.0.0'))
        self.assertTrue(library.mod_folder(library.installed()['sample']).is_dir())
        self.recover()
        self.assertEqual(library.removed()[0]['version'], '2.0.0')

    def test_real_process_exit_before_update_commit_recovers_original_bytes(self):
        library.import_archive(self.archive(), self.item())
        self.archive('next.zip', {'WAD/Ahri.wad.client': b'new process payload'})
        self.crash_process('update')
        self.recover()
        item = library.installed()['sample']
        self.assertEqual(item['version'], '1.0.0')
        self.assertEqual((library.mod_folder(item) / 'WAD/Ahri.wad.client').read_bytes(), b'fixture-wad-data')
        self.assertEqual(library.removed()[0]['reason'], 'interrupted')

    def test_real_process_exit_after_update_commit_keeps_new_bytes(self):
        library.import_archive(self.archive(), self.item())
        self.archive('next.zip', {'WAD/Ahri.wad.client': b'new process payload'})
        self.crash_process('update', after_commit=True)
        self.recover()
        item = library.installed()['sample']
        self.assertEqual(item['version'], '2.0.0')
        self.assertEqual((library.mod_folder(item) / 'WAD/Ahri.wad.client').read_bytes(), b'new process payload')

    def test_real_process_exit_during_removal_recovers_mod(self):
        item = library.import_archive(self.archive(), self.item())
        self.crash_process('remove')
        self.recover()
        self.assertTrue(library.mod_folder(item).is_dir())
        self.assertIn('sample', library.installed())

    def test_real_process_exit_during_restore_keeps_backup(self):
        library.import_archive(self.archive(), self.item())
        library.remove('sample')
        original_backup = library.removed()[0]['backup_id']
        self.crash_process('restore')
        self.recover()
        self.assertEqual(library.installed(), {})
        self.assertEqual(library.removed()[0]['backup_id'], original_backup)
