"""Large loopback downloads, limits and cancellation with disposable user data.

No public network, game process or installed user data is used. This deliberately
creates about 1.5 GiB of temporary files with the default 511 MiB fixture.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--megabytes', type=int, default=511)
    parser.add_argument('--report', type=Path, default=ROOT / 'build/large-download-check.json')
    args = parser.parse_args()
    if not 16 <= args.megabytes <= 511:
        parser.error('Fixture must be between 16 and 511 MiB')
    import psutil
    import requests
    from utils.core import paths
    from hub import library
    previous = paths._cached_user_data_dir, paths._migration_checked
    report = {'ok': False, 'checks': [], 'cases': [], 'scope': 'Loopback HTTP and temporary files only',
              'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                               for name in ('hub/library.py', 'injection/mods/storage.py', 'utils/core/safe_extract.py')}}
    block = bytes(range(256)) * 4096
    server = None
    try:
        with tempfile.TemporaryDirectory(prefix='okdev-large-download-') as temporary:
            base = Path(temporary)
            paths._cached_user_data_dir, paths._migration_checked = base / 'data', True
            archive = base / 'large.fantome'
            payload_digest = hashlib.sha256()
            with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_STORED) as package:
                with package.open('WAD/Ahri.wad.client', 'w') as output:
                    for _ in range(args.megabytes):
                        output.write(block)
                        payload_digest.update(block)
            with archive.open('rb') as source:
                digest = hashlib.file_digest(source, 'sha256').hexdigest()
            report['archive_bytes'] = archive.stat().st_size
            state = {'mode': 'valid'}

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass

                def do_GET(self):
                    self.send_response(200)
                    mode = state['mode']
                    if mode != 'stream-limit':
                        self.send_header('Content-Length', str(library.MAX_DOWNLOAD + 1 if mode == 'header-limit' else archive.stat().st_size))
                    self.end_headers()
                    try:
                        if mode == 'stream-limit':
                            for _ in range(library.MAX_DOWNLOAD // len(block) + 1):
                                self.wfile.write(block)
                        elif mode != 'header-limit':
                            with archive.open('rb') as source:
                                while chunk := source.read(65536):
                                    self.wfile.write(chunk)
                    except (ConnectionError, OSError):
                        pass

            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            real_get = requests.get
            item = dict(id='large-fixture', name='Large fixture', champion='Ahri', champion_id=103,
                        category='skins', description='Disposable test data', version='1.0.0',
                        sha256=digest, download_url='https://fixture.invalid/large.fantome')

            def local_get(url, **kwargs):
                assert url == item['download_url'], 'Unexpected external request'
                return real_get(f'http://127.0.0.1:{server.server_port}/fixture', **kwargs)

            process = psutil.Process()
            baseline = process.memory_info().rss
            peak = [baseline]
            stop = threading.Event()

            def sample():
                while not stop.wait(.05):
                    peak[0] = max(peak[0], process.memory_info().rss)

            sampler = threading.Thread(target=sample, daemon=True)
            sampler.start()
            try:
                with patch('hub.sources.entries', return_value=[item]), patch('hub.library.requests.get', side_effect=local_get):
                    for mode in ('valid', 'cancel', 'hash-mismatch', 'header-limit', 'stream-limit'):
                        state['mode'] = mode
                        item['sha256'] = '0' * 64 if mode == 'hash-mismatch' else digest
                        progress_bytes = [0]
                        started = time.monotonic()
                        before = library.installed(strict=True)
                        try:
                            installed = library.download_source(item['id'],
                                lambda value: progress_bytes.__setitem__(0, value['received']),
                                lambda: mode == 'cancel' and progress_bytes[0] >= 8 * 1024**2)
                        except ValueError as exc:
                            assert mode != 'valid', str(exc)
                            expected = 'iptal' if mode == 'cancel' else 'doğrulanamadı' if mode == 'hash-mismatch' else 'sınırını'
                            assert expected in str(exc), str(exc)
                            assert library.installed(strict=True) == before, 'Rejected download changed installed record'
                        else:
                            assert mode == 'valid', 'Invalid download was installed'
                            payload = library.mod_folder(installed) / 'WAD/Ahri.wad.client'
                            with payload.open('rb') as source:
                                assert hashlib.file_digest(source, 'sha256').hexdigest() == payload_digest.hexdigest()
                        assert not list(library.root().glob('download-*')), 'Temporary download workspace leaked'
                        assert not library.removed(), 'Rejected download created an unexpected replacement backup'
                        report['cases'].append({'mode': mode, 'received': progress_bytes[0],
                                                'seconds': round(time.monotonic() - started, 3)})
                        report['checks'].append(mode + ': validated and temporary workspace cleaned')
            finally:
                stop.set()
                sampler.join(2)
            report.update(baseline_rss_bytes=baseline, peak_rss_bytes=peak[0], growth_rss_bytes=peak[0] - baseline)
            assert peak[0] - baseline < 128 * 1024**2, 'Streaming download retained excessive memory'
            report['checks'].append('Peak additional RSS below 128 MiB for streamed fixture')
            payload = library.mod_folder(library.installed()[item['id']]) / 'WAD/Ahri.wad.client'
            with payload.open('rb') as source:
                assert hashlib.file_digest(source, 'sha256').hexdigest() == payload_digest.hexdigest()
            report['checks'].append('Original installed payload unchanged after all rejected attempts')
            report['ok'] = True
    except Exception as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        if server:
            server.shutdown()
            server.server_close()
        paths._cached_user_data_dir, paths._migration_checked = previous
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
