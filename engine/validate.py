"""Validate a prepared artifact and its source fingerprint; never apply it."""
import json
import hashlib
from pathlib import Path, PurePosixPath
from .selection import Selection
from .prepare import _sha256
from .wad import read_index


def validate(directory: Path, *, expected_selection=None, game=None):
    directory = Path(directory).resolve()
    path = directory/'manifest.json'
    if path.stat().st_size > 4*1024**2:
        raise ValueError('Manifest exceeds limit')
    manifest_bytes=path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if (not isinstance(manifest,dict) or type(manifest.get('schema')) is not int
            or manifest['schema'] != 1):
        raise ValueError('Unsupported build manifest')
    selection = manifest.get('selection')
    if not isinstance(selection,dict) or set(selection) != {'session_id','champion_id','skin_id'}:
        raise ValueError('Invalid selection identity')
    selection = Selection(**selection)
    if expected_selection is not None and selection != expected_selection:
        raise ValueError('Prepared artifact belongs to another selection')
    expected_state = 'base_selected' if selection.is_base else 'prepared_offline'
    if manifest.get('state') != expected_state:
        raise ValueError('Build is incomplete or superseded')
    if type(manifest.get('base_skin_id')) is not int or manifest['base_skin_id'] != selection.base_skin_id:
        raise ValueError('Base skin identity mismatch')
    if any(manifest.get(key) is not False for key in ('runtime_available','applied','game_ready')):
        raise ValueError('Offline artifact cannot claim runtime application')
    archives = manifest.get('archives')
    if not isinstance(archives,list) or len(archives)>20000:
        raise ValueError('Invalid archive list')
    if (selection.is_base and archives) or (not selection.is_base and not archives):
        raise ValueError('Archive list does not match base/modified selection')
    seen = set()
    for archive in archives:
        if not isinstance(archive,dict) or not isinstance(archive.get('path'),str):
            raise ValueError('Invalid archive record')
        name = archive['path']
        parts = name.split('/')
        if (len(parts)<3 or parts[:2] != ['DATA','FINAL'] or '\\' in name
                or any(p in ('','.','..') or ':' in p for p in parts)
                or not name.lower().endswith('.wad.client') or PurePosixPath(name).is_absolute()):
            raise ValueError('Invalid prepared archive path')
        if name.casefold() in seen:
            raise ValueError('Duplicate prepared archive')
        seen.add(name.casefold())
        file = directory/name
        if not file.resolve().is_relative_to(directory):
            raise ValueError('Prepared archive escapes build directory')
        if _sha256(file) != archive.get('output_sha256'):
            raise ValueError('Prepared archive content changed')
        with file.open('rb') as source:
            if len(read_index(source)) != archive.get('entries'):
                raise ValueError('Prepared archive table changed')
        if game is not None:
            game_root = Path(game).resolve()
            original = (game_root/name).resolve()
            if not original.is_relative_to(game_root) or _sha256(original) != archive.get('source_sha256'):
                raise ValueError('Installed game changed; rebuild required')
    return {'validated_archives':len(archives),'selection':manifest['selection'],
            'manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest(),
            'runtime_available':False,'game_ready':False,'applied':False}
