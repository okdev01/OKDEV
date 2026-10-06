"""Seeded model-based stress of library mutations in disposable user data.

The independent model tracks selected groups, every payload version and backup
multiplicity. Every operation checks real files, not only the JSON index. No game
or external network is used. Use --duration for a sustained randomized run.
"""
import argparse
from collections import Counter
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import random
import sys
import tempfile
import time
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=float, default=60)
    parser.add_argument('--interval', type=float, default=.5)
    parser.add_argument('--seed', type=int, default=150006)
    parser.add_argument('--round-size', type=int, default=200)
    parser.add_argument('--report', type=Path, default=ROOT / 'build/library-model-stress.json')
    args = parser.parse_args()
    if args.duration <= 0 or args.interval < 0 or not 1 <= args.round_size <= 1000:
        parser.error('Positive duration, nonnegative interval and round size 1–1000 required')
    from hub import library, profiles, selections, transactions
    from utils.core import paths
    from utils.core.atomic_file import atomic_write
    import psutil
    process = psutil.Process()
    rng = random.Random(args.seed)
    started = time.monotonic()
    report = {'ok': False, 'running': True, 'seed': args.seed, 'operations': 0,
              'rounds': 0, 'counts': {}, 'recent_actions': [], 'samples': [],
              'scope': 'Independent state model and real disposable mod files; no game or network.',
              'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name in ('hub/library.py', 'hub/profiles.py', 'hub/selections.py', 'hub/transactions.py')}}
    previous = paths._cached_user_data_dir, paths._migration_checked

    def checkpoint():
        report['elapsed_seconds'] = round(time.monotonic() - started, 2)
        report['samples'].append({'operations': report['operations'], 'rss_bytes': process.memory_info().rss,
                                 'handles': process.num_handles() if sys.platform == 'win32' else process.num_fds()})
        report['samples'] = report['samples'][-180:]
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with atomic_write(args.report) as stream:
            json.dump(report, stream, indent=2)

    try:
        while time.monotonic() - started < args.duration:
            with tempfile.TemporaryDirectory(prefix='okdev-model-') as temporary, ExitStack() as stack:
                data = Path(temporary)
                paths._cached_user_data_dir, paths._migration_checked = data, True
                stack.enter_context(patch('hub.library.requests.get', side_effect=AssertionError('Network is forbidden')))
                model, payloads, profile_model = {}, {}, {}
                expected_backups = Counter()
                generation = 0
                def group(key):
                    n = int(key.split('-')[-1])
                    return ('skins', (103, 18, 22)[n % 3]) if n < 6 else ('ui', None)

                def choose_set():
                    chosen = set()
                    used = set()
                    for key in rng.sample(sorted(model), len(model)):
                        if rng.choice((False, True)) and group(key) not in used:
                            chosen.add(key)
                            used.add(group(key))
                    return chosen

                def verify():
                    actual = library.installed(strict=True)
                    assert set(actual) == set(model), 'Installed IDs diverged'
                    for key, expected in model.items():
                        item = actual[key]
                        assert item['version'] == expected['version'], 'Version diverged'
                        assert item['enabled'] is expected['enabled'], 'Selection diverged'
                        payload = (library.mod_folder(item) / 'WAD/Fixture.wad.client').read_bytes()
                        assert payload == payloads[key, item['version']], 'Installed payload changed'
                    actual_backups = Counter()
                    for backup in library.removed():
                        key = backup['mod_id'], backup['version']
                        payload = (library.root() / 'removed' / backup['backup_id'] / 'mod/WAD/Fixture.wad.client').read_bytes()
                        assert payload == payloads[key], 'Backup payload changed'
                        actual_backups[key] += 1
                    assert actual_backups == +expected_backups, 'Backup multiplicity diverged'
                    assert {k: set(p['mods']) for k, p in profiles.list_profiles(strict=True).items()} == profile_model, 'Profiles diverged'
                    assert transactions.status()['pending'] == 0, 'Transaction did not settle'
                    selected_groups = [group(key) for key, value in model.items() if value['enabled']]
                    assert len(selected_groups) == len(set(selected_groups)), 'Conflicting selections persisted'

                for step in range(args.round_size):
                    if time.monotonic() - started >= args.duration:
                        break
                    action = rng.choice(('import', 'import', 'selection', 'undo', 'remove', 'restore', 'profile', 'apply_profile', 'stale_preview', 'failed_import'))
                    report['recent_actions'].append({'round': report['rounds'], 'step': step, 'action': action})
                    report['recent_actions'] = report['recent_actions'][-25:]
                    if action == 'import' or not model:
                        key = 'fixture-' + str(rng.randrange(8))
                        generation += 1
                        version = str(generation) + '.0.0'
                        payload = ('Isolated model fixture ' + key + ' / ' + version).encode() * 128
                        payloads[key, version] = payload
                        package = data / 'fixture.fantome'
                        with zipfile.ZipFile(package, 'w') as archive:
                            archive.writestr('WAD/Fixture.wad.client', payload)
                        category, champion = group(key)
                        old = model.get(key)
                        library.import_archive(package, {'id': key, 'name': key, 'category': category,
                            'champion_id': champion, 'champion': 'Fixture' if champion else '',
                            'version': version, 'description': 'Not a playable mod'})
                        if old:
                            expected_backups[key, old['version']] += 1
                        model[key] = {'version': version, 'enabled': old['enabled'] if old else False}
                    elif action in ('selection', 'undo'):
                        before = {k for k, v in model.items() if v['enabled']}
                        chosen = choose_set()
                        selections.apply(sorted(chosen), 'replace')
                        if action == 'undo' and before != chosen:
                            selections.undo()
                            chosen = before
                        for key in model:
                            model[key]['enabled'] = key in chosen
                    elif action == 'remove':
                        key = rng.choice(sorted(model))
                        library.remove(key)
                        expected_backups[key, model.pop(key)['version']] += 1
                    elif action == 'restore':
                        candidates = [b for b in library.removed() if b['mod_id'] not in model]
                        if candidates:
                            backup = rng.choice(candidates)
                            key, version = backup['mod_id'], backup['version']
                            metadata = library.load_json(library.root() / 'removed' / backup['backup_id'] / 'metadata.json')
                            collision = library.mod_folder(metadata['item']).exists()
                            if collision:
                                try:
                                    library.restore(backup['backup_id'])
                                except ValueError:
                                    report['blocked_restores'] = report.get('blocked_restores', 0) + 1
                                else:
                                    raise AssertionError('Restore overwrote an occupied destination')
                            else:
                                library.restore(backup['backup_id'])
                                expected_backups[key, version] -= 1
                                model[key] = {'version': version, 'enabled': False}
                    elif action == 'profile':
                        selected = {k for k, v in model.items() if v['enabled']}
                        if profile_model and rng.choice((False, True)):
                            key = rng.choice(sorted(profile_model))
                            profiles.update(key)
                        else:
                            key = profiles.save('Profile ' + str(step))
                        profile_model[key] = selected
                    elif action == 'apply_profile' and profile_model:
                        key = rng.choice(sorted(profile_model))
                        selected = profile_model[key]
                        if selected <= model.keys():
                            profiles.apply(key)
                            for item in model:
                                model[item]['enabled'] = item in selected
                        else:
                            try:
                                profiles.apply(key)
                            except ValueError:
                                pass
                            else:
                                raise AssertionError('Missing profile references unexpectedly applied')
                    elif action == 'stale_preview':
                        chosen = choose_set()
                        plan = selections.preview(sorted(chosen), 'replace')
                        index = library.root() / 'installed.json'
                        original = index.read_bytes()
                        try:
                            selections.apply(sorted(chosen), 'replace', '0' * 64)
                        except ValueError:
                            pass
                        else:
                            raise AssertionError('Stale selection accepted')
                        assert index.read_bytes() == original, 'Stale selection wrote the index'
                        assert plan['revision'] != '0' * 64
                    elif action == 'failed_import':
                        package = data / 'broken.fantome'
                        package.write_bytes(b'not an archive')
                        key = rng.choice(sorted(model))
                        item = library.installed()[key]
                        try:
                            library.import_archive(package, item)
                        except (ValueError, zipfile.BadZipFile):
                            pass
                        else:
                            raise AssertionError('Broken package accepted')
                    verify()
                    report['operations'] += 1
                    report['counts'][action] = report['counts'].get(action, 0) + 1
                    if report['operations'] % 10 == 0:
                        checkpoint()
                    time.sleep(min(args.interval, max(0, args.duration - (time.monotonic() - started))))
                report['rounds'] += 1
        report['ok'] = True
    except Exception as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
        import traceback
        report['traceback'] = traceback.format_exc()
    finally:
        paths._cached_user_data_dir, paths._migration_checked = previous
        report['running'] = False
        checkpoint()
    print(json.dumps({k: report[k] for k in ('ok', 'operations', 'rounds', 'elapsed_seconds')}))
    if report.get('error'):
        print(report['error'])
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
