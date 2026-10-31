"""Read-only format audit for a local Fantome library."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import zipfile
from .package import inspect_package
from .wad import read_index
from .payload import read_payload


def inspect_one(path, verify_payloads=False):
    try:
        info = inspect_package(path)
        stats = Counter()
        with zipfile.ZipFile(path) as archive:
            for name in info['wad_entries']:
                if len(name.split('/')) != 2 or not name.lower().endswith('.wad.client'):
                    return {'path': str(path), 'supported': False, 'reason': 'loose_payload_layout'}
                # Bounded audit: avoid allocating untrusted large WAD payloads.
                if archive.getinfo(name).file_size > 16 * 1024**2:
                    return {'path': str(path), 'supported': False, 'reason': 'audit_size_limit'}
                stream = io.BytesIO(archive.read(name))
                entries = read_index(stream)
                for entry in entries:
                    stats[str(entry.compression)] += 1
                    if verify_payloads and entry.compression in (0,1,3):
                        read_payload(stream, entry)
        return {'path': str(path), 'supported': '4' not in stats,
                'reason': 'replacement_subchunks' if '4' in stats else 'ok',
                'entries_by_compression': dict(stats)}
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        return {'path': str(path), 'supported': False,
                'reason': type(error).__name__, 'detail': str(error)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('library', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--verify-payloads', action='store_true')
    args = parser.parse_args()
    packages = sorted(args.library.rglob('*.fantome'))
    results = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        from functools import partial
        for result in executor.map(partial(inspect_one, verify_payloads=args.verify_payloads), packages):
            results.append(result)
            if len(results) % 500 == 0:
                print(f'Audited {len(results)}/{len(packages)}', flush=True)
    report = {'packages': len(results),
              'supported_offline': sum(r['supported'] for r in results),
              'reasons': dict(Counter(r['reason'] for r in results)),
              'runtime_available': False, 'results': results}
    report['payload_verification_requested'] = args.verify_payloads
    with args.report.open('x', encoding='utf-8') as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != 'results'}))


if __name__ == '__main__':
    main()
