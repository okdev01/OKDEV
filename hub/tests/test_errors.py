import errno
import unittest
import zipfile

import requests

from hub.errors import message
from hub.desktop import Api


class PublicErrorTests(unittest.TestCase):
    def test_machine_and_network_details_never_escape(self):
        private = 'C:/private/user/secret?token=hidden'
        examples = [(OSError(errno.ENOSPC, private), 'boş alan'),
                    (PermissionError(private), 'erişilemiyor'),
                    (FileNotFoundError(private), 'bulunamadı'),
                    (requests.Timeout(private), 'zamanında'),
                    (requests.ConnectionError(private), 'bağlanılamadı'),
                    (requests.HTTPError(private), 'Kaynak sunucu'),
                    (zipfile.BadZipFile(private), 'paketi bozuk'),
                    (RuntimeError(private), 'İşlem tamamlanamadı')]
        for error, expected in examples:
            with self.subTest(error=type(error).__name__):
                result = message(error)
                self.assertIn(expected, result)
                self.assertNotIn('private', result)
                self.assertNotIn('hidden', result)

    def test_validation_messages_remain_useful_and_bounded(self):
        self.assertEqual(message(ValueError('Şampiyon eşleşmiyor.')), 'Şampiyon eşleşmiyor.')
        self.assertEqual(len(message(ValueError('x' * 1000))), 500)
        self.assertTrue(message(ValueError()))

    def test_api_uses_same_sanitized_error_contract(self):
        def action():
            raise OSError(errno.ENOSPC, 'private disk path')
        result = Api()._run(action)
        self.assertFalse(result['ok'])
        self.assertIn('boş alan', result['error'])
        self.assertNotIn('private', result['error'])
