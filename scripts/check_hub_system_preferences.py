"""Offline WebView checks for OS appearance, motion and data-saving preferences."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from check_hub_scale import FixtureApi
from hub.desktop import build_html


def main():
    import webview
    api = FixtureApi()
    api.count = 6
    api.preferences['theme'] = 'system'
    original_snapshot = api.snapshot
    def snapshot(refresh=False):
        value = original_snapshot(refresh)
        for mod in value['installed'].values():
            mod['image_url'] = 'https://ui-fixture.invalid/blocked-preview.png'
        return value
    api.snapshot = snapshot
    out = ROOT / 'output/ui2-20261030'
    report = {'ok': False, 'checks': [], 'errors': [], 'source_sha256': {
        name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        for name in ('hub/web/app.js', 'hub/web/index.html', 'hub/web/app.css')},
        'scope': 'Isolated WebView2 with in-memory bridge. OS media emulated through CDP; network images blocked by CSP.'}
    with patch('hub.preferences.get', return_value=copy.deepcopy(api.preferences)):
        html = build_html().replace('img-src data: https:;', 'img-src data:;')
    window = webview.create_window('OKDEV • Sistem tercihleri testi', html=html, js_api=api,
                                  width=1180, height=800, min_size=(600, 460))
    def evaluate(js):
        return window.evaluate_js(js)
    def wait(expression):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                if evaluate(expression): return
            except Exception: pass
            time.sleep(.05)
        raise AssertionError(expression)
    def check(name, expression):
        assert evaluate(expression), name
        report['checks'].append(name)
    def cdp(method, params):
        from System import Func, Object
        task = window.native.webview.Invoke(Func[Object](lambda:
            window.native.webview.CoreWebView2.CallDevToolsProtocolMethodAsync(method, json.dumps(params))))
        assert task.Wait(10000), method
        return json.loads(task.Result)
    def media(scheme='dark', motion='no-preference', contrast='none'):
        cdp('Emulation.setEmulatedMedia', {'features': [
            {'name': 'prefers-color-scheme', 'value': scheme},
            {'name': 'prefers-reduced-motion', 'value': motion},
            {'name': 'forced-colors', 'value': contrast}]})
        time.sleep(.1)
    def pref(name, value):
        evaluate(f"(()=>{{const e=document.querySelector('[data-pref={name}]');e[e.type==='checkbox'?'checked':'value']={json.dumps(value)};e.dispatchEvent(new Event('change',{{bubbles:true}}));}})()")
        wait("document.getElementById('main').getAttribute('aria-busy')==='false'")
        time.sleep(.1)
        assert api.preferences[name] == value, (name, value)
    def capture(name):
        data = cdp('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': False})
        (out / 'screenshots' / (name+'.png')).write_bytes(base64.b64decode(data['data']))
    def exercise():
        try:
            wait("!document.body.classList.contains('initializing') && document.querySelector('#installedGrid .card')")
            evaluate("window.__prefErrors=[];window.__blocked=[];addEventListener('error',e=>__prefErrors.push(e.message));addEventListener('unhandledrejection',e=>__prefErrors.push(String(e.reason)));addEventListener('securitypolicyviolation',e=>__blocked.push(e.blockedURI))")
            for scheme in ('light', 'dark', 'light'):
                media(scheme)
                wait(f'document.documentElement.dataset.theme==="{scheme}"')
                check(f'System theme follows {scheme} without reopening', f'document.documentElement.dataset.theme==="{scheme}"')
            pref('theme', 'dark')
            media('light')
            check('Explicit dark theme survives light OS preference', 'document.documentElement.dataset.theme==="dark"')
            pref('theme', 'light')
            media('dark')
            check('Explicit light theme survives dark OS preference', 'document.documentElement.dataset.theme==="light"')
            evaluate("window.__motionProbe=document.createElement('span');__motionProbe.className='loading-spinner';__motionProbe.style.cssText='position:fixed;left:-999px';document.body.append(__motionProbe)")
            media(motion='reduce')
            check('OS reduced motion disables spinner animation', 'getComputedStyle(__motionProbe).animationName==="none"')
            media()
            check('Default motion permits progress animation', 'getComputedStyle(__motionProbe).animationName!=="none"')
            pref('reduce_motion', True)
            check('Application reduced-motion setting overrides OS default', 'getComputedStyle(__motionProbe).animationName==="none"')
            pref('reduce_motion', False)
            evaluate('__motionProbe.remove()')
            check('Data saver starts enabled', 'document.getElementById("dataSaver").checked')
            evaluate('document.querySelector("[data-page=installed]").click()')
            check('Data saver creates no remote image elements', "document.querySelectorAll('#installedGrid img[src^=\"https:\"]').length===0")
            pref('data_saver', False)
            wait('__blocked.some(url=>url.includes("ui-fixture.invalid"))')
            wait('document.querySelectorAll("#installedGrid img").length===0')
            check('Blocked image falls back to usable mod cards', 'document.querySelectorAll("#installedGrid .card").length===6 && [...document.querySelectorAll("#installedGrid .actions button")].some(e=>!e.disabled)')
            pref('data_saver', True)
            before = evaluate('__blocked.length')
            evaluate('document.querySelector("[data-page=library]").click();document.querySelector("[data-page=installed]").click()')
            check('Reenabled data saver stops new remote preview attempts', f'__blocked.length==={before}')
            pref('theme', 'system')
            for scheme in ('dark', 'light'):
                media(scheme=scheme, contrast='active')
                check('Forced colors emulation is active: '+scheme, 'matchMedia("(forced-colors:active)").matches')
                for page in ('home', 'installed', 'assistants', 'profiles'):
                    evaluate(f'document.querySelector("[data-page={page}]").click()')
                    time.sleep(.15)
                    check(f'Forced colors {scheme}/{page} has no horizontal overflow', 'document.documentElement.scrollWidth<=innerWidth')
                    if page == 'assistants':
                        for selector, state in (('#compactCards', False), ('#dataSaver', True)):
                            check(f'Forced-color {scheme} switch state {state} has a visible thumb', f"(()=>{{const e=document.querySelector('{selector}');return e.checked==={str(state).lower()}&&getComputedStyle(e,'::before').backgroundColor!==getComputedStyle(e).backgroundColor;}})()")
                        evaluate('document.getElementById("theme").focus()')
                        for kind in ('keyDown', 'keyUp'):
                            cdp('Input.dispatchKeyEvent', {'type': kind, 'key': 'Tab', 'code': 'Tab', 'windowsVirtualKeyCode': 9})
                        check('Forced-color keyboard focus remains outlined: '+scheme, 'parseFloat(getComputedStyle(document.activeElement).outlineWidth)>0')
                    if page in ('home', 'assistants'):
                        capture(f'forced-colors-{scheme}-{page}')
            check('No unhandled preference errors', '__prefErrors.length===0')
            report['ok'] = True
        except Exception as error:
            report['errors'].append(f'{type(error).__name__}: {error}')
            try: capture('system-preferences-failure')
            except Exception: pass
        finally:
            (out/'hub-system-preferences.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            window.destroy()
    webview.start(exercise, gui='edgechromium', private_mode=True)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['ok'] else 1


if __name__ == '__main__': raise SystemExit(main())
