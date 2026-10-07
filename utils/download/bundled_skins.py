"""Install verified, missing patch assets after the upstream library sync.

Never replace a package or translation already supplied by the library.
"""
import hashlib
import json
import os
import tempfile
from pathlib import Path

from utils.core.atomic_file import write_text_atomic
from utils.core.paths import get_assets_dir, get_user_data_dir
from utils.core.safe_extract import join_within


def install_bundled_skins(bundle_dir=None, data_dir=None):
    bundle = (Path(bundle_dir) if bundle_dir else get_assets_dir() / 'skin-patches' / '26.20').resolve()
    target = (Path(data_dir) if data_dir else get_user_data_dir()).resolve()
    manifest_path = bundle / 'manifest.json'
    if not manifest_path.is_file():
        return 0
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    prepared = []
    # Verify the complete bundle before creating any user files.
    for item in manifest['packages']:
        relative = item['path']
        source = join_within(bundle, relative)
        destination = join_within(target / 'skins', relative)
        if not source or not destination or Path(relative).suffix != '.fantome':
            raise ValueError('Invalid bundled skin path')
        raw = Path(source).read_bytes()
        if hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('Bundled skin checksum mismatch: ' + relative)
        prepared.append((Path(destination), raw))
    installed = 0
    for destination, raw in prepared:
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Publish a complete file atomically, without overwriting a concurrent
        # upstream download. Both paths are on the same filesystem.
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            try:
                os.link(temporary, destination)
                installed += 1
            except FileExistsError:
                pass
        finally:
            temporary.unlink(missing_ok=True)
    for language, names in manifest['names'].items():
        if language not in ('default', 'en', 'tr'):
            raise ValueError('Unexpected bundled language')
        mapping_path = target / 'resources' / language / 'skin_ids.json'
        # A supplement must not masquerade as the full champion catalog.
        if not mapping_path.is_file():
            continue
        mapping = json.loads(mapping_path.read_text(encoding='utf-8'))
        changed = False
        for skin_id, name in names.items():
            if skin_id not in mapping:
                mapping[skin_id] = name
                changed = True
        if changed:
            write_text_atomic(mapping_path, json.dumps(mapping, ensure_ascii=False, indent=2) + '\n')
    return installed
