"""User-selected exports must not replace the application's live state."""
from pathlib import Path

from . import library


def destination(value, suffixes=('.json',)):
    path = Path(value)
    if path.suffix.lower() not in suffixes:
        raise ValueError('Dosyayı ' + ' veya '.join(suffixes) + ' uzantısıyla kaydet.')
    if path.resolve().is_relative_to(library.get_user_data_dir().resolve()):
        raise ValueError('Dışa aktarılan dosyayı OKDEV veri klasörü dışında bir konuma kaydet.')
    if path.is_symlink():
        raise ValueError('Dışa aktarma için dosya bağlantısı yerine normal bir dosya konumu seç.')
    return path


def write_json(value, document):
    library.write_json(destination(value), document)
