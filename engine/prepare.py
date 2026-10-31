"""Prepare one champion selection into a separate offline build directory."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import tempfile
import shutil
import re
from .selection import Selection
from .build import build
from .manifest import write_manifest


def _sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024**2), b''):
            digest.update(block)
    return digest.hexdigest()


def resolve_package(library: Path, selection: Selection):
    """Resolve base skins and nested chromas without fuzzy cross-skin matches."""
    champion_root = library / str(selection.champion_id)
    candidates = []
    for suffix in ('.fantome', '.zip'):
        direct = champion_root / str(selection.skin_id) / f'{selection.skin_id}{suffix}'
        if direct.is_file():
            candidates = [direct]
            break
    if not candidates and champion_root.is_dir():
        for suffix in ('.fantome', '.zip'):
            candidates.extend(champion_root.rglob(f'{selection.skin_id}{suffix}'))
    if len(candidates) != 1:
        raise ValueError('Selected package is missing or ambiguous')
    package = candidates[0].resolve()
    if not package.is_relative_to(library.resolve()):
        raise ValueError('Package resolves outside skin library')
    return package


def prepare(selection: Selection, library: Path, game: Path, output_root: Path):
    """Resolve the selected package, build, verify, then publish a manifest last.

    Output directories must be outside the game installation and skin library.
    A prepared result is explicitly not an applied result.
    """
    library, game, output_root = (Path(p).resolve() for p in (library, game, output_root))
    for source in (game, library):
        if output_root == source or source in output_root.parents:
            raise ValueError('Output must be outside source directories')
    package = None if selection.is_base else resolve_package(library, selection)
    output_root.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix='selection-', dir=output_root))
    try:
        manifest = {'schema': 1, 'selection': asdict(selection),
                    'base_skin_id': selection.base_skin_id,
                    'state': 'base_selected' if selection.is_base else 'prepared_offline',
                    'runtime_available': False, 'applied': False,
                    'game_ready': False, 'archives': [], 'skipped_optional_archives': []}
        if not selection.is_base:
            from .package import inspect_package
            package_info = inspect_package(package)
            manifest['package_sha256'] = package_info['sha256']
            payloads = package_info['wad_entries']
            if any(len(p.split('/')) != 2 or not p.lower().endswith('.wad.client') for p in payloads):
                raise ValueError('Only complete top-level WAD archives are currently supported')
            for name in payloads:
                candidates = [p for p in (game/'DATA'/'FINAL').rglob('*.wad.client')
                              if p.name.casefold() == name.split('/')[-1].casefold()]
                if not candidates and re.fullmatch(r'[\w-]+\.[a-zA-Z]{2}_[a-zA-Z]{2}\.wad\.client', name.split('/')[-1]):
                    manifest['skipped_optional_archives'].append({
                        'archive':name,'reason':'locale_not_installed'})
                    continue
                if len(candidates) != 1:
                    raise ValueError(f'Expected exactly one installed archive for {name}')
                original = candidates[0]
                if not original.resolve().is_relative_to(game):
                    raise ValueError('Game archive resolves outside installation')
                relative = original.relative_to(game)
                output = destination / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                source_hash = _sha256(original)
                report = build(package, original, output)
                if _sha256(original) != source_hash:
                    raise ValueError('Game changed while preparing; retry after update')
                manifest['archives'].append({'path': relative.as_posix(),
                    'source_sha256': source_hash, 'output_sha256': _sha256(output), **report})
            if not manifest['archives']:
                raise ValueError('No installed archive can receive this package')
            if _sha256(package) != package_info['sha256']:
                raise ValueError('Skin package changed while preparing')
        # A completed manifest is the commit marker. Incomplete builds are removed.
        write_manifest(destination,manifest)
        return destination, manifest
    except BaseException:
        # destination is created exclusively by this invocation beneath output_root.
        shutil.rmtree(destination)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session-id', required=True)
    parser.add_argument('--champion-id', required=True, type=int)
    parser.add_argument('--skin-id', required=True, type=int)
    parser.add_argument('--library', required=True, type=Path)
    parser.add_argument('--game', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    selection = Selection(args.session_id, args.champion_id, args.skin_id)
    destination, manifest = prepare(selection, args.library, args.game, args.output)
    print(json.dumps({'directory': str(destination), **manifest}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
