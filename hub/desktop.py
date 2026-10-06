import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import webbrowser
from . import library

MOBALYTICS = 'https://mobalytics.gg/lol?int_source=homepage&int_medium=header'
_process = None


def build_html(base=None):
    base = base or Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    web = base / 'hub/web'
    html = (web / 'index.html').read_text(encoding='utf-8')
    from .sources import entries
    from config import APP_VERSION
    bootstrap = {'version': APP_VERSION, 'sources': entries(), 'champions': json.loads((web / 'champions.json').read_text(encoding='utf-8'))['champions']}
    encoded = json.dumps(bootstrap, ensure_ascii=False).replace('<', '\\u003c')
    return html.replace('/*BOOTSTRAP*/', 'window.HUB_DATA=' + encoded + ';').replace(
        '/*APP_JS*/', (web / 'app.js').read_text(encoding='utf-8')).replace(
        '/*APP_CSS*/', (web / 'app.css').read_text(encoding='utf-8'))


def open_hub():
    global _process
    if _process is not None and _process.poll() is None:
        # Focus the already-open window rather than starting another writer.
        import ctypes
        hwnd = ctypes.windll.user32.FindWindowW(None, 'OKDEV • Mod Merkezi')
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 9)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        return
    cmd = [sys.executable, '--hub'] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).resolve().parents[1] / 'main.py'), '--hub']
    _process = subprocess.Popen(cmd, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def close_hub():
    if _process is not None and _process.poll() is None:
        from .lifecycle import request_shutdown
        try:
            request_shutdown(_process.pid)
        except (OSError, ValueError):
            pass  # A normal close still asks the user when disk handoff fails.
        import ctypes
        hwnd = ctypes.windll.user32.FindWindowW(None, 'OKDEV • Mod Merkezi')
        if hwnd:
            ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)


class Api:
    def __init__(self):
        self._window = None
        self._selected = None
        self._cover = None
        self._source = None
        self._busy = threading.Lock()
        self._progress_lock = threading.Lock()
        self._download_progress = {'stage': 'idle', 'received': 0, 'total': 0}
        self._cancel_download = threading.Event()
        self._queue = None
        self._queue_lock = threading.Lock()
        self._profile_import = None
        self._closing = False
        self._allow_close = False
        self._close_lock = threading.Lock()
        try:
            import psutil
            self._started_at = psutil.Process().create_time()
        except Exception:
            self._started_at = time.time()

    def minimize_window(self):
        if self._window is not None:
            self._window.minimize()
        return {'ok': True}

    def close_window(self):
        if self._closing:
            return {'ok': True, 'result': None}
        return self._run(self._begin_close)

    def _begin_close(self):
        with self._close_lock:
            if self._closing:
                return
            self._closing = True
        if self._queue is not None:
            self._queue.close(persist_completion=True)
        def finish():
            # An explicit tray exit also waits for an already-running foreground
            # import/export. New actions are blocked by _closing.
            with self._busy:
                if self._queue is not None:
                    self._queue.close(persist_completion=True)
            if self._queue is not None:
                self._queue.wait_closed()
            self._allow_close = True
            if self._window is not None:
                self._window.destroy()
        threading.Thread(target=finish, name='OKDEV-safe-close', daemon=False).start()

    def _before_close(self):
        if self._allow_close:
            return True
        from .lifecycle import consume_shutdown
        if consume_shutdown(self._started_at):
            self._begin_close()
            return False
        active = self._queue is not None and self._queue.snapshot()['active'] > 0
        if active or self._busy.locked() or self._closing:
            def show():
                try:
                    self._window.evaluate_js("window.dispatchEvent(new Event('okdev-close-request'))")
                except Exception:
                    pass
            threading.Thread(target=show, daemon=True).start()
            return False
        return True

    def _downloads(self):
        with self._queue_lock:
            if self._queue is None:
                from .downloads import DownloadQueue
                self._queue = DownloadQueue()
            return self._queue

    def downloads_status(self):
        return self._downloads().snapshot()

    def enqueue_download(self, mod_id, source='curated'):
        return self._run(lambda: self._downloads().enqueue(mod_id, source))

    def cancel_queued_download(self, job_id):
        return self._run(lambda: self._downloads().cancel(job_id))

    def retry_download(self, job_id):
        return self._run(lambda: self._downloads().retry(job_id))

    def clear_download_history(self):
        return self._run(lambda: self._downloads().clear_finished())

    def repair_download_history(self):
        return self._run(lambda: self._downloads().repair_history())

    def snapshot(self, refresh=False):
        # Local actions must not wait on a network timeout. Fetch only when
        # the user explicitly refreshes the public catalog.
        data, warning = library.catalog(bool(refresh), allow_network=bool(refresh))
        try:
            with library.mutation_lock():
                pass  # Recover folder/index mutations before reading.
        except ValueError as exc:
            warning = (warning + ' ' + str(exc)).strip()
        try:
            installed = library.installed(strict=True)
        except ValueError as exc:
            installed = library.installed()
            warning = (warning + ' ' + str(exc)).strip()
        try:
            settings = library.settings(strict=True)
        except ValueError as exc:
            settings = library.settings()
            warning = (warning + ' ' + str(exc)).strip()
        from .profiles import list_profiles
        try:
            profiles = list_profiles(strict=True)
        except ValueError as exc:
            profiles = {}
            warning = (warning + ' ' + str(exc)).strip()
        for mod_id, item in installed.items():
            item['files_available'] = library.mod_folder(item).is_dir()
        from . import preferences, guides, companion, selections, activity
        return {'catalog': data['mods'], 'installed': installed, 'settings': settings,
                'preferences': preferences.get(), 'guide': guides.read_state(), 'companion': companion.status(),
                'removed': library.removed(), 'profiles': profiles, 'warning': warning,
                'downloads': self.downloads_status(), 'selection_undo': selections.undo_status(installed),
                'activity': activity.read()}

    def cover_previews(self, mod_ids):
        if not isinstance(mod_ids, list) or len(mod_ids) > 48 or not all(library.valid_id(v) for v in mod_ids):
            return {}
        from .covers import preview
        installed = library.installed()
        return {mod_id: {'key': installed[mod_id].get('cover_key'),
                         'data': preview(installed[mod_id].get('cover_key'))}
                for mod_id in set(mod_ids) if mod_id in installed}

    def guide_state(self):
        from . import guides, companion, preferences
        return {'guide': guides.read_state(), 'companion': companion.status(), 'preferences': preferences.get()}

    def save_preferences(self, changes):
        from . import preferences
        return self._run(lambda: preferences.update(changes))

    def show_guide(self, champion_id=None, role=''):
        def action():
            from . import companion, guides
            pick = None
            if champion_id is not None:
                guides.build_url(champion_id, role)
                pick = {'champion': {'id': champion_id}, 'role': role}
            companion.command('show', pick)
        return self._run(action)

    def hide_guide(self):
        from . import companion
        return self._run(lambda: companion.command('hide'))

    def save_profile(self, name):
        from .profiles import save
        return self._run(lambda: save(name))

    def apply_profile(self, profile_id):
        from .profiles import apply
        return self._run(lambda: apply(profile_id))

    def remove_profile(self, profile_id):
        from .profiles import remove
        return self._run(lambda: remove(profile_id))

    def rename_profile(self, profile_id, name):
        from .profiles import rename
        return self._run(lambda: rename(profile_id, name))

    def update_profile(self, profile_id):
        from .profiles import update
        return self._run(lambda: update(profile_id))

    def export_profile(self, profile_id):
        def action():
            import webview
            from .profiles import export_profile
            document = export_profile(profile_id)
            paths = self._window.create_file_dialog(webview.FileDialog.SAVE,
                save_filename='OKDEV_Profil.json', file_types=('OKDEV profili (*.json)',))
            if not paths:
                return {'saved': False}
            path = Path(paths if isinstance(paths, str) else paths[0])
            from .exports import write_json
            write_json(path, document)
            return {'saved': True}
        return self._run(action)

    def choose_profile(self):
        def action():
            import webview
            from .profiles import inspect_portable
            self._profile_import = None
            paths = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False,
                file_types=('OKDEV profili (*.json)',))
            if not paths:
                return None
            path = Path(paths if isinstance(paths, str) else paths[0])
            if path.stat().st_size > 512 * 1024:
                raise ValueError('Profil dosyası çok büyük. En fazla 512 KB olabilir.')
            try:
                document = json.loads(path.read_text(encoding='utf-8-sig'))
            except (ValueError, UnicodeError):
                raise ValueError('Profil dosyası okunamadı. Geçerli bir OKDEV profili seç.') from None
            preview = inspect_portable(document)
            self._profile_import = document
            return preview
        return self._run(action)

    def import_profile(self):
        def action():
            from .profiles import import_profile
            if self._profile_import is None:
                raise ValueError('Önce bir profil dosyası seç.')
            result = import_profile(self._profile_import)
            self._profile_import = None
            return result
        return self._run(action)

    def favorite(self, mod_id, favorite):
        return self._run(lambda: library.set_favorite(mod_id, favorite))

    def diagnostics(self):
        from .diagnostics import collect
        return self._run(collect)

    def recover_library(self):
        def action():
            with library.mutation_lock():
                pass
            from .transactions import status
            return status()
        return self._run(action)

    def export_diagnostics(self):
        def action():
            import webview
            from .diagnostics import collect
            report = collect()
            paths = self._window.create_file_dialog(webview.FileDialog.SAVE,
                save_filename='OKDEV_Destek_' + report['version'] + '.json',
                file_types=('Destek raporu (*.json)',))
            if not paths:
                return {'saved': False}
            path = Path(paths if isinstance(paths, str) else paths[0])
            from .exports import write_json
            write_json(path, report)
            return {'saved': True}
        return self._run(action)

    def open_data_folder(self):
        return self._run(lambda: os.startfile(str(library.root())))

    def open_project_page(self, page):
        destinations = {'releases': 'https://github.com/okdev01/OKDEV/releases',
                        'support': 'https://github.com/okdev01/OKDEV/issues',
                        'source': 'https://github.com/okdev01/OKDEV'}
        def action():
            if not isinstance(page, str) or page not in destinations:
                raise ValueError('Bu proje sayfası açılamıyor.')
            if not webbrowser.open(destinations[page]):
                raise ValueError('Tarayıcı açılamadı. Varsayılan tarayıcını kontrol et.')
        return self._run(action)

    def inspect_backup(self, backup_id):
        from . import backups
        return self._run(lambda: backups.inspect(backup_id))

    def export_backup(self, backup_id):
        def action():
            import webview
            from . import backups
            info = backups.inspect(backup_id)
            paths = self._window.create_file_dialog(webview.FileDialog.SAVE,
                save_filename='OKDEV-Yedek-' + backup_id[:8] + '.fantome',
                file_types=('Mod paketi (*.fantome)',))
            if not paths:
                return {'saved': False}
            destination = paths[0] if isinstance(paths, (list, tuple)) else paths
            return backups.export(info['id'], Path(destination))
        return self._run(action)

    def open_source(self, source_id):
        def action():
            from .sources import entries
            entry = next((item for item in entries() if item['id'] == source_id), None)
            if not entry:
                raise ValueError('Kaynak bulunamadı')
            webbrowser.open(entry['source_url'])
        return self._run(action)

    def prepare_import(self, source_id=None):
        def action():
            from .sources import entries
            source = None
            if source_id is not None:
                source = next((m for m in entries() if m['id'] == source_id), None)
                if not source:
                    raise ValueError('Kaynak bulunamadı')
            self._source = source
            self._selected = None
            self._cover = None
        return self._run(action)

    def _run(self, action):
        if self._closing:
            return {'ok': False, 'error': 'Uygulama kapanıyor. İşlemler güvenle tamamlanıyor.'}
        if not self._busy.acquire(blocking=False):
            return {'ok': False, 'error': 'Diğer işlemin bitmesini bekleyin.'}
        try:
            result = action()
            return {'ok': True, 'result': result}
        except Exception as exc:
            # Do not expose requests, headers or credentials in the UI.
            from .errors import message
            return {'ok': False, 'error': message(exc)}
        finally:
            self._busy.release()

    def download(self, mod_id):
        return self._download_with(lambda progress, cancelled: library.download(mod_id, progress, cancelled))

    def download_source(self, source_id):
        return self._download_with(lambda progress, cancelled: library.download_source(source_id, progress, cancelled))

    def _download_with(self, operation):
        def progress(value):
            with self._progress_lock:
                self._download_progress = value

        def action():
            self._cancel_download.clear()
            progress({'stage': 'downloading', 'received': 0, 'total': 0})
            try:
                return operation(progress, self._cancel_download.is_set)
            finally:
                progress({'stage': 'idle', 'received': 0, 'total': 0})
        return self._run(action)

    def download_status(self):
        with self._progress_lock:
            return dict(self._download_progress)

    def cancel_download(self):
        with self._progress_lock:
            if self._download_progress['stage'] == 'downloading':
                self._cancel_download.set()
                return {'ok': True}
        return {'ok': False, 'error': 'Dosya doğrulama ve yükleme aşamasına geçti.'}

    def enable(self, mod_id, enabled):
        from . import selections
        if type(enabled) is not bool:
            return {'ok': False, 'error': 'Geçersiz mod seçimi.'}
        return self._run(lambda: selections.apply([mod_id], 'enable' if enabled else 'disable'))

    def preview_selection(self, mod_ids, mode='enable'):
        from . import selections
        return self._run(lambda: selections.preview(mod_ids, mode))

    def apply_selection(self, mod_ids, mode, revision):
        from . import selections
        return self._run(lambda: selections.apply(mod_ids, mode, revision))

    def undo_selection(self):
        from . import selections
        return self._run(selections.undo)

    def remove(self, mod_id):
        return self._run(lambda: library.remove(mod_id))

    def restore(self, backup_id):
        return self._run(lambda: library.restore(backup_id))

    def auto_accept(self, enabled):
        return self._run(lambda: library.set_auto_accept(enabled))

    def choose_mod(self):
        import webview
        paths = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False,
                                                file_types=('Mod paketi (*.fantome;*.zip)',))
        if not paths:
            return None
        from .package_info import inspect
        selected = Path(paths[0])
        result = inspect(selected)
        if self._source:
            detected = result['suggested'].get('champion_id')
            if detected is not None and detected != self._source.get('champion_id'):
                raise ValueError('Seçilen paket bu kaynakta gösterilen şampiyonla eşleşmiyor.')
            result['suggested'] = {key: value for key, value in result['suggested'].items() if key == 'version'}
        self._selected = selected
        return result

    def _item(self, fields):
        if not self._selected:
            raise ValueError('Önce bir mod dosyası seçin')
        item = {key: str(fields.get(key, '')).strip() for key in ('id', 'name', 'champion', 'description', 'version')}
        from .package_info import inspect, slug
        item['id'] = item['id'] or slug(item['name']) or 'yerel-mod'
        item['version'] = item['version'] or '1.0.0'
        item['category'] = fields.get('category', 'skins')
        try:
            item['champion_id'] = int(fields.get('champion_id') or 0) if item['category'] == 'skins' else None
        except (TypeError, ValueError):
            raise ValueError('Listeden geçerli bir şampiyon seç.') from None
        if item['category'] == 'skins' and not item['champion_id']:
            from .guides import champions
            champion = next((c for c in champions().values() if c['name'].casefold() == item['champion'].casefold()), None)
            if champion:
                item['champion_id'] = champion['id']
        if self._source:
            if (item['category'] != self._source['category']
                    or item['champion_id'] != self._source.get('champion_id')):
                raise ValueError('Kategori ve şampiyon özgün kaynakla eşleşmeli. Farklı bir paket için formu temizleyin.')
            item.update({key: self._source[key] for key in ('author', 'license', 'source_url')})
        suggested = inspect(self._selected)['suggested']
        if suggested.get('champion_id') is not None and suggested['champion_id'] != item['champion_id']:
            raise ValueError('Paketin şampiyonu seçilen şampiyonla eşleşmiyor.')
        if not self._source and suggested.get('author'):
            item['author'] = suggested['author']
        library.validate_metadata(item)
        return item

    def choose_cover(self):
        import webview
        paths = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False,
                                                file_types=('Mod görseli (*.png;*.jpg;*.jpeg;*.webp)',))
        if not paths:
            return None
        self._cover = Path(paths[0])
        return self._cover.name

    def import_mod(self, fields):
        return self._run(lambda: library.import_archive(self._selected, self._item(fields)))

    def publish_mod(self, fields, token):
        from .publisher import publish
        if self._source:
            return {'ok': False, 'error': 'Bu içerik özgün RuneForge sayfasından dağıtılır. Yerel içe aktarmayı kullanın.'}
        return self._run(lambda: publish(self._selected, self._item(fields), token, self._cover))

    def mobalytics(self, external=False):
        if external:
            webbrowser.open(MOBALYTICS)
        else:
            import webview
            # External pages never receive OKDEV's Python API bridge.
            webview.create_window('Mobalytics • OKDEV', MOBALYTICS, width=1200, height=850)
        return {'ok': True}


def run(smoke_path=None):
    if smoke_path:
        import tempfile
        from utils.core import paths
        previous, migrated = paths._cached_user_data_dir, paths._migration_checked
        try:
            with tempfile.TemporaryDirectory(prefix='okdev-hub-smoke-', ignore_cleanup_errors=True) as temporary:
                paths._cached_user_data_dir = Path(temporary)
                paths._migration_checked = True
                return _run_window(smoke_path)
        finally:
            paths._cached_user_data_dir, paths._migration_checked = previous, migrated
    return _run_window()


def _run_window(smoke_path=None):
    import webview
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    mutex = kernel.CreateMutexW(None, False, 'Local\\OKDEV-ModHub' + ('-Smoke-' + str(os.getpid()) if smoke_path else ''))
    if not mutex:
        raise RuntimeError('Mod Merkezi başlatılamadı.')
    if ctypes.get_last_error() == 183:
        if smoke_path:
            Path(smoke_path).write_text(json.dumps({'skipped': 'Mod Merkezi zaten açık; mevcut pencereye dokunulmadı.'}), encoding='utf-8')
            kernel.CloseHandle(mutex)
            return
        hwnd = ctypes.windll.user32.FindWindowW(None, 'OKDEV • Mod Merkezi')
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 9)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        kernel.CloseHandle(mutex)
        return
    api = Api()
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    html = build_html(base)
    api._window = webview.create_window('OKDEV • Arayüz kontrolü' if smoke_path else 'OKDEV • Mod Merkezi', html=html, js_api=api,
                                       width=1180, height=800, min_size=(850, 620), background_color='#0d111a')
    def close_companions():
        if api._queue is not None:
            api._queue.close()
        for window in list(webview.windows):
            if window is not api._window:
                window.destroy()
    api._window.events.closed += close_companions
    api._window.events.closing += api._before_close
    def check_pending_shutdown(*_):
        from .lifecycle import consume_shutdown
        if consume_shutdown(api._started_at):
            api._begin_close()
    api._window.events.loaded += check_pending_shutdown
    def smoke():
        import time
        try:
            if not api._window.events.loaded.wait(25):
                raise TimeoutError('WebView yüklenemedi.')
            for _ in range(100):
                result = api._window.evaluate_js("JSON.stringify({title:document.title,sections:document.querySelectorAll('.section').length,bridge:!!(window.pywebview&&window.pywebview.api&&window.pywebview.api.snapshot),ready:document.getElementById('main').getAttribute('aria-busy')==='false',sources:document.querySelectorAll('#catalogGrid .card').length,installed:document.getElementById('installedCount').textContent})")
                result = json.loads(result)
                if result['bridge'] and result['ready']:
                    assert result['sections'] == 9
                    assert result['sources'] >= 24 and result['installed'] == '0'
                    result['ok'] = True
                    Path(smoke_path).write_text(json.dumps(result), encoding='utf-8')
                    break
                time.sleep(.2)
            else:
                raise TimeoutError('Arayüz bağlantısı hazır olmadı.')
        except Exception as exc:
            Path(smoke_path).write_text(json.dumps({'ok': False, 'error': str(exc)}), encoding='utf-8')
        finally:
            api._window.destroy()
    try:
        webview.start(smoke if smoke_path else None, gui='edgechromium', icon=str(base / 'assets/icon.ico'),
                      storage_path=str(library.root() / 'webview'), private_mode=False)
    finally:
        kernel.CloseHandle(mutex)
