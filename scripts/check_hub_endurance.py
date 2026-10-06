"""Paced endurance run using loopback HTTP and entirely disposable user data.

Exercises the production queue, streaming/hash validation, failed download retry,
selection undo, profile writes and folder recovery. No public service or game is
contacted. A heartbeat records resource usage and the exact tested source hashes.
"""
import argparse
import hashlib
import io
import json
import sys
import tempfile
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=float, default=3600)
    parser.add_argument('--interval', type=float, default=15)
    parser.add_argument('--report', type=Path, default=ROOT / 'build/hub-endurance.json')
    args = parser.parse_args()
    if args.duration <= 0 or args.interval < 0:
        parser.error('Duration must be positive and interval nonnegative')
    import psutil
    import requests
    from utils.core import paths
    from hub import library, downloads, profiles, selections, activity
    previous, previous_migration = paths._cached_user_data_dir, paths._migration_checked
    started = time.monotonic()
    report = {'ok': False, 'running': True, 'cycles': 0, 'failed_downloads_retried': 0,
              'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                               for name in ('hub/library.py', 'hub/downloads.py', 'hub/transactions.py',
                                            'hub/selections.py', 'hub/profiles.py')}, 'samples': []}
    report['scope'] = 'Loopback HTTP fixture and temporary data only; no game or public CDN traffic.'
    process = psutil.Process()
    def checkpoint():
        report['elapsed_seconds'] = round(time.monotonic() - started, 2)
        sample = {'cycle': report['cycles'], 'rss_bytes': process.memory_info().rss,
                  'threads': process.num_threads(), 'handles': process.num_handles() if sys.platform == 'win32' else process.num_fds()}
        report['samples'].append(sample)
        report['samples'] = report['samples'][-300:]
        args.report.parent.mkdir(parents=True, exist_ok=True)
        from utils.core.atomic_file import atomic_write
        with atomic_write(args.report) as stream:
            json.dump(report, stream, indent=2)

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, 'w') as archive:
        archive.writestr('WAD/Ahri.wad.client', b'Endurance fixture only. ' * 48000)
    content = payload.getvalue()
    server_state = {'broken': False}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            body = b'corrupt fixture' if server_state['broken'] else content
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            try:
                for offset in range(0, len(body), 65536):
                    self.wfile.write(body[offset:offset + 65536])
                    self.wfile.flush()
                    time.sleep(.003)
            except (ConnectionError, OSError):
                pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    real_get = requests.get
    queue = None
    try:
        with tempfile.TemporaryDirectory(prefix='okdev-endurance-') as temporary:
            paths._cached_user_data_dir, paths._migration_checked = Path(temporary), True
            item = dict(id='soak-fixture', name='Endurance fixture', champion='Ahri', champion_id=103,
                        category='skins', description='Disposable test data', version='1.0.0',
                        sha256=hashlib.sha256(content).hexdigest(),
                        download_url='https://fixture.invalid/archive.fantome')
            def get_fixture(url, **kwargs):
                assert url == item['download_url'], 'Unexpected external request'
                return real_get(f'http://127.0.0.1:{server.server_port}/fixture', **kwargs)
            def finish_job(job_id):
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    job = next(j for j in queue.snapshot()['jobs'] if j['id'] == job_id)
                    if job['status'] not in downloads.ACTIVE:
                        return job
                    library.set_auto_accept(False)
                    time.sleep(.025)
                raise AssertionError('Queue failed to settle within 20 seconds')
            with patch('hub.sources.entries', return_value=[item]), patch('hub.library.requests.get', side_effect=get_fixture):
                queue = downloads.DownloadQueue()
                while time.monotonic() - started < args.duration:
                    cycle = report['cycles']
                    server_state['broken'] = cycle % 5 == 0
                    job = finish_job(queue.enqueue(item['id'])['id'])
                    if server_state['broken']:
                        assert job['status'] == 'failed', job
                        server_state['broken'] = False
                        job = finish_job(queue.retry(job['id'])['id'])
                        report['failed_downloads_retried'] += 1
                    assert job['status'] == 'completed', job
                    assert len(library.installed(strict=True)) == 1
                    selections.apply([item['id']], 'enable')
                    assert library.installed()[item['id']]['enabled']
                    profile = profiles.save('Endurance ' + str(cycle))
                    selections.undo()
                    assert not library.installed()[item['id']]['enabled']
                    profiles.apply(profile)
                    profiles.remove(profile)
                    library.remove(item['id'])
                    backup = next(b for b in library.removed() if b['reason'] == 'removed')
                    library.restore(backup['backup_id'])
                    assert not library.installed()[item['id']]['enabled']
                    assert not list(library.root().glob('download-*'))
                    assert not list((library.root() / 'pending').glob('*.json'))
                    assert len(activity.read()['events']) <= 200
                    assert len(queue.snapshot()['jobs']) <= downloads.MAX_JOBS
                    report['cycles'] += 1
                    checkpoint()
                    time.sleep(min(args.interval, max(0, args.duration - (time.monotonic() - started))))
                queue.close()
                assert queue.wait_closed(10), 'Queue thread did not close'
                queue = None
                samples = report['samples']
                if len(samples) >= 20:
                    baseline = samples[5]
                    assert samples[-1]['rss_bytes'] - baseline['rss_bytes'] < 128 * 1024 * 1024, 'Sustained memory growth exceeded 128 MiB'
                    assert samples[-1]['handles'] - baseline['handles'] < 200, 'Handle count grew by 200 or more'
                    assert samples[-1]['threads'] <= baseline['threads'] + 3, 'Worker threads accumulated'
                report['ok'] = True
    except Exception as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        if queue is not None:
            queue.close()
            queue.wait_closed(10)
        paths._cached_user_data_dir, paths._migration_checked = previous, previous_migration
        server.shutdown()
        server.server_close()
        report['running'] = False
        checkpoint()
    print(json.dumps({key: report[key] for key in ('ok', 'cycles', 'elapsed_seconds', 'failed_downloads_retried')}))
    if report.get('error'):
        print(report['error'])
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
