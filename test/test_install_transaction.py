import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import okdev_install_transaction as transaction
from okdev_update_helper import apply_update


class InstallationTransactionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='okdev-install-recovery-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.target = self.root / 'OKDEV'
        self.prepared = self.root / '.okdev-update-abcdef123456'
        self.backup = self.root / 'OKDEV.backup-abcdef123456'
        for folder, version in ((self.target, 'old'), (self.prepared, 'new')):
            folder.mkdir()
            (folder / 'OKDEV.exe').write_bytes(version.encode())
            (folder / 'okdev-install.json').write_text(json.dumps({'install_id': 'fixture', 'version': version}))
            (folder / 'config.ini').write_text('keep user settings')

    def journal(self):
        record = {'schema': 1, 'target': self.target.name, 'prepared': self.prepared.name,
                  'backup': self.backup.name, 'before': transaction._fingerprint(self.target),
                  'after': transaction._fingerprint(self.prepared)}
        transaction.journal_path(self.target).write_text(json.dumps(record), encoding='utf-8')
        return record

    def recover(self):
        with transaction.installation_lock(self.target):
            return transaction.recover(self.target)

    def test_normal_commit_keeps_original_backup_and_clears_journal(self):
        transaction.commit(self.target, self.prepared, self.backup)
        self.assertEqual((self.target / 'OKDEV.exe').read_bytes(), b'new')
        self.assertEqual((self.backup / 'OKDEV.exe').read_bytes(), b'old')
        self.assertFalse(transaction.journal_path(self.target).exists())
        self.assertFalse(self.recover()['recovered'])

    def test_journal_before_first_rename_preserves_both_folders(self):
        self.journal()
        self.assertEqual(self.recover()['status'], 'not_started')
        self.assertEqual((self.target / 'OKDEV.exe').read_bytes(), b'old')
        self.assertEqual((self.prepared / 'OKDEV.exe').read_bytes(), b'new')

    def test_interruption_between_renames_restores_original(self):
        self.journal()
        self.target.rename(self.backup)
        result = self.recover()
        self.assertEqual(result['status'], 'rolled_back')
        self.assertEqual((self.target / 'OKDEV.exe').read_bytes(), b'old')
        self.assertEqual((self.target / 'config.ini').read_text(), 'keep user settings')
        self.assertTrue(self.prepared.exists())
        self.assertFalse(self.backup.exists())
        self.assertFalse(self.recover()['recovered'])

    def test_interruption_after_commit_keeps_new_application(self):
        self.journal()
        self.target.rename(self.backup)
        self.prepared.rename(self.target)
        self.assertEqual(self.recover()['status'], 'completed')
        self.assertEqual((self.target / 'OKDEV.exe').read_bytes(), b'new')
        self.assertEqual((self.backup / 'OKDEV.exe').read_bytes(), b'old')

    def test_ordinary_rename_failure_rolls_back_immediately(self):
        original = Path.rename
        def rename(source, target):
            if source == self.prepared:
                raise PermissionError('locked')
            return original(source, target)
        with patch.object(Path, 'rename', rename), self.assertRaises(PermissionError):
            transaction.commit(self.target, self.prepared, self.backup)
        self.assertEqual((self.target / 'OKDEV.exe').read_bytes(), b'old')
        self.assertTrue(self.prepared.exists())
        self.assertFalse(transaction.journal_path(self.target).exists())

    def test_changed_backup_never_replaces_missing_target(self):
        self.journal()
        self.target.rename(self.backup)
        (self.backup / 'OKDEV.exe').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            self.recover()
        self.assertFalse(self.target.exists())
        self.assertTrue(self.prepared.exists())
        self.assertTrue(transaction.journal_path(self.target).exists())

    def test_external_target_change_is_preserved(self):
        self.journal()
        (self.target / 'OKDEV.exe').write_bytes(b'external change')
        with self.assertRaises(ValueError):
            self.recover()
        self.assertEqual((self.target / 'OKDEV.exe').read_bytes(), b'external change')
        self.assertTrue(self.prepared.exists())

    def test_malformed_and_escaping_journal_stays_untouched(self):
        record = self.journal()
        path = transaction.journal_path(self.target)
        for value in ('{broken', json.dumps({**record, 'prepared': '../outside'}),
                      json.dumps({**record, 'schema': True}), json.dumps({**record, 'before': {'metadata': 'invalid'}})):
            path.write_text(value, encoding='utf-8')
            with self.assertRaises(ValueError):
                self.recover()
            self.assertEqual(path.read_text(encoding='utf-8'), value)
            self.assertEqual((self.target / 'OKDEV.exe').read_bytes(), b'old')

    def crash(self, stage):
        code = '''
import os, sys
from pathlib import Path
import okdev_install_transaction as transaction
root=Path(sys.argv[1]); stage=sys.argv[2]
original=Path.rename
def rename(source,target):
    result=original(source,target)
    if (stage=='between' and source.name=='OKDEV') or (stage=='after' and source.name.startswith('.okdev-update-')):
        os._exit(73)
    return result
Path.rename=rename
transaction.commit(root/'OKDEV',root/'.okdev-update-abcdef123456',root/'OKDEV.backup-abcdef123456')
'''
        result = subprocess.run([sys.executable, '-c', code, str(self.root), stage], capture_output=True,
                                timeout=15, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual(result.returncode, 73, result.stderr.decode(errors='replace'))

    def test_real_process_death_between_folder_renames_is_recovered(self):
        self.crash('between')
        self.assertFalse(self.target.exists())
        self.assertEqual(self.recover()['status'], 'rolled_back')
        self.assertEqual((self.target / 'OKDEV.exe').read_bytes(), b'old')

    def test_real_process_death_after_commit_keeps_new_version(self):
        self.crash('after')
        self.assertEqual(self.recover()['status'], 'completed')
        self.assertEqual((self.target / 'OKDEV.exe').read_bytes(), b'new')

    def test_updater_recovers_missing_install_before_retrying(self):
        self.crash('between')
        payload = self.root / 'payload'
        payload.mkdir()
        (payload / 'OKDEV.exe').write_bytes(b'latest')
        (payload / 'okdev-update.json').write_text('{"app":"OKDEV","version":"1.5.0"}')
        backup = apply_update(self.target, payload)
        self.assertEqual((self.target / 'OKDEV.exe').read_bytes(), b'latest')
        self.assertEqual((backup / 'OKDEV.exe').read_bytes(), b'old')
        self.assertEqual((self.target / 'config.ini').read_text(), 'keep user settings')

    def test_existing_backup_is_never_overwritten(self):
        self.backup.mkdir()
        (self.backup / 'personal.txt').write_text('keep')
        with self.assertRaises(ValueError):
            transaction.commit(self.target, self.prepared, self.backup)
        self.assertEqual((self.backup / 'personal.txt').read_text(), 'keep')
        self.assertEqual((self.target / 'OKDEV.exe').read_bytes(), b'old')
