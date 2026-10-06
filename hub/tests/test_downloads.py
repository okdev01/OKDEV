import hashlib
from unittest.mock import Mock, patch

from hub import library
from hub.tests.test_library import LibraryFixture


class DownloadTests(LibraryFixture):
    def prepare(self, chunks, length=None):
        item = self.item(sha256=hashlib.sha256(b''.join(chunks)).hexdigest(),
                         url='https://github.com/okdev01/OKDEV/releases/download/test/mod.fantome')
        library.write_json(library.root() / 'catalog.json', {'schema': 1, 'mods': [item]})
        response = Mock(headers={} if length is None else {'Content-Length': str(length)})
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_content.return_value = iter(chunks)
        return response

    def test_progress_finishes_with_verified_installation(self):
        content = self.archive().read_bytes()
        progress = []
        response = self.prepare([content[:100], content[100:]], len(content))
        with patch.object(library.requests, 'get', return_value=response):
            library.download('sample', progress.append)
        self.assertEqual(progress[-1], {'stage': 'installing', 'received': len(content), 'total': len(content)})
        self.assertIn('sample', library.installed())

    def test_cancellation_removes_partial_file_without_installing(self):
        content = self.archive().read_bytes()
        response = self.prepare([content[:100], content[100:]])
        checks = iter([False, False, True])
        with patch.object(library.requests, 'get', return_value=response), self.assertRaisesRegex(ValueError, 'iptal'):
            library.download('sample', cancelled=lambda: next(checks))
        self.assertFalse(list(library.root().glob('*.partial')))
        self.assertEqual(library.installed(), {})

    def test_oversized_content_length_is_rejected_before_reading(self):
        response = self.prepare([b'bad'], library.MAX_DOWNLOAD + 1)
        with patch.object(library.requests, 'get', return_value=response), self.assertRaisesRegex(ValueError, 'sınır'):
            library.download('sample')
        response.iter_content.assert_not_called()

    def test_local_snapshot_never_accesses_network(self):
        from hub.desktop import Api
        with patch.object(library.requests, 'get', side_effect=AssertionError('network')):
            snapshot = Api().snapshot()
        self.assertEqual(snapshot['catalog'], [])
