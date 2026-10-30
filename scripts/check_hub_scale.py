"""Render large synthetic libraries in the real WebView2, entirely offline.

This measures UI rendering, not archive processing or real League behavior.
The bridge is in memory; user files, settings and games are never touched.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hub.desktop import build_html
from hub.preferences import DEFAULTS


class FixtureApi:
    def __init__(self):
        self.count = 100
        self.preferences = copy.deepcopy(DEFAULTS)

    def snapshot(self, refresh=False):
        mods = {}
        for i in range(self.count):
            identifier = f'scale-{i:05d}'
            mods[identifier] = {
                'id': identifier, 'name': f'Mod {i:05d} · ' + ('Uzun isim İğne Şampiyon Görünümü ' * 4 if i % 31 == 0 else 'Gece görünümü'),
                'champion': 'Ahri', 'champion_id': 103,
                'category': ('skins', 'ui', 'maps')[i % 3],
                'version': '1.0.0', 'enabled': i % 7 == 0,
                'files_available': i % 11 != 0, 'installed_at': 1700000000 + i,
                'description': 'Uzun açıklama. ' * 60,
                'author': 'Yerel arayüz test verisi',
            }
        profiles = {f'profile-{i}': {'name': f'Profil {i} · Uzun profil adı testi',
                    'mods': [f'scale-{j:05d}' for j in range(i, min(i + 5, self.count))]}
                    for i in range(min(12, self.count))}
        return {'catalog': [], 'installed': mods, 'settings': {'favorites': []},
                'preferences': self.preferences, 'guide': {}, 'companion': {},
                'profiles': profiles, 'removed': [], 'downloads': self.downloads_status(),
                'activity': {'events': []}, 'selection_undo': {'available': False},
                'revision': str(self.count), 'warning': ''}

    def guide_state(self):
        return {'guide': {}, 'companion': {}, 'preferences': self.preferences}

    def downloads_status(self):
        return {'jobs': [], 'active': 0}

    def state_revision(self):
        return str(self.count)

    def cover_previews(self, *args):
        return {}

    def save_preferences(self, changes):
        self.preferences.update(changes)
        return {'ok': True, 'result': self.preferences}

    def diagnostics(self):
        return {'ok': True, 'result': {'version': '2.0.0', 'checked_at': '2026-10-30T21:00:00Z',
            'note': 'Yalıtılmış arayüz testi', 'storage': [], 'checks': [
                {'name': 'Yüklü mod dosyaları', 'status': 'warning',
                 'detail': 'Yeniden içe aktarılması gerekenler: ' + 'A' * 100},
                {'name': 'Mod kayıtları', 'status': 'ok', 'detail': 'Kayıt dosyası okunabiliyor.'},
            ]}}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--layout', action='store_true', help='Also sweep every page, theme, viewport and zoom level')
    args = parser.parse_args()
    import webview
    out = ROOT / 'output/ui2-20261030'
    out.mkdir(parents=True, exist_ok=True)
    report = {'ok': False, 'scope': __doc__, 'libraries': [], 'checks': [], 'errors': [],
              'source_sha256': {f: hashlib.sha256((ROOT/f).read_bytes()).hexdigest()
                                for f in ('hub/web/app.js', 'hub/web/app.css', 'hub/web/index.html')}}
    api = FixtureApi()
    with patch('hub.preferences.get', return_value=copy.deepcopy(DEFAULTS)):
        html = build_html().replace('img-src data: https:;', 'img-src data:;')
    window = webview.create_window('OKDEV • Kütüphane ölçek testi', html=html, js_api=api,
                                   width=1180, height=800, min_size=(600, 460))

    def evaluate(js):
        return window.evaluate_js(js)

    def wait(expression, timeout=25):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if evaluate(expression): return
            except Exception: pass
            time.sleep(.04)
        raise AssertionError('Timed out: '+expression)

    def cdp(method, params):
        from System import Func, Object
        task = window.native.webview.Invoke(Func[Object](lambda:
            window.native.webview.CoreWebView2.CallDevToolsProtocolMethodAsync(method, json.dumps(params))))
        assert task.Wait(10000), method
        return json.loads(task.Result)

    def tap(selector):
        encoded = json.dumps(selector)
        evaluate(f'document.querySelector({encoded}).scrollIntoView({{block:"center",behavior:"instant"}})')
        time.sleep(.05)
        point = evaluate(f'''(()=>{{const e=document.querySelector({encoded}),r=e.getBoundingClientRect();
          const x=r.left+r.width/2,y=r.top+r.height/2,top=document.elementFromPoint(x,y);
          return {{x,y,hit:(top===e||e.contains(top))&&!e.disabled,width:r.width,height:r.height}};}})()''')
        assert point['hit'] and point['width'] and point['height'], (selector, point)
        for event in ('mousePressed', 'mouseReleased'):
            cdp('Input.dispatchMouseEvent', {'type': event, 'x': point['x'], 'y': point['y'], 'button': 'left', 'clickCount': 1})
        wait('document.getElementById("main").getAttribute("aria-busy")==="false"')

    def check(name, expression):
        assert evaluate(expression), name
        report['checks'].append(name)

    def capture(name):
        import base64
        time.sleep(.2)
        result = cdp('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': False})
        folder = out / 'screenshots'; folder.mkdir(exist_ok=True)
        (folder / ('scale-'+name+'.png')).write_bytes(base64.b64decode(result['data']))

    def exercise():
        try:
            wait('document.querySelector("#installedGrid .card") && !document.body.classList.contains("initializing")')
            evaluate('window.__scaleErrors=[];addEventListener("error",e=>__scaleErrors.push(e.message));addEventListener("unhandledrejection",e=>__scaleErrors.push(String(e.reason)))')
            tap('[data-page="installed"]')
            for count in (100, 1000, 10000):
                api.count = count
                evaluate('document.getElementById("installedSearch").value="reset";document.getElementById("installedSearch").dispatchEvent(new Event("input"));document.getElementById("installedSearch").value="";document.getElementById("installedSearch").dispatchEvent(new Event("input"))')
                tap('[data-page="library"]')
                started = time.perf_counter()
                tap('#refresh')
                wait(f'document.getElementById("installedResults").textContent.startsWith("{count} mod")')
                refresh_ms = round((time.perf_counter()-started)*1000, 2)
                tap('[data-page="installed"]')
                check(f'{count}: initial DOM is capped at 24 cards', 'document.querySelectorAll("#installedGrid .card").length===24')
                tap('#moreInstalled')
                check(f'{count}: pagination renders exactly 48 cards', 'document.querySelectorAll("#installedGrid .card").length===48')
                timings = []
                for _ in range(5):
                    timings.append(evaluate('''(()=>{const e=document.getElementById('installedSearch'),start=performance.now();
                      e.value='Uzun isim';e.dispatchEvent(new Event('input'));return performance.now()-start;})()'''))
                    check(f'{count}: filtered pagination resets', 'document.querySelectorAll("#installedGrid .card").length<=24')
                    evaluate('document.getElementById("installedSearch").value="";document.getElementById("installedSearch").dispatchEvent(new Event("input"))')
                # Use native text input as well; the direct event above isolates render time.
                tap('#installedSearch')
                cdp('Input.insertText', {'text': f'Mod {count-1:05d}'})
                wait('document.querySelectorAll("#installedGrid .card").length===1')
                check(f'{count}: native search finds final entry', f'document.querySelector("#installedGrid .card").dataset.modId==="scale-{count-1:05d}"')
                evaluate('document.getElementById("installedSearch").value="";document.getElementById("installedSearch").dispatchEvent(new Event("input"))')
                check(f'{count}: library has no horizontal overflow', 'document.documentElement.scrollWidth<=innerWidth')
                report['libraries'].append({'count': count, 'refresh_bridge_and_render_ms': refresh_ms,
                    'filter_render_ms': timings, 'dom_nodes': evaluate('document.querySelectorAll("*").length'),
                    'heap': cdp('Runtime.getHeapUsage', {})})
            tap('[data-view-owner="installed"][data-view-mode="list"]')
            window.resize(850, 620); time.sleep(.2)
            check('10000: narrow list has no horizontal overflow', 'document.documentElement.scrollWidth<=innerWidth')
            capture('10000-list')
            tap('#installedGrid .actions button:last-child')
            check('Long description scrolls inside detail dialog', '''(()=>{const e=document.getElementById('detailDialog'),r=e.getBoundingClientRect();return e.open&&r.top>=0&&r.bottom<=innerHeight+1&&r.right<=innerWidth+1;})()''')
            capture('long-detail')
            evaluate('document.getElementById("detailDialog").close()')
            tap('[data-page="profiles"]')
            check('Twelve long-name profiles fit without overflow', 'document.querySelectorAll("#profileCards .profile-card").length===12&&document.documentElement.scrollWidth<=innerWidth')
            capture('profiles')
            tap('[data-page="installed"]')
            api.count = 0
            tap('[data-page="library"]'); tap('#refresh'); tap('[data-page="installed"]')
            wait('document.querySelectorAll("#installedGrid .card").length===0')
            check('Empty library has a useful next action', '!!document.querySelector("#installedGrid .empty button")')
            capture('empty')
            tap('[data-page="diagnostics"]'); tap('#checkDiagnostics')
            capture('long-diagnostic')
            check('A valid 100-character unbroken mod name fits diagnostics', 'document.documentElement.scrollWidth<=innerWidth')
            if args.layout:
                from hub_layout_qa import run
                report['layout'] = run(window, evaluate, tap, cdp, capture, api, ROOT)
            check('No unhandled script errors', 'window.__scaleErrors.length===0')
            report['ok'] = True
        except Exception as error:
            report['errors'].append(f'{type(error).__name__}: {error}')
            try: capture('failure')
            except Exception: pass
        finally:
            (out / 'hub-scale.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            window.destroy()
    webview.start(exercise, gui='edgechromium', private_mode=True)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['ok'] else 1


if __name__ == '__main__': raise SystemExit(main())
