"""Native WebView2 input and geometry checks for the 2.0 desktop UI.

Uses Chromium's input dispatch into the isolated test WebView. Unlike DOM
click(), these interactions require visible, unobstructed controls. No real
League client, user settings or network service is used.
"""
import hashlib
import json
import time
from pathlib import Path
from unittest.mock import patch


def run(window, evaluate, wait_for, capture, api, root, output=None):
    from System import Func, Object
    from hub import library, preferences
    output = Path(output or root / 'build/hub-polish-check.json')
    report = {'ok': False, 'checks': [], 'errors': [], 'accessibility': [],
              'scope': 'Isolated real WebView2; CDP mouse/key input, real local Python bridge; no game or public network.',
              'source_sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                               for name in ('hub/web/app.js', 'hub/web/index.html', 'hub/web/app.css', 'hub/preferences.py')}}

    def check(name, expression):
        assert evaluate(expression), name
        report['checks'].append(name)

    def cdp(method, params):
        task = window.native.webview.Invoke(Func[Object](lambda:
            window.native.webview.CoreWebView2.CallDevToolsProtocolMethodAsync(method, json.dumps(params))))
        assert task.Wait(10000), 'CDP input timeout'
        return task.Result

    def key(name, code=None, vk=None, modifiers=0):
        for event in ('keyDown', 'keyUp'):
            values = {'type': event, 'key': name, 'code': code or name, 'modifiers': modifiers}
            if vk is not None:
                values.update(windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)
            if name == 'Enter' and event == 'keyDown':
                values.update(text='\r', unmodifiedText='\r')
            cdp('Input.dispatchKeyEvent', values)
        time.sleep(.05)

    def type_text(text):
        cdp('Input.insertText', {'text': text})
        time.sleep(.08)

    def tap(selector):
        encoded = json.dumps(selector)
        evaluate(f"document.querySelector({encoded})?.scrollIntoView({{block:'center',inline:'nearest',behavior:'instant'}})")
        time.sleep(.06)
        bounds = evaluate(f"""(()=>{{const e=document.querySelector({encoded});if(!e)return null;
          const r=e.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2;
          const top=document.elementFromPoint(x,y);
          return {{x,y,width:r.width,height:r.height,disabled:!!e.disabled,
            visible:getComputedStyle(e).visibility!=='hidden',hit:top===e||e.contains(top),
            blocker:top?.outerHTML?.slice(0,180)}};}})()""")
        assert bounds and bounds['width'] > 0 and bounds['height'] > 0 and bounds['visible'], f'Invisible control: {selector}'
        assert not bounds['disabled'], f'Disabled control: {selector}'
        assert bounds['hit'], f'Obstructed control: {selector}: {bounds}'
        for event in ('mousePressed', 'mouseReleased'):
            cdp('Input.dispatchMouseEvent', {'type': event, 'x': bounds['x'], 'y': bounds['y'], 'button': 'left', 'clickCount': 1})
        time.sleep(.08)
        wait_for("document.getElementById('main').getAttribute('aria-busy') === 'false'")

    def clear_toast():
        if evaluate("!!document.querySelector('#status .dismiss-notice')"):
            tap('#status .dismiss-notice')

    def audit(label):
        evaluate("window.__polishAxe=null;axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}},(e,r)=>window.__polishAxe=e?{error:String(e)}:{violations:r.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),incomplete:r.incomplete.map(v=>({id:v.id,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}))})")
        wait_for('window.__polishAxe !== null')
        result = evaluate('window.__polishAxe')
        if result.get('incomplete'):
            result['geometry_debug'] = evaluate("""window.__polishAxe.incomplete.flatMap(i=>i.nodes.map(n=>{const e=document.querySelector(n.target[0]);if(!e)return {};const r=e.getBoundingClientRect(),s=getComputedStyle(e);const range=document.createRange();range.selectNodeContents(e);return {target:n.target,html:e.outerHTML,rect:r.toJSON(),color:s.color,background:s.backgroundColor,opacity:s.opacity,lines:Array.from(range.getClientRects()).map(x=>({rect:x.toJSON(),hit:document.elementFromPoint(x.left+x.width/2,x.top+x.height/2)?.outerHTML.slice(0,200)}))};}))""")
        # Reviewed in the captured native dialog: axe reports overlap for this
        # two-line paragraph although its own opaque background and all text
        # hit points are unobstructed. Keep the raw finding and require an
        # independent, numeric contrast + geometry check; do not waive other
        # incomplete results or any actual violation.
        reviewed = True
        for item in result.get('incomplete', []):
            for node in item['nodes']:
                selector = node['target'][0]
                if item['id'] != 'color-contrast' or selector != '#createProfileDialog > p:nth-child(3)' or 'partially overlaps' not in node['summary']:
                    reviewed = False
                    continue
                proof = evaluate("""(()=>{const e=document.querySelector('#createProfileDialog > p:nth-child(3)'),s=getComputedStyle(e);
                  const rgb=v=>v.match(/[\\d.]+/g).map(Number),fg=rgb(s.color),bg=rgb(s.backgroundColor);
                  const lum=c=>c.slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
                  const a=lum(fg),b=lum(bg),ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05),range=document.createRange();range.selectNodeContents(e);
                  const clear=[...range.getClientRects()].every(r=>[r.left+2,r.left+r.width/2,r.right-2].every(x=>{const hit=document.elementFromPoint(x,r.top+r.height/2);return hit===e||e.contains(hit);}));
                  return {ratio,unobstructed:clear,opaque:(bg.length===3||bg[3]===1)&&s.opacity==='1',background:s.backgroundColor,color:s.color};})()""")
                result.setdefault('reviewed_findings', []).append({'target': selector, **proof})
                reviewed = reviewed and proof['ratio'] >= 4.5 and proof['opaque'] and proof['unobstructed']
        report['accessibility'].append({'state': label, **result})
        assert not result.get('error') and not result['violations'] and reviewed, f'{label}: {result}'

    try:
        evaluate((root / 'test/ui/node_modules/axe-core/axe.min.js').read_text(encoding='utf-8'))
        window.resize(1180, 800)
        clear_toast()
        tap('[data-page="assistants"]')
        tap('#settingsTab-appearance')
        check('Switch geometry is a 42x24 toggle, not a round button', "(()=>{const r=document.getElementById('dataSaver').getBoundingClientRect();return r.width===42&&r.height===24;})()")
        key('ArrowRight', vk=39)
        check('Native keyboard selects the next settings tab', "document.activeElement.id==='settingsTab-play' && !document.getElementById('settingsPanel-play').hidden && document.getElementById('settingsPanel-appearance').hidden")
        capture('polish-settings-play')
        audit('settings-play')
        key('End', vk=35)
        check('Native End key selects the last settings tab', "document.activeElement.id==='settingsTab-about' && !document.getElementById('settingsPanel-about').hidden")
        capture('polish-settings-about')
        key('Home', vk=36)
        check('Native Home key returns to appearance settings', "document.activeElement.id==='settingsTab-appearance'")

        tap('[data-page="installed"]')
        evaluate("document.getElementById('installedSearch').value='';document.getElementById('installedCategory').value='';document.getElementById('installedFilter').value='all';document.getElementById('installedSearch').dispatchEvent(new Event('input'))")
        tap('[data-view-owner="installed"][data-view-mode="list"]')
        assert preferences.get()['mod_view'] == 'list'
        report['checks'].append('Native list switch persists through the real Python bridge')
        check('Dense list rows use the available width', "(()=>{const r=document.querySelector('#installedGrid .card').getBoundingClientRect();return r.width>600&&r.height<190;})()")
        check('List switch keeps keyboard focus after saving', "document.activeElement.dataset.viewMode==='list'")
        capture('polish-installed-list')
        audit('installed-list')
        tap('#installedSearch');type_text('QA Ahri')
        check('Native typing filters the installed list', "document.querySelectorAll('#installedGrid .card').length===1&&document.getElementById('installedChips').children.length===1")
        tap('#installedChips button')
        check('Removing the search chip restores input focus and results', "document.activeElement.id==='installedSearch'&&document.querySelectorAll('#installedGrid .card').length===2")
        tap('#selectionMenu summary');tap('#selectVisible')
        check('Selecting visible rows opens contextual actions', "!document.getElementById('bulkToolbar').hidden&&document.querySelectorAll('#installedGrid .bulk-selected').length===2")
        capture('polish-bulk-selection')
        tap('#clearBulk')
        check('Clearing selection removes contextual action bar', "document.getElementById('bulkToolbar').hidden")
        tap('[data-view-owner="installed"][data-view-mode="grid"]')

        tap('[data-page="profiles"]');tap('#newProfile')
        check('Create-profile dialog places native focus in the name field', "document.getElementById('createProfileDialog').open&&document.activeElement.id==='profileName'")
        capture('polish-profile-create')
        audit('create-profile-dialog')
        key('Escape', vk=27)
        check('Native Escape closes profile dialog and restores opener focus', "!document.getElementById('createProfileDialog').open&&document.activeElement.id==='newProfile'")
        tap('#newProfile');type_text('Gece oyunu')
        key('Enter', vk=13)
        wait_for("!document.getElementById('createProfileDialog').open")
        check('Native Enter saves the profile through the actual bridge', "document.getElementById('profileCards').textContent.includes('Gece oyunu')")
        clear_toast()
        tap('#newProfile');type_text('Hata senaryosu')
        with patch.object(api, 'save_profile', return_value={'ok':False,'error':'QA: Kayıt yazılamadı.'}):
            tap('#createProfileDialog button[type="submit"]')
        check('Backend errors remain visible inside the native modal layer', "document.getElementById('createProfileDialog').open&&document.querySelector('#createProfileDialog .dialog-feedback.error')?.textContent.includes('Kayıt yazılamadı')")
        capture('polish-profile-error')
        audit('profile-error-dialog')
        key('Escape', vk=27);clear_toast()

        tap('[data-page="installed"]')
        tap('#installedGrid .card-title-button')
        check('Card title opens the real detail dialog', "document.getElementById('detailDialog').open")
        capture('polish-mod-detail')
        audit('mod-detail-dialog')
        key('Escape', vk=27)
        check('Detail close restores focus to the originating card', "document.activeElement.classList.contains('card-title-button')")
        key('k', code='KeyK', vk=75, modifiers=2)
        check('Native Ctrl+K opens the command palette', "document.getElementById('commandDialog').open&&document.activeElement.id==='commandSearch'")
        type_text('ayarlar')
        key('Enter', vk=13)
        wait_for("!document.getElementById('assistants').hidden")
        check('Native command search opens the selected page', "document.activeElement.id==='title'&&document.getElementById('commandDialog').open===false")

        # Check all settings panels in both themes, including the long draft
        # editor. A page-level scan of only the default tab misses these.
        for theme in ('dark', 'light'):
            preferences.update({'theme': theme})
            api._window.evaluate_js("document.getElementById('retryConnection').click()")
            wait_for("document.documentElement.dataset.theme === " + json.dumps(theme))
            clear_toast()
            for panel in ('appearance', 'play', 'about'):
                tap('#settingsTab-' + panel)
                audit(theme + '-settings-' + panel)
                capture('polish-' + theme + '-settings-' + panel)
        preferences.update({'theme':'dark','mod_view':'grid'})
        evaluate("document.getElementById('retryConnection').click()")
        wait_for("document.documentElement.dataset.theme==='dark'")
        clear_toast()
        tap('#settingsTab-appearance')
        tap('[data-page="home"]')
        check('Native input journeys produce no JavaScript errors', 'window.__qaErrors.length===0')
        report['ok'] = True
    except Exception as exc:
        report['errors'].append(str(exc))
        raise
    finally:
        output.parent.mkdir(exist_ok=True, parents=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
