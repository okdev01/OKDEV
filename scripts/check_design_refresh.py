"""Render the real Hub in isolated WebView2 storage, with explicit concept fixtures.

Never touches the user's installed mods. No live League match or remote download.
"""
import base64
from contextlib import ExitStack
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'output/design-refresh-20261031'


def main():
    import webview
    from hub import library, profiles, preferences
    from hub.desktop import Api, build_html
    result = {'ok': False, 'checks': [], 'layouts': [], 'accessibility': [],
              'scope': 'Actual WebView2 and Python services in temporary storage. Concept mod fixtures, no live game.',
              'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                for name in ('hub/web/app.js', 'hub/web/index.html', 'hub/web/app.css', 'hub/desktop.py')}}
    with tempfile.TemporaryDirectory(prefix='okdev-design-') as tmp, ExitStack() as stack:
        data = Path(tmp)
        for name in ('hub.library.get_user_data_dir', 'injection.mods.storage.get_user_data_dir',
                     'utils.core.historic.get_user_data_dir', 'utils.core.mod_historic.get_user_data_dir'):
            stack.enter_context(patch(name, return_value=data))
        library.write_json(library.root() / 'catalog.json', {'schema': 1, 'mods': []})
        fixtures = [('font', 'Korean Font', 'fonts', '', 0, None),
                    ('hud', 'Dark Mode Minimap', 'ui', '', 0, None),
                    ('caitlyn', 'Caitlyn with Caitlyn', 'skins', 'Caitlyn', 51, 'mod-caitlyn'),
                    ('mordekaiser', 'Iron Golem Mordekaiser', 'skins', 'Mordekaiser', 82, 'mod-mordekaiser'),
                    ('darius', 'Berserker Darius', 'skins', 'Darius', 122, 'mod-darius')]
        for index, (ident, name, category, champion, champion_id, artwork) in enumerate(fixtures):
            package = data / (ident + '.fantome')
            with zipfile.ZipFile(package, 'w') as archive:
                archive.writestr('WAD/' + (champion or 'ui') + '.wad.client', b'Design QA fixture, not a playable mod')
                if artwork:
                    from PIL import Image
                    with Image.open(ROOT / 'hub/web/assets' / (artwork + '.webp')) as image:
                        preview = io.BytesIO()
                        image.save(preview, format='PNG')
                        archive.writestr('META/image.png', preview.getvalue())
            library.import_archive(package, {'id': ident, 'name': name, 'category': category,
                'champion': champion, 'champion_id': champion_id or None, 'version': '1.0.0',
                'description': 'Tasarım kontrolüne özel konsept örnek. Gerçek mod veya oyun içi önizleme değildir.'})
        installed = library.installed()
        for index, ident in enumerate([item[0] for item in fixtures]):
            installed[ident]['installed_at'] = 100 + index
        library.write_json(library.root() / 'installed.json', installed)
        library.enable('font', True); library.enable('hud', True)
        profile_id = profiles.save('Varsayılan')
        preferences.update({'theme': 'dark', 'data_saver': True})
        api = Api()
        window = webview.create_window('OKDEV • Tasarım doğrulaması', html=build_html(), js_api=api,
                                       width=1200, height=850)
        api._window = window

        def wait(expression, timeout=20):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    if window.evaluate_js(expression):
                        return
                except Exception:
                    pass
                time.sleep(.08)
            raise AssertionError('Timed out: ' + expression)

        def check(name, expression):
            assert window.evaluate_js(expression), name
            result['checks'].append(name)

        def cdp(method, params):
            from System import Func, Object
            task = window.native.webview.Invoke(Func[Object](lambda:
                window.native.webview.CoreWebView2.CallDevToolsProtocolMethodAsync(method, json.dumps(params))))
            assert task.Wait(15000), method
            return json.loads(task.Result)

        def viewport(width, height, scale=1):
            cdp('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': False})
            window.evaluate_js('document.documentElement.style.zoom=' + json.dumps(str(scale)))
            time.sleep(.2)

        def capture(name):
            time.sleep(.25)
            value = cdp('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': False})
            (OUT / (name + '.png')).write_bytes(base64.b64decode(value['data']))

        def click(selector):
            window.evaluate_js('document.querySelector(' + json.dumps(selector) + ').click()')
            wait("document.getElementById('main').getAttribute('aria-busy')==='false'")

        def native_click(selector):
            encoded = json.dumps(selector)
            window.evaluate_js(f"document.querySelector({encoded}).scrollIntoView({{block:'center',behavior:'instant'}})")
            point = window.evaluate_js(f"(()=>{{const e=document.querySelector({encoded}),r=e.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2;return {{x,y,hit:e.contains(document.elementFromPoint(x,y))}};}})()")
            assert point.pop('hit'), 'Obstructed: ' + selector
            for event in ('mousePressed','mouseReleased'):
                cdp('Input.dispatchMouseEvent', {'type':event,'button':'left','clickCount':1,**point})
            time.sleep(.15)
            wait("document.getElementById('main').getAttribute('aria-busy')==='false'")

        def run():
            try:
                wait("document.body.classList.contains('bridge-ready')")
                wait("document.querySelectorAll('#homeRecent img').length===3")
                wait("document.getElementById('homeProfile').value!==''")
                viewport(1600, 1000)
                capture('home-1600x1000')
                check('Real local counters and profile match', "document.getElementById('installedCount').textContent==='5' && document.getElementById('activeCount').textContent==='2' && document.getElementById('homeProfile').selectedOptions[0].textContent==='Varsayılan'")
                check('Native file drop listeners installed', "document.getElementById('homeDropzone').hasAttribute('data-pywebview-id')")
                native_click('#loadoutItems .mod-switch')
                wait("document.getElementById('activeCount').textContent==='1'")
                assert not library.installed()['font']['enabled']
                result['checks'].append('Home switch persists through the real Python service')
                with patch('hub.selections.apply', side_effect=ValueError('Deneme: kayıt başarısız.')):
                    native_click('#loadoutItems .mod-switch')
                    wait("document.getElementById('status').textContent.includes('kayıt başarısız')")
                    assert library.installed()['hud']['enabled']
                    check('Failed save preserves the enabled switch and count', "document.getElementById('activeCount').textContent==='1' && document.querySelector('#loadoutItems .mod-switch').getAttribute('aria-checked')==='true'")
                window.evaluate_js("document.getElementById('homeProfile').value="+json.dumps(profile_id)+";document.getElementById('homeProfile').dispatchEvent(new Event('change'))")
                wait("document.getElementById('selectionDialog').open")
                native_click('#confirmSelection')
                wait("document.getElementById('activeCount').textContent==='2'")
                check('Home profile confirmation restores matching selections', 'document.getElementById("homeProfile").value==='+json.dumps(profile_id))
                drop_handler = next(handler for node in window.dom._elements.values()
                                    for handler in node._event_handlers.get('drop', []))
                drop_handler({'dataTransfer':{'files':[{'pywebviewFullPath':str(data/'darius.fantome')}]}})
                wait("!document.getElementById('publish').hidden && document.getElementById('selected').textContent==='darius.fantome'")
                check('Native drop callback uses the reviewed import form', "!document.querySelector('#modForm [type=submit]').disabled && document.getElementById('championName').value==='Darius'")
                click('[data-page="home"]')
                viewport(850,700)
                native_click('#menuToggle')
                check('Compact menu exposes navigation to keyboard', "document.getElementById('menuToggle').getAttribute('aria-expanded')==='true' && document.activeElement.dataset.page==='home'")
                for event in ('keyDown','keyUp'):
                    cdp('Input.dispatchKeyEvent',{'type':event,'key':'Escape','code':'Escape','windowsVirtualKeyCode':27})
                check('Native Escape closes menu and restores its button', "document.getElementById('menuToggle').getAttribute('aria-expanded')==='false' && document.activeElement.id==='menuToggle'")
                viewport(1600,1000)
                click('[data-page="home"]')
                window.evaluate_js("document.getElementById('status').replaceChildren()")
                for width, height in [(1600,1000),(1920,1080),(1440,900),(1280,800),(1024,768),(850,700),(500,850)]:
                    for zoom in (1,2):
                        viewport(width,height,zoom)
                        for page in ('home','library','installed','profiles','guides','downloads','assistants','diagnostics','publish'):
                            click('[data-page="'+page+'"]' if page!='publish' else '#quickImport')
                            layout = window.evaluate_js("""(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth,
                              outside:[...document.querySelectorAll('main button,main input,main select,main h2')].filter(e=>!e.closest('[hidden],dialog:not([open]),details:not([open])')).filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&(r.right>innerWidth+2||r.left< -2)}).map(e=>e.id||e.className)}))()""")
                            result['layouts'].append({'size':[width,height],'zoom':zoom,'page':page,**layout})
                            assert layout['scroll'] <= layout['client'] + 2 and not layout['outside'], str(result['layouts'][-1])
                        if zoom == 1:
                            click('[data-page="home"]'); capture(f'home-{width}x{height}')
                viewport(1600,1000)
                for page in ('library','installed','profiles','guides','downloads','assistants','diagnostics','publish'):
                    click('[data-page="'+page+'"]' if page!='publish' else '#quickImport'); capture(page)
                window.evaluate_js((ROOT / 'test/ui/node_modules/axe-core/axe.min.js').read_text(encoding='utf-8'))
                for theme in ('dark','light'):
                    click('[data-page="assistants"]')
                    window.evaluate_js("document.getElementById('theme').value="+json.dumps(theme)+";document.getElementById('theme').dispatchEvent(new Event('change'))")
                    wait("document.getElementById('main').getAttribute('aria-busy')==='false'")
                    time.sleep(.3)  # Complete the theme's 160 ms surface transitions.
                    for page in ('home','library','installed','profiles','guides','downloads','assistants','diagnostics','publish'):
                        click('[data-page="'+page+'"]' if page!='publish' else '#quickImport')
                        window.evaluate_js("window.__audit=null;axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}},(e,r)=>window.__audit=e?{error:String(e)}:{violations:r.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}))})")
                        wait('window.__audit!==null')
                        audit=window.evaluate_js('window.__audit');result['accessibility'].append({'theme':theme,'page':page,**audit})
                        assert not audit.get('error') and not audit['violations'], str(result['accessibility'][-1])
                    click('[data-page="home"]');capture('home-'+theme)
                # Edge cases use the same temporary library and snapshot service.
                click('[data-page="assistants"]')
                window.evaluate_js("document.getElementById('theme').value='dark';document.getElementById('theme').dispatchEvent(new Event('change'))")
                wait("document.getElementById('main').getAttribute('aria-busy')==='false'")
                saved = library.installed()
                changed = json.loads(json.dumps(saved))
                changed['darius']['name'] = 'Çok Uzun Türkçe Şampiyon Modu — Karanlık Vadi ve Yıldız Muhafızları Koleksiyonu'
                changed['darius']['cover_key'] = None
                library.write_json(library.root()/'installed.json', changed)
                click('#retryConnection');click('[data-page="home"]')
                check('Long names and absent covers preserve layout', "document.documentElement.scrollWidth<=innerWidth && document.querySelector('#homeRecent .recent-title').title.includes('Çok Uzun') && !document.querySelector('#homeRecent [data-mod-id=darius] .recent-art img')")
                capture('home-long-name-no-cover')
                library.write_json(library.root()/'installed.json', {})
                click('#retryConnection')
                check('Empty library has genuine zero counters and actionable onboarding', "document.getElementById('installedCount').textContent==='0' && document.getElementById('activeCount').textContent==='0' && !!document.querySelector('#homeRecent .empty button')")
                capture('home-empty')
                library.write_json(library.root()/'installed.json', saved)
                click('#retryConnection')
                with patch.object(api,'snapshot',side_effect=ValueError('Test: yerel servis çevrimdışı.')):
                    click('#retryConnection')
                    check('Connection failure exposes retry instead of false online state', "!document.getElementById('bridgeNotice').hidden && document.body.classList.contains('bridge-offline')")
                    capture('home-service-error')
                click('#retryConnection')
                result['ok']=True
            except Exception as exc:
                result['error']=str(exc)
                try: capture('failure')
                except Exception: pass
            finally:
                (OUT / 'design-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps({'ok':result['ok'],'layouts':len(result['layouts']),'error':result.get('error')},ensure_ascii=False))
                window.destroy()

        webview.start(run, gui='edgechromium', private_mode=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
