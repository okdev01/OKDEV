"""Bounded local thumbnails from package metadata; no remote image requests."""
import base64
import io
import zipfile

from . import library
from utils.core.atomic_file import atomic_write


def save_from_archive(path, mod_id):
    if not library.valid_id(mod_id):
        return False
    from PIL import Image, UnidentifiedImageError
    try:
        with zipfile.ZipFile(path) as archive:
            entry = next((f for f in archive.infolist() if f.filename.lower() in {
                'meta/image.png', 'meta/image.jpg', 'meta/image.jpeg', 'info/image.png'}), None)
            if not entry or entry.file_size > 8 * 1024 * 1024:
                return False
            with Image.open(io.BytesIO(archive.read(entry)), formats=('PNG', 'JPEG')) as image:
                if image.width * image.height > 16_000_000:
                    return False
                image.thumbnail((640, 360))
                image = image.convert('RGB')
                target = library.root() / 'covers' / (mod_id + '.jpg')
                target.parent.mkdir(parents=True, exist_ok=True)
                with atomic_write(target, 'wb') as stream:
                    image.save(stream, format='JPEG', quality=82)
        return True
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError, UnidentifiedImageError, Image.DecompressionBombError):
        return False


def preview(mod_id):
    if not library.valid_id(mod_id):
        return None
    try:
        path = library.root() / 'covers' / (mod_id + '.jpg')
        if path.stat().st_size > 512 * 1024:
            return None
        return 'data:image/jpeg;base64,' + base64.b64encode(path.read_bytes()).decode('ascii')
    except OSError:
        return None
