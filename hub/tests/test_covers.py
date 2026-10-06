import base64
import io

from PIL import Image

from hub import covers, library
from hub.tests.test_library import LibraryFixture


class CoverTests(LibraryFixture):
    def package(self, color='red', name='sample.fantome'):
        data = io.BytesIO()
        Image.new('RGBA', (1200, 800), color).save(data, 'PNG')
        return self.archive(name, {'META/image.png': data.getvalue(), 'WAD/Ahri.wad.client': b'fixture'})

    def test_cover_is_resized_and_embedded_as_jpeg(self):
        self.assertTrue(covers.save_from_archive(self.package(), 'sample'))
        value = covers.preview('sample')
        self.assertTrue(value.startswith('data:image/jpeg;base64,'))
        with Image.open(io.BytesIO(base64.b64decode(value.split(',', 1)[1]))) as image:
            self.assertEqual(image.format, 'JPEG')
            self.assertLessEqual(image.width, 640)
            self.assertLessEqual(image.height, 360)

    def test_invalid_image_does_not_block_import(self):
        package = self.archive(files={'META/image.png': b'broken image', 'WAD/Ahri.wad.client': b'fixture'})
        result = library.import_archive(package, self.item())
        self.assertIsNone(result['cover_key'])
        self.assertTrue(library.mod_folder(result).is_dir())

    def test_disguised_unsupported_image_is_not_decoded_as_a_cover(self):
        data = io.BytesIO()
        Image.new('RGB', (12, 12), 'red').save(data, 'GIF')
        package = self.archive(files={'META/image.png': data.getvalue(), 'WAD/Ahri.wad.client': b'fixture'})
        self.assertFalse(covers.save_from_archive(package, 'sample'))
        self.assertIsNone(library.import_archive(package, self.item())['cover_key'])

    def test_restoring_old_version_restores_its_cover(self):
        first = library.import_archive(self.package(), self.item())
        first_preview = covers.preview(first['cover_key'])
        second = library.import_archive(self.package('blue', 'next.fantome'), dict(self.item(), version='2.0.0'))
        self.assertNotEqual(first['cover_key'], second['cover_key'])
        self.assertNotEqual(first_preview, covers.preview(second['cover_key']))
        old_backup = next(m for m in library.removed() if m['version'] == '1.0.0')
        library.remove('sample')
        restored = library.restore(old_backup['backup_id'])
        self.assertEqual(covers.preview(restored['cover_key']), first_preview)

    def test_preview_refuses_unsafe_key_and_oversized_file(self):
        self.assertIsNone(covers.preview('../outside'))
        folder = library.root() / 'covers'
        folder.mkdir()
        (folder / 'sample.jpg').write_bytes(b'x' * (512 * 1024 + 1))
        self.assertIsNone(covers.preview('sample'))
