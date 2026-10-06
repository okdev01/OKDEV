"""Round-trip every cached curated package through production backup export.

The cache is read-only. All imports, removals, exports and reimports use a fresh
temporary data directory for each package. No game or public network is used.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def manifest(folder):
    result = {}
    for path in folder.rglob('*'):
        if path.is_file():
            relative = path.relative_to(folder).as_posix()
            if relative.lower() == 'meta/okdev-backup.json':
                continue  # Export's optional descriptive note is not game data.
            with path.open('rb') as stream:
                result[relative.casefold()] = (path.stat().st_size, hashlib.file_digest(stream, 'sha256').hexdigest())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', required=True, type=Path)
    parser.add_argument('--report', type=Path, default=ROOT / 'build/backup-roundtrips.json')
    args = parser.parse_args()
    from utils.core import paths
    from hub import library, backups, sources, package_info
    previous = paths._cached_user_data_dir, paths._migration_checked
    report = {'ok': False, 'running': True, 'results': [], 'scope': __doc__,
              'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                               for name in ('hub/library.py', 'hub/backups.py', 'utils/core/atomic_file.py')}}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    try:
        for source in sources.entries():
            started = time.monotonic()
            result = {'id': source['id'], 'ok': False}
            try:
                package = args.cache / (source['id'] + '.fantome')
                original_stat = package.stat()
                with package.open('rb') as stream:
                    assert hashlib.file_digest(stream, 'sha256').hexdigest() == source['sha256']
                with tempfile.TemporaryDirectory(prefix='okdev-backup-qa-') as temporary:
                    base = Path(temporary)
                    paths._cached_user_data_dir, paths._migration_checked = base / 'data', True
                    original = library.import_archive(package, source)
                    original_files = manifest(library.mod_folder(original))
                    assert original_files, 'No extracted payload'
                    library.remove(source['id'])
                    backup = library.removed()[0]
                    saved = base / 'export.fantome'
                    backups.export(backup['backup_id'], saved)
                    info = package_info.inspect(saved)
                    assert info['suggested']['name'], 'Export metadata unreadable'
                    imported = library.import_archive(saved, source)
                    assert not imported['enabled']
                    assert manifest(library.mod_folder(imported)) == original_files, 'Reimport changed file bytes or names'
                    backup_folder = library.root() / 'removed' / backup['backup_id'] / 'mod'
                    assert manifest(backup_folder) == original_files, 'Export changed original backup'
                    assert len(library.removed()) == 1
                    assert not list((library.root() / 'pending').glob('*.json'))
                    result.update(ok=True, files=len(original_files), bytes=sum(size for size, _ in original_files.values()),
                                  exported_bytes=saved.stat().st_size, source_sha256=source['sha256'])
                current_stat = package.stat()
                assert (original_stat.st_size, original_stat.st_mtime_ns) == (current_stat.st_size, current_stat.st_mtime_ns), 'Read-only cache changed'
            except Exception as exc:
                result.update(ok=False, error=f'{type(exc).__name__}: {exc}')
            result['seconds'] = round(time.monotonic() - started, 2)
            report['results'].append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
            library.write_json(args.report, report)
        report.update(ok=bool(report['results']) and all(item['ok'] for item in report['results']), running=False)
    finally:
        paths._cached_user_data_dir, paths._migration_checked = previous
        library.write_json(args.report, report)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
