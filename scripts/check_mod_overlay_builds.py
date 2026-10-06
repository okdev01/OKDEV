"""Build temporary overlays against installed game data, without running a patcher.

Game files are read by mod-tools. All mod extraction and overlay output remains
in a temporary directory; no game, injector, client or LTK host is launched.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hub import library, sources
from utils.core.safe_extract import extract_mod_archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir', required=True, type=Path)
    parser.add_argument('--id', action='append')
    parser.add_argument('--cache', type=Path, default=ROOT / 'downloads/community')
    parser.add_argument('--report', type=Path, default=ROOT / 'build/mod-overlay-build-check.json')
    args = parser.parse_args()
    game = args.game_dir.resolve()
    if not (game / 'League of Legends.exe').is_file():
        raise ValueError('Game directory not found')
    if shutil.disk_usage(ROOT).free < 10 * 1024**3:
        raise ValueError('At least 10 GB of free temporary workspace is required')
    original = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in game.rglob('*.wad.client')}
    results = []
    for item in sources.entries():
        if args.id and item['id'] not in args.id:
            continue
        started = time.monotonic()
        try:
            import psutil
            if any((p.info['name'] or '').lower() == 'league of legends.exe' for p in psutil.process_iter(['name'])):
                raise RuntimeError('Game is running; stop the offline overlay test')
            package = args.cache / (item['id'] + '.fantome')
            with package.open('rb') as stream:
                assert hashlib.file_digest(stream, 'sha256').hexdigest() == item['sha256'], 'Package hash mismatch'
            library.validate_archive(package)
            with tempfile.TemporaryDirectory(prefix='okdev-overlay-qa-', dir=ROOT / 'build') as tmp:
                folder = Path(tmp).resolve()
                mods, overlay = folder / 'mods', folder / 'overlay'
                extract_mod_archive(package, mods / 'fixture')
                command = [str(ROOT / 'injection/tools/mod-tools.exe'), 'mkoverlay', str(mods), str(overlay),
                    '--game:' + str(game), '--mods:fixture', '--noTFT', '--ignoreConflict']
                result = subprocess.run(command, capture_output=True, text=True, errors='replace', timeout=120,
                    creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
                wads = list(overlay.rglob('*.wad.client'))
                results.append({'id': item['id'], 'ok': result.returncode == 0 and bool(wads),
                    'compiled_wads': len(wads), 'output_bytes': sum(p.stat().st_size for p in wads),
                    'seconds': round(time.monotonic() - started, 2),
                    'detail': (result.stderr + result.stdout)[-2400:] if result.returncode else ''})
        except Exception as exc:
            results.append({'id': item['id'], 'ok': False, 'error': f'{type(exc).__name__}: {exc}'})
        print(json.dumps(results[-1], ensure_ascii=False), flush=True)
    unchanged = all(p.is_file() and (p.stat().st_size, p.stat().st_mtime_ns) == stamp for name, stamp in original.items() for p in [Path(name)])
    report = {'ok': bool(results) and unchanged and all(r['ok'] for r in results), 'game_files_unchanged': unchanged,
        'game_wads_checked': len(original), 'results': results,
        'scope': 'Offline mod-tools mkoverlay only; no patcher or game process. This is not a live match or visual compatibility test.'}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
