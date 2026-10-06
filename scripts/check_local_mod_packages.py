"""Check downloaded packages with mod-tools import in isolated temporary folders.

No game paths, overlays, injection, mod activation, or windows are involved.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hub import library


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extra-package', type=Path, action='append', default=[])
    args = parser.parse_args()
    packages = list((ROOT / 'downloads/community').glob('*.fantome')) + args.extra_package
    by_hash = {}
    for package in packages:
        with package.open('rb') as stream:
            by_hash[hashlib.file_digest(stream, 'sha256').hexdigest()] = package
    results = []
    for item in library.installed(strict=True).values():
        if not item['id'].startswith('rf-'):
            continue
        path = by_hash.get(item.get('sha256'))
        if path is None:
            results.append({'id': item['id'], 'ok': False, 'error': 'Original package not found'})
            continue
        library.validate_archive(path)
        with tempfile.TemporaryDirectory(prefix='okdev-package-check-', dir=ROOT / 'build') as tmp:
            target = Path(tmp) / 'mod'
            command = [str(ROOT / 'injection/tools/mod-tools.exe'), 'import', str(path.resolve()), str(target)]
            result = subprocess.run(command, capture_output=True, text=True, errors='replace', timeout=90,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                                    | getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0))
            wad_files = list((target / 'WAD').glob('*'))
            results.append({'id': item['id'], 'name': item['name'], 'ok': result.returncode == 0 and bool(wad_files),
                            'returncode': result.returncode, 'compiled_wads': len(wad_files),
                            'package_sha256': item['sha256'],
                            'detail': (result.stderr or result.stdout)[-2000:]})
    report = {'ok': bool(results) and all(item['ok'] for item in results), 'packages': results,
              'scope': 'Archive integrity and isolated mod-tools import only; not an in-game compatibility test.'}
    (ROOT / 'build/local-mod-package-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'ok': report['ok'], 'checked': len(results), 'failed': [item['id'] for item in results if not item['ok']]}))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
