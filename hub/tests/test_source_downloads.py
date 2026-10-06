import hashlib
from unittest.mock import Mock, patch

from hub import library, sources
from hub.tests.test_library import LibraryFixture


class SourceDownloadTests(LibraryFixture):
    def setUp(self):
        super().setUp()
        self.content = self.archive().read_bytes()
        self.item_data = self.item('rf-fixture', category='skins', author='Original artist', license='CC-BY-4.0')
        self.item_data.update(source_url='https://runeforge.dev/mods/356044a5-2d63-4089-b9af-b63bede9dcb6',
            download_url='https://r2-prod.runeforge.dev/mod_releases%2F356044a5-2d63-4089-b9af-b63bede9dcb6%2Ffixture.fantome',
            sha256=hashlib.sha256(self.content).hexdigest(), download_size=len(self.content))

    def response(self, content=None, status=200):
        response = Mock(status_code=status, headers={})
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_content.return_value = [self.content if content is None else content]
        return response

    def test_original_host_download_preserves_credit_and_stays_disabled(self):
        with patch.object(sources, 'entries', return_value=[self.item_data]), patch.object(library.requests, 'get', return_value=self.response()) as get:
            result = library.download_source('rf-fixture')
        self.assertEqual(result['author'], 'Original artist')
        self.assertEqual(result['license'], 'CC-BY-4.0')
        self.assertFalse(result['enabled'])
        self.assertEqual(get.call_args.args[0], self.item_data['download_url'])
        self.assertFalse(get.call_args.kwargs['allow_redirects'])
        self.assertFalse(list(library.root().glob('*.fantome')))

    def test_changed_source_file_is_not_installed(self):
        with patch.object(sources, 'entries', return_value=[self.item_data]), patch.object(library.requests, 'get', return_value=self.response(b'changed')):
            with self.assertRaisesRegex(ValueError, 'doğrulanamadı'):
                library.download_source('rf-fixture')
        self.assertEqual(library.installed(), {})

    def test_source_redirect_is_rejected_without_reading_body(self):
        response = self.response(status=302)
        with patch.object(sources, 'entries', return_value=[self.item_data]), patch.object(library.requests, 'get', return_value=response):
            with self.assertRaisesRegex(ValueError, 'Kaynak adresi'):
                library.download_source('rf-fixture')
        response.iter_content.assert_not_called()

    def test_source_download_binding_rejects_foreign_host_and_mod(self):
        self.assertTrue(sources.valid_download(self.item_data))
        for url in ('https://evil.example/package.fantome',
                    self.item_data['download_url'].replace('https:', 'http:'),
                    self.item_data['download_url'].replace('356044a5', '00000000'),
                    self.item_data['download_url'].replace('fixture.fantome', '..%2Ffixture.fantome')):
            self.assertFalse(sources.valid_download(dict(self.item_data, download_url=url)))

    def test_curated_preview_only_accepts_expected_image_service(self):
        url='https://runeforge.dev/cdn-cgi/image/width=640,height=360/https://r2-images-prod.runeforge.dev/example.png'
        self.assertTrue(sources.valid_preview(url))
        self.assertFalse(sources.valid_preview(url.replace('r2-images-prod.runeforge.dev', 'evil.example')))
        self.assertFalse(sources.valid_preview(url + '?token=anything'))
