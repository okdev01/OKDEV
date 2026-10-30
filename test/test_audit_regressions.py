"""Regression coverage for the 2026-10-30 audit, using isolated app data."""
import ast
import json
import os
import shutil
import subprocess
import sys
import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from hub import library, transactions
from hub.tests.test_library import LibraryFixture
from injection.mods.storage import ModStorageService

ROOT = Path(__file__).resolve().parents[1]


class AuditRegressions(LibraryFixture):
    def test_restore_repairs_manifest_interrupted_by_power_loss(self):
        class PowerLoss(BaseException):
            pass
        service = ModStorageService()
        with patch.object(ModStorageService, 'set_champion_target_ids', side_effect=PowerLoss):
            with self.assertRaises(PowerLoss):
                library.import_client_archive(service, self.archive(), champion_id=103, targets=[103001])
        with library.mutation_lock():
            pass
        library.restore(library.removed()[0]['backup_id'])
        entries = service.list_mods_for_champion(103)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].target_skin_ids, (103001,))

    def test_legacy_client_delete_restore_keeps_paid_skin_target(self):
        service = ModStorageService()
        folder, _, name = service.import_mod_file(103, self.archive(), [103001])
        self.assertTrue(library.remove_client_mod(service, champion_id=103, mod_name=name))
        restored = library.restore(library.removed()[0]['backup_id'])
        self.assertEqual(restored['target_skin_ids'], [103001])
        library.enable(restored['id'], True)
        self.assertEqual(library.active_mod(103)['skin_id'], 103001)

    def test_legacy_client_mods_are_adopted_once_without_losing_history(self):
        from hub.client_sync import reconcile
        from utils.core.historic import write_historic_entry
        service = ModStorageService()
        folder, _, _ = service.import_mod_file(103, self.archive(), [103001])
        relative = folder.relative_to(service.mods_root).as_posix()
        write_historic_entry(103, 'path:' + relative)
        self.assertEqual(reconcile(service), 1)
        self.assertEqual(reconcile(service), 0)
        self.assertEqual(library.active_mod(103)['skin_id'], 103001)
        self.assertEqual(len(service.list_mods_for_champion(103)), 1)

    def test_client_category_choices_and_hub_profile_agree(self):
        from hub.client_sync import select
        from hub.integration import apply_category_selections
        from hub import profiles
        service = ModStorageService()
        first = library.import_client_archive(service, self.archive(), category='vfx')
        second = library.import_client_archive(service, self.archive('second.zip'), category='vfx')
        select('vfx', [first['relative_path'], second['relative_path']])
        profile = profiles.save('Both effects')
        state = SimpleNamespace()
        apply_category_selections(state)
        self.assertEqual(len(state.selected_other_mods), 2)
        select('vfx', [])
        apply_category_selections(state)
        self.assertEqual(state.selected_other_mods, [])
        profiles.apply(profile)
        apply_category_selections(state)
        self.assertEqual(len(state.selected_other_mods), 2)

    def test_import_crash_before_cover_or_index_can_be_recovered(self):
        original = ModStorageService.import_mod_file
        class PowerLoss(BaseException):
            pass
        def crash(service, *args, **kwargs):
            original(service, *args, **kwargs)
            raise PowerLoss()
        with patch.object(ModStorageService, 'import_mod_file', crash), self.assertRaises(PowerLoss):
            library.import_archive(self.archive(), self.item())
        self.assertEqual(transactions.status()['pending'], 1)
        with library.mutation_lock():
            pass
        self.assertEqual(library.installed(), {})
        self.assertEqual(len(library.removed()), 1)

    def test_cache_revision_does_not_modify_an_existing_extraction(self):
        from utils.core.junction import _get_or_extract_to_cache
        archive = self.archive()
        first = _get_or_extract_to_cache(archive, 'sample', self.root / 'cache')
        old = (first / 'WAD/Ahri.wad.client').read_bytes()
        self.archive(files={'WAD/Ahri.wad.client': b'replacement content'})
        second = _get_or_extract_to_cache(archive, 'sample', self.root / 'cache')
        self.assertNotEqual(first, second)
        self.assertEqual((first / 'WAD/Ahri.wad.client').read_bytes(), old)
        self.assertEqual((second / 'WAD/Ahri.wad.client').read_bytes(), b'replacement content')

    def test_corrupt_history_cannot_be_overwritten_if_backup_fails(self):
        from utils.core.historic import write_historic_entry
        path = self.root / 'historic.json'
        path.write_bytes(b'{broken')
        with patch('utils.core.history_store.atomic_write', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                write_historic_entry(99, 99001)
        self.assertEqual(path.read_bytes(), b'{broken')

    def test_A01_client_delete_is_visible_and_recoverable_in_hub(self):
        item = library.import_archive(self.archive(), self.item())
        library.enable(item['id'], True)
        self.assertTrue(library.remove_client_mod(ModStorageService(), champion_id=103,
                                                  mod_name=item['folder_name'], relative_path=item['relative_path']))
        self.assertEqual(library.installed(), {})
        self.assertFalse(library.mod_folder(item).exists())
        backup = library.removed()[0]
        restored = library.restore(backup['backup_id'])
        self.assertEqual((library.mod_folder(restored) / 'WAD/Ahri.wad.client').read_bytes(), b'fixture-wad-data')

    def test_A02_client_import_preserves_targets_and_hub_selection(self):
        from hub.client_sync import select
        service = ModStorageService()
        item = library.import_client_archive(service, self.archive(), champion_id=103, targets=[103001, 103002])
        self.assertEqual(len(service.list_mods_for_champion(103)), 1)
        self.assertIn(item['id'], library.installed())
        select('skins', [item['relative_path']], champion_id=103, skin_id=103002)
        self.assertEqual(library.active_mod(103)['skin_id'], 103002)
        select('skins', [], champion_id=103)
        self.assertIsNone(library.active_mod(103))

    def test_A03_custom_target_ownership_is_independent_of_hover(self):
        from state import SharedState
        from threads.handlers.injection_trigger import InjectionTrigger
        state = SharedState()
        state.locked_champ_id = 103
        state.last_hovered_skin_id = state.selected_skin_id = 103001
        state.owned_skin_ids = {103000, 103001}
        trigger = InjectionTrigger(Mock(), state, Mock())
        trigger._inject_custom_mod = Mock()
        trigger._force_owned_skin = Mock()
        custom = dict(_hub=True, champion_id=103, skin_id=103000, mod_name='Sample',
                      mod_folder_name='Sample', relative_path='skins/103000/Sample')
        with patch('hub.library.active_mod', return_value=custom), patch('utils.core.mod_historic.get_historic_mod', return_value=None):
            trigger.trigger_injection('skin_103001', 1, 'Ahri')
        trigger._force_owned_skin.assert_called_once_with(103000)
        trigger._inject_custom_mod.assert_called_once()

    def test_A04_journal_failure_precedes_any_mod_extraction(self):
        with patch.object(transactions, 'begin', side_effect=OSError('journal unavailable')):
            with self.assertRaises(OSError):
                library.import_archive(self.archive(), self.item())
        self.assertEqual(list((self.root / 'mods').rglob('*.wad.client')), [])
        self.assertEqual(library.installed(), {})
        self.assertEqual(transactions.recover_pending(), 0)

    def test_A05_put_retry_uses_refreshed_connection(self):
        from lcu.core.lcu_api import LCUAPI
        old, new = Mock(), Mock()
        old.put.side_effect = requests.ConnectionError('client restarted')
        new.put.return_value = SimpleNamespace(status_code=204)
        conn = SimpleNamespace(ok=True, base='https://127.0.0.1:10001', session=old)
        def refresh(force=False):
            conn.base, conn.session = 'https://127.0.0.1:10002', new
        conn.refresh_if_needed = refresh
        self.assertEqual(LCUAPI(conn).put('/fixture', {}, 1).status_code, 204)
        self.assertEqual(new.put.call_args.args[0], 'https://127.0.0.1:10002/fixture')

    def test_A06_folder_hash_tracks_nested_changes(self):
        from party.discovery.custom_mods import mod_hashes, _folder_content_hash
        folder = self.root / 'mod/WAD'
        folder.mkdir(parents=True)
        file = folder / 'data.bin'
        file.write_bytes(b'AAAA')
        first = mod_hashes(folder.parent)[0]
        file.write_bytes(b'BBBB')
        # Force a distinct file timestamp even on filesystems with coarse clocks.
        os.utime(file, ns=(file.stat().st_atime_ns, file.stat().st_mtime_ns + 1000000000))
        second = mod_hashes(folder.parent)[0]
        self.assertNotEqual(first, second)
        self.assertEqual(second, _folder_content_hash(folder.parent))

    def downloader(self):
        from utils.download.repo_downloader import RepoDownloader
        folder = self.root / 'skins'
        folder.mkdir()
        return RepoDownloader(folder)

    def test_A07_failed_rename_download_keeps_working_file(self):
        downloader = self.downloader()
        old = downloader.target_dir / 'old.fantome'
        old.write_bytes(b'working')
        downloader.session.get = Mock(side_effect=requests.ConnectionError('offline'))
        self.assertFalse(downloader.download_changed_files([dict(filename='skins/new.fantome',
                          status='renamed', previous_filename='skins/old.fantome')]))
        self.assertEqual(old.read_bytes(), b'working')
        self.assertFalse((downloader.target_dir / 'new.fantome').exists())

    def test_A07_successful_rename_commits_new_before_removing_old(self):
        downloader = self.downloader()
        old = downloader.target_dir / 'old.fantome'
        old.write_bytes(b'working')
        response = Mock()
        def content(**kwargs):
            self.assertTrue(old.exists())
            yield b'replacement'
        response.iter_content.side_effect = content
        downloader.session.get = Mock(return_value=response)
        self.assertTrue(downloader.download_changed_files([dict(filename='skins/new.fantome',
                         status='renamed', previous_filename='skins/old.fantome')]))
        self.assertFalse(old.exists())
        self.assertEqual((downloader.target_dir / 'new.fantome').read_bytes(), b'replacement')

    def test_A08_failed_delete_does_not_report_success(self):
        downloader = self.downloader()
        old = downloader.target_dir / 'old.fantome'
        old.write_bytes(b'working')
        with patch.object(Path, 'unlink', side_effect=PermissionError('locked')):
            self.assertFalse(downloader.download_changed_files([dict(filename='skins/old.fantome', status='removed')]))
        self.assertTrue(old.exists())

    def test_A09_startup_wait_obeys_stop_and_is_inside_cleanup(self):
        tree = ast.parse((ROOT / 'main/__init__.py').read_text(encoding='utf-8-sig'))
        startup = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run_league_unlock')
        loop = next(n for n in ast.walk(startup) if isinstance(n, ast.While))
        guarded = next(n for n in ast.walk(startup) if isinstance(n, ast.Try) and loop in n.body)
        self.assertIn('perform_cleanup', ast.unparse(guarded.finalbody[0]))
        wrapper = ast.parse('def wait():\n    pass').body[0]
        wrapper.body = [loop]
        sleep = Mock(side_effect=AssertionError('stop should return immediately'))
        scope = dict(state=SimpleNamespace(stop=True), t_ws=SimpleNamespace(connection=SimpleNamespace(is_connected=False)), time=SimpleNamespace(sleep=sleep))
        exec(compile(ast.fix_missing_locations(ast.Module(body=[wrapper], type_ignores=[])), '<startup>', 'exec'), scope)
        scope['wait']()
        sleep.assert_not_called()

    def test_A10_smart_downloader_stream_timeout_reaches_http(self):
        from utils.download.smart_skin_downloader import SmartSkinDownloader
        downloader = SmartSkinDownloader(self.root)
        response = Mock(status_code=200)
        response.headers = {}
        response.iter_content.return_value = [b'archive']
        downloader.session.get = Mock(return_value=response)
        result = downloader.download_file_batch(['https://fixture.invalid/a'], [self.root / 'a.zip'])
        self.assertEqual(result, [True])
        downloader.session.get.assert_called_once()

    def test_A11_unverifiable_empty_library_is_not_ready(self):
        downloader = self.downloader()
        downloader.fetch_remote_sha = Mock(return_value=None)
        self.assertFalse(downloader.download_incremental_updates(force_update=True))

    def test_A12_recovery_restores_phase_without_reentering_champ_select(self):
        from state import SharedState
        from threads.core.phase_thread import PhaseThread
        for gap in (1, 3):
            with self.subTest(gap=gap):
                state = SharedState()
                state.phase = 'ChampSelect'
                values = iter([None] * gap + ['ChampSelect'])
                class FakeLCU:
                    ok = True
                    def refresh_if_needed(self):
                        pass
                    @property
                    def phase(self):
                        value = next(values)
                        if value == 'ChampSelect':
                            state.stop = True
                        return value
                worker = PhaseThread(FakeLCU(), state)
                worker.last_phase = worker._last_raw_phase = 'ChampSelect'
                worker.phase_handler = worker.lobby_processor = worker.swiftplay_handler = Mock()
                with patch('threads.core.phase_thread.time.sleep'):
                    worker.run()
                self.assertEqual(state.phase, 'ChampSelect')
                worker.phase_handler.handle_phase_change.assert_not_called()

    def test_A13_hotkey_restores_last_manual_guide(self):
        from hub.companion import WindowState, hotkey_command
        machine = WindowState()
        machine.apply(dict(id='manual', created_at=100, action='show', pick={'champion': {'id': 103}, 'role': 'mid'}), now=100)
        before = machine.url
        current = {'pick': None, 'phase': 'Lobby'}
        for now in (101, 102):
            machine.apply(hotkey_command(machine.visible, current, now=now, last_pick=machine.last_pick), now=now)
        self.assertEqual(machine.url, before)
        self.assertTrue(machine.visible)

    def test_A14_same_named_category_mods_both_reach_overlay(self):
        from state import SharedState
        from threads.handlers.injection_trigger import InjectionTrigger
        state = SharedState()
        state.locked_champ_id = 103
        for category, attr in [('map', 'selected_map_mod'), ('font', 'selected_font_mod')]:
            source = self.root / category / 'Sample'
            (source / 'WAD').mkdir(parents=True)
            (source / 'WAD' / (category + '.bin')).write_bytes(category.encode())
            setattr(state, attr, dict(mod_name=category, mod_folder_name='Sample', mod_path=str(source)))
        injector = Mock()
        injector.mods_dir = self.root / 'stage'
        injector.mods_dir.mkdir()
        injector.overlay_manager.mk_run_overlay.return_value = 0
        manager = Mock(injector=injector)
        manager._monitor_active = True
        trigger = InjectionTrigger(Mock(), state, manager)
        def copy(source, dest, cache_dir):
            shutil.copytree(source, dest)
        with patch('threads.handlers.injection_trigger.get_injection_dir', return_value=self.root), patch('threads.handlers.injection_trigger.link_or_extract', side_effect=copy):
            trigger._inject_custom_mod(dict(champion_id=103, skin_id=103000))
        staged = injector.overlay_manager.mk_run_overlay.call_args.args[0]
        self.assertEqual(len(set(staged)), 2)
        self.assertTrue((injector.mods_dir / staged[0] / 'WAD/map.bin').exists())
        self.assertTrue((injector.mods_dir / staged[1] / 'WAD/font.bin').exists())

    def test_A15_equal_archive_names_and_dates_have_distinct_cache(self):
        from utils.core.junction import _get_or_extract_to_cache
        cached = []
        for category in ['a', 'b']:
            directory = self.root / category
            directory.mkdir()
            target = directory / 'sample.fantome'
            with zipfile.ZipFile(target, 'w') as z:
                z.writestr('WAD/data.bin', category.encode())
            os.utime(target, (1700000000, 1700000000))
            cached.append(_get_or_extract_to_cache(target, 'sample', self.root / 'cache'))
        self.assertNotEqual(*cached)
        self.assertEqual([(p / 'WAD/data.bin').read_bytes() for p in cached], [b'a', b'b'])

    def test_A16_locked_delete_preserves_registration(self):
        service = ModStorageService()
        folder, _, name = service.import_mod_file(103, self.archive(), [103000])
        with patch('utils.core.junction.shutil.rmtree'):
            with self.assertRaises(OSError):
                service.delete_champion_mod(103, name, folder.relative_to(service.mods_root).as_posix())
        self.assertTrue(folder.exists())
        self.assertEqual(len(service.list_mods_for_champion(103)), 1)

    def test_A17_corrupt_history_is_backed_up_before_replacement(self):
        from utils.core.historic import write_historic_entry
        from utils.core.mod_historic import write_historic_mod
        original = b'{"103": 103001, "broken":'
        for name in ('historic.json', 'mod_historic.json'):
            (self.root / name).write_bytes(original)
        write_historic_entry(99, 99001)
        write_historic_mod('map', 'maps/new')
        backups = list(self.root.glob('*.corrupt-*.json'))
        self.assertEqual(len(backups), 2)
        self.assertTrue(all(p.read_bytes() == original for p in backups))
        self.assertEqual(json.loads((self.root / 'historic.json').read_text()), {'99': 99001})

    def test_A20_history_writers_in_separate_processes_keep_all_updates(self):
        code = '''
import sys
from pathlib import Path
from utils.core import paths
paths._cached_user_data_dir = Path(sys.argv[1])
paths._migration_checked = True
from utils.core.historic import write_historic_entry
for value in range(int(sys.argv[2]), int(sys.argv[2])+15):
    write_historic_entry(value, value*1000)
'''
        processes = [subprocess.Popen([sys.executable, '-B', '-c', code, str(self.root), str(base)],
                     cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)) for base in (100, 200)]
        for process in processes:
            out, err = process.communicate(timeout=20)
            self.assertEqual(process.returncode, 0, err.decode(errors='replace'))
        data = json.loads((self.root / 'historic.json').read_text())
        self.assertEqual(set(data), {str(n) for base in (100, 200) for n in range(base, base + 15)})

    def test_S21_entrypoint_uses_the_guarded_runner(self):
        tree = ast.parse((ROOT / 'main.py').read_text(encoding='utf-8-sig'))
        self.assertTrue(any(isinstance(node, ast.ImportFrom) and node.module == 'main' and
                            any(alias.name == 'guarded_main' for alias in node.names) for node in tree.body))
        tree = ast.parse((ROOT / 'main/__init__.py').read_text(encoding='utf-8-sig'))
        guard = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'guarded_main')
        reporter = Mock()
        scope = {'main': Mock(side_effect=RuntimeError('fixture startup failure')),
                 'get_logger': Mock(), 'sys': SimpleNamespace(platform='test', stderr=sys.stderr,
                                                             exit=Mock(side_effect=SystemExit(1)))}
        with patch.dict(sys.modules, {'utils.core.issue_reporter': SimpleNamespace(report_issue=reporter)}):
            exec(compile(ast.Module(body=[guard], type_ignores=[]), '<guard>', 'exec'), scope)
            with self.assertRaises(SystemExit):
                scope['guarded_main']()
        self.assertEqual(reporter.call_args.args[0], 'FATAL_CRASH')
