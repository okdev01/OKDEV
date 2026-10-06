"""Curated source links, not mirrored third-party download packages."""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote


def valid_preview(url):
    return isinstance(url, str) and re.fullmatch(
        r'https://runeforge\.dev/cdn-cgi/image/[a-zA-Z0-9=,.-]+/https://r2-images-prod\.runeforge\.dev/[a-zA-Z0-9_-]+\.(?:png|jpe?g|webp|gif|avif)', url) is not None


def valid_download(item):
    url = item.get('download_url')
    if not isinstance(url, str):
        return False
    parsed = urlparse(url)
    source_id = item['source_url'].rsplit('/', 1)[-1]
    path = unquote(parsed.path)
    return (parsed.scheme == 'https' and parsed.netloc == 'r2-prod.runeforge.dev'
            and any(path.startswith('/' + kind + '/' + source_id + '/') for kind in ('mod_release_artifacts', 'mod_releases'))
            and '..' not in path.split('/') and '\\' not in path
            and isinstance(item.get('sha256'), str) and re.fullmatch('[a-f0-9]{64}', item['sha256']) is not None
            and type(item.get('download_size')) is int and 0 < item['download_size'] <= 512 * 1024 * 1024)


def entries():
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    data = json.loads((base / 'hub/web/sources.json').read_text(encoding='utf-8'))
    for item in data['mods']:
        if not re.fullmatch(r'https://runeforge\.dev/mods/[a-f0-9-]{36}', item['source_url']):
            raise ValueError('Geçersiz kaynak adresi')
        if item.get('image_url') and not valid_preview(item['image_url']):
            raise ValueError('Geçersiz kaynak görseli')
        if item.get('download_url') and not valid_download(item):
            raise ValueError('Geçersiz kaynak indirmesi')
    return data['mods']
