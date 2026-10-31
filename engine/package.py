"""Inspect a local package without extracting files or touching the game."""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath

MAX_FILES = 20000
MAX_TOTAL = 2 * 1024**3
MAX_METADATA = 1024**2


def inspect_package(path: Path) -> dict:
    """Validate a Fantome archive layout; this does not validate game compatibility."""
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_FILES:
            raise ValueError("Too many package entries")
        seen = set()
        total = 0
        wads = []
        for entry in entries:
            name = entry.orig_filename
            if name != entry.filename or '\x00' in name:
                raise ValueError('Normalized or truncated package path')
            parts = PurePosixPath(name).parts
            if (not parts or name.startswith('/') or '\\' in name
                    or any(p in ('.', '..') or ':' in p for p in name.split('/') if p)):
                raise ValueError("Unsafe package path")
            key = name.casefold().rstrip('/')
            if key in seen:
                raise ValueError("Duplicate package path")
            seen.add(key)
            if entry.flag_bits & 1 or stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError("Encrypted entries and symlinks are unsupported")
            total += entry.file_size
            if total > MAX_TOTAL:
                raise ValueError("Package exceeds expanded size limit")
            if not entry.is_dir() and parts[0] == 'WAD':
                wads.append(name)
        metadata_entry = archive.getinfo('META/info.json')
        if metadata_entry.file_size > MAX_METADATA:
            raise ValueError("Metadata exceeds size limit")
        metadata = json.loads(archive.read(metadata_entry))
        if (not isinstance(metadata, dict) or not isinstance(metadata.get('Name'), str)
                or not metadata['Name'].strip()):
            raise ValueError("Missing package name")
        if not wads:
            raise ValueError("Package contains no WAD payload")
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024**2), b''):
            digest.update(block)
    return {'engine': 'okdev-offline', 'name': metadata['Name'],
            'sha256': digest.hexdigest(), 'expanded_bytes': total,
            'wad_entries': wads, 'runtime_available': False,
            'game_compatibility': 'not_checked'}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(inspect_package(args.package), ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        parser.exit(2, f'Package rejected: {error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
