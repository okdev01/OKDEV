"""Revalidate pinned community packages and import into disposable user data.

Reads a supplied local cache; never downloads, changes the cache, activates a
mod, starts a game, or reads the user's real library.
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    arguments = parser.parse_args()
    from utils.core import paths
    previous = paths._cached_user_data_dir, paths._migration_checked
    report = {'ok': False, 'packages': [], 'scope': 'Pinned archive hashes and isolated production imports; no game compatibility claim.'}
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix='okdev-cached-packages-') as temporary:
            paths._cached_user_data_dir = Path(temporary)
            paths._migration_checked = True
            from hub import library, sources
            for item in sources.entries():
                result = {'id': item['id'], 'ok': False}
                try:
                    package = arguments.cache / (item['id'] + '.fantome')
                    with package.open('rb') as stream:
                        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                    if digest != item['sha256']:
                        raise ValueError('Cached archive does not match pinned SHA-256')
                    installed = library.import_archive(package, item)
                    if installed['enabled'] or not library.mod_folder(installed).is_relative_to(Path(temporary).resolve()):
                        raise ValueError('Import did not remain disabled and isolated')
                    result.update(ok=True, bytes=package.stat().st_size, sha256=digest)
                except Exception as exc:
                    result['error'] = str(exc)
                report['packages'].append(result)
                print(json.dumps(result, ensure_ascii=True), flush=True)
            report['ok'] = bool(report['packages']) and all(item['ok'] for item in report['packages'])
    finally:
        paths._cached_user_data_dir, paths._migration_checked = previous
        report['elapsed_seconds'] = round(time.monotonic() - started, 2)
        output = ROOT / 'build/cached-package-check.json'
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
