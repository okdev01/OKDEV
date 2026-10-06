"""Publish immutable mod assets and update the independent public catalog."""
import base64
import hashlib
import json
import re
from pathlib import Path
import requests
from .library import validate_archive, validate_catalog

API = 'https://api.github.com/repos/okdev01/OKDEV'


def publish(path, item, token, cover=None):
    # The existing public schema-1 channel is still consumed by older clients.
    # Category packages and upstream build versions remain local until a
    # separately versioned publishing channel is introduced.
    if item.get('category', 'skins') != 'skins' or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', str(item.get('version', ''))):
        raise ValueError('Herkese açık kanal şimdilik yalnızca şampiyon modları ve 1.0.0 biçimindeki sürümleri destekler.')
    path = Path(path)
    validate_archive(path)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    tag = f"mod-{item['id']}-{item['version']}-{digest[:10]}"
    filename = f"{item['id']}-{item['version']}.fantome"
    item = dict(item, sha256=digest, url=f'https://github.com/okdev01/OKDEV/releases/download/{tag}/{filename}')
    cover_name = None
    if cover:
        cover = Path(cover)
        if cover.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('Görsel en fazla 8 MB olabilir')
        from PIL import Image
        with Image.open(cover, formats=('PNG', 'JPEG', 'WEBP')) as image:
            if image.width * image.height > 16_000_000:
                raise ValueError('Görsel en fazla 16 milyon piksel olabilir')
            image.verify()
        if cover.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
            raise ValueError('PNG, JPEG veya WebP görseli seçin')
        cover_name = 'cover-' + hashlib.sha256(cover.read_bytes()).hexdigest()[:12] + cover.suffix.lower()
        item['image_url'] = f'https://github.com/okdev01/OKDEV/releases/download/{tag}/{cover_name}'
    validate_catalog({'schema': 1, 'mods': [item]})
    if not isinstance(token, str) or not token.strip():
        raise ValueError('Yayımlamak için bu depoya yazma yetkisi olan GitHub erişim anahtarı gerekli')
    with requests.Session() as session:
        session.headers.update({'Authorization': 'Bearer ' + token.strip(), 'Accept': 'application/vnd.github+json',
                                'X-GitHub-Api-Version': '2022-11-28'})

        def check(response):
            if not response.ok:
                if response.status_code in (401, 403):
                    raise ValueError('GitHub yetkilendirmesi başarısız. OKDEV deposuna Contents yazma yetkisini kontrol edin.')
                raise ValueError(f'GitHub işlemi tamamlanamadı (HTTP {response.status_code}). Yenileyip tekrar deneyin.')
            return response.json()

        current_response = session.get(API + '/contents/mods/catalog.json', timeout=20)
        current = None if current_response.status_code == 404 else check(current_response)
        catalog = {'schema': 1, 'mods': []} if current is None else validate_catalog(json.loads(base64.b64decode(current['content'])))
        response = session.get(API + '/releases/tags/' + tag, timeout=20)
        release = None if response.status_code == 404 else check(response)
        if release is None:
            release = check(session.post(API + '/releases', json={
                'tag_name': tag, 'name': item['name'] + ' ' + item['version'], 'draft': True,
                'prerelease': True, 'make_latest': 'false', 'body': 'OKDEV mod kütüphanesi dosyası.'}, timeout=20))
        asset = next((a for a in release.get('assets', []) if a['name'] == filename), None)
        if asset is None:
            with path.open('rb') as stream:
                check(session.post(release['upload_url'].split('{')[0], params={'name': filename}, data=stream,
                                   headers={'Content-Type': 'application/octet-stream'}, timeout=(15, 180)))
        if cover and not any(a['name'] == cover_name for a in release.get('assets', [])):
            with cover.open('rb') as stream:
                check(session.post(release['upload_url'].split('{')[0], params={'name': cover_name}, data=stream,
                                   headers={'Content-Type': 'application/octet-stream'}, timeout=(15, 90)))
        if release.get('draft'):
            check(session.patch(API + '/releases/' + str(release['id']), json={'draft': False, 'prerelease': True, 'make_latest': 'false'}, timeout=20))
        catalog['mods'] = [m for m in catalog['mods'] if m['id'] != item['id']] + [item]
        body = {'message': 'Update OKDEV mod catalog: ' + item['id'],
                'content': base64.b64encode(json.dumps(catalog, ensure_ascii=False, indent=2).encode()).decode(), 'branch': 'main'}
        if current:
            body['sha'] = current['sha']
        check(session.put(API + '/contents/mods/catalog.json', json=body, timeout=25))
        return item
