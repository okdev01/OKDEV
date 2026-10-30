"""Render the real settings plugin in an isolated, offline WebView2 host.

The fixture supplies only the League bridge contract. This is not a live
League-client test; CSP blocks all network requests and no files are modified.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', action='store_true')
    parser.add_argument('--soak-seconds', type=int, default=0)
    parser.add_argument('--locales', action='store_true')
    parser.add_argument('--skins', action='store_true')
    args = parser.parse_args()
    import webview
    out = ROOT / 'output/ui2-20261030'
    source_name = 'Pengu Loader/plugins/OKDEV-SettingsPanel/index.js'
    if args.baseline:
        with zipfile.ZipFile(out / 'source-before.zip') as archive:
            source = archive.read(source_name).decode('utf-8')
    else:
        source = (ROOT / source_name).read_text(encoding='utf-8')
    locale = json.loads((ROOT / 'Pengu Loader/plugins/OKDEV-I18n/locales/tr.json').read_text(encoding='utf-8'))
    fonts = {}
    for name in ('BeaufortforLOL-Regular.ttf', 'BeaufortforLOL-Bold.ttf', 'tooltip.png'):
        mime = 'image/png' if name.endswith('.png') else 'font/ttf'
        fonts[name] = 'data:' + mime + ';base64,' + base64.b64encode((ROOT / 'assets' / name).read_bytes()).decode()
    fixture = (ROOT / 'test/fixtures/client_settings.js').read_text(encoding='utf-8')
    script = lambda value: '<script>' + value.replace('</script', '<\\/script') + '</script>'
    html = '''<!doctype html><html lang="tr"><head><meta charset="utf-8">
      <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'">
      <title>OKDEV istemci ayarları • Çevrimdışı test</title>
      <style>html,body{margin:0;width:100%;height:100%;background:#09111b;color:#dce6f4;font:14px 'Segoe UI',sans-serif;overflow:hidden}
      #qa-nav{position:absolute;left:300px;top:14px;padding:10px 16px;border:1px solid #695625;border-radius:4px;background:#152231;cursor:pointer}
      #qa-label{position:absolute;right:24px;top:24px;color:#9eacc0}
      lc-flyout-content{display:block}button,input,select{box-sizing:border-box}
      @media(max-width:600px){#qa-label{display:none}}
      </style></head><body><main aria-label="Çevrimdışı istemci testi"><lol-uikit-navigation-item id="qa-nav" tabindex="0" class="menu_item_Golden OKDEV">OKDEV</lol-uikit-navigation-item>
      <span id="qa-label">İstemci paneli · Çevrimdışı test</span></main>'''
    html += script('window.__qaLocale=' + json.dumps(locale) + ';') + script(fixture) + script(source)
    html += script('''window.__qaAssets=''' + json.dumps(fonts) + r''';
      document.getElementById('qa-nav').addEventListener('click',()=>window.__settingsQa.open());
      window.__qaInlineAssets=()=>{
        const style=document.getElementById('okdev-settings-panel-css');
        if(style)style.textContent=style.textContent.replace(/http:\/\/127\.0\.0\.1:\d+\/asset\/([\w.-]+)/g,(url,name)=>window.__qaAssets[name]||url);
      };''') + '</body></html>'
    report = {'ok':False, 'checks':[], 'errors':[], 'accessibility':[], 'geometry':[],
              'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
              'scope':'Actual settings plugin in isolated WebView2; fake bridge; no live League, no external network or user-data writes.'}
    suffix = 'baseline' if args.baseline else 'current'
    window = webview.create_window('OKDEV • İstemci paneli testi', html=html, width=1100, height=820, min_size=(480,400))
    def evaluate(code): return window.evaluate_js(code)
    def wait(expression, timeout=10):
        until = time.monotonic()+timeout
        while time.monotonic()<until:
            if evaluate(expression): return
            time.sleep(.08)
        raise AssertionError('Timed out: '+expression)
    def check(name, expression):
        assert evaluate(expression), name
        report['checks'].append(name)
    def cdp(method, params):
        from System import Func, Object
        task=window.native.webview.Invoke(Func[Object](lambda:window.native.webview.CoreWebView2.CallDevToolsProtocolMethodAsync(method,json.dumps(params))))
        assert task.Wait(10000)
        return json.loads(task.Result)
    def key(name, vk, modifiers=0):
        for kind in ('keyDown','keyUp'):
            values={'type':kind,'key':name,'windowsVirtualKeyCode':vk,'nativeVirtualKeyCode':vk,'modifiers':modifiers}
            if name=='Enter' and kind=='keyDown': values.update(text='\r',unmodifiedText='\r')
            cdp('Input.dispatchKeyEvent',values)
        time.sleep(.08)
    def tap(selector):
        encoded=json.dumps(selector)
        evaluate(f'document.querySelector({encoded}).scrollIntoView({{block:"center",behavior:"instant"}})')
        point=evaluate(f'''(()=>{{const e=document.querySelector({encoded}),r=e.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2,h=document.elementFromPoint(x,y);
          return {{x,y,visible:r.width>0&&r.height>0&&getComputedStyle(e).visibility!=='hidden',hit:e===h||e.contains(h),disabled:!!e.disabled}};}})()''')
        assert point['visible'] and point['hit'] and not point['disabled'], (selector,point)
        for kind in ('mousePressed','mouseReleased'):
            cdp('Input.dispatchMouseEvent',{'type':kind,'x':point['x'],'y':point['y'],'button':'left','clickCount':1})
        time.sleep(.12)
    def capture(name):
        from System import Func,Object
        from System.IO import FileStream,FileMode
        from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat
        folder=out/'screenshots';folder.mkdir(exist_ok=True)
        stream=FileStream(str(folder/f'client-{suffix}-{name}.png'),FileMode.Create)
        try:
            task=window.native.webview.Invoke(Func[Object](lambda:window.native.webview.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png,stream)))
            assert task.Wait(10000)
        finally: stream.Dispose()
    def audit(label):
        evaluate("window.__qaAxe=null;axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}},(e,r)=>window.__qaAxe=e?{error:String(e)}:{violations:r.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),incomplete:r.incomplete.map(v=>({id:v.id,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}))})")
        wait('window.__qaAxe!==null')
        result=evaluate('window.__qaAxe')
        reviewed=True
        for item in result.get('incomplete',[]):
            for node in item['nodes']:
                selector=node['target'][0]
                reviewed_targets = {'#delete-mod-confirm-dialog > .flyout > div:nth-child(1)'}
                if label == 'chroma-picker':
                    reviewed_targets.add('.skin-card-back-header > span')
                if item['id']!='color-contrast' or selector not in reviewed_targets or 'partially overlaps' not in node['summary']:
                    reviewed=False
                    continue
                # Native screenshots reviewed: the opaque confirmation paragraph
                # and transformed chroma header are unobscured. Keep the raw finding and independently verify
                # contrast and hit testing at three points on every text line.
                proof=evaluate('''(()=>{const e=document.querySelector(REVIEW_SELECTOR),s=getComputedStyle(e);
                  const rgb=v=>v.match(/[\\d.]+/g).map(Number),fg=rgb(s.color),bg=rgb(s.backgroundColor);
                  const lum=c=>c.slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
                  const a=lum(fg),b=lum(bg),range=document.createRange();range.selectNodeContents(e);
                  return {ratio:(Math.max(a,b)+.05)/(Math.min(a,b)+.05),opaque:s.opacity==='1'&&(bg.length===3||bg[3]===1),
                  unobscured:[...range.getClientRects()].every(r=>[r.left+2,r.left+r.width/2,r.right-2].every(x=>{const h=document.elementFromPoint(x,r.top+r.height/2);return h===e||e.contains(h)}))};})()'''.replace('REVIEW_SELECTOR', json.dumps(selector)))
                result.setdefault('reviewed_findings',[]).append({'target':selector,**proof})
                reviewed=reviewed and proof['ratio']>=4.5 and proof['opaque'] and proof['unobscured']
        report['accessibility'].append({'state':label,**result})
        assert not result.get('error') and not result['violations'] and reviewed, (label,result)
    def geometry(label):
        value=evaluate('''(()=>{const e=document.getElementById('okdev-settings-flyout'),r=e.getBoundingClientRect(),c=e.querySelector('lc-flyout-content,.lc-flyout-content'),s=document.getElementById('threshold-slider').getBoundingClientRect();
          return {window:[innerWidth,innerHeight],frame:r.toJSON(),content:c.getBoundingClientRect().toJSON(),scrollWidth:c.scrollWidth,clientWidth:c.clientWidth,range:s.toJSON(),listeners:window.__settingsQa.listenerCount()};})()''')
        report['geometry'].append({'state':label,**value})
        return value
    def exercise():
        try:
            wait("!!document.getElementById('okdev-settings-panel-css')")
            evaluate('window.__qaInlineAssets()')
            tap('#qa-nav');wait("!!document.getElementById('save-button')")
            time.sleep(.25)
            geometry('initial');capture('initial')
            if args.baseline:
                report['ok']=True
                return
            evaluate((ROOT/'test/ui/node_modules/axe-core/axe.min.js').read_text(encoding='utf-8'))
            audit('settings')
            tap('#threshold-slider');key('End',35)
            check('Keyboard range reaches its maximum',"document.getElementById('threshold-value').textContent==='2.00 s'")
            check('Range thumb remains inside its responsive track',"(()=>{const e=document.querySelector('#okdev-settings-flyout .lol-uikit-slider-button').getBoundingClientRect(),r=document.getElementById('threshold-slider').getBoundingClientRect();return e.left>=r.left-1&&e.right<=r.right+1;})()")
            tap('#save-button')
            check('Save acknowledges the real plugin request',"document.getElementById('okdev-settings-feedback').textContent===window.OKDEVI18n.t('Saved!')")
            evaluate('window.__settingsQa.failSave=true')
            tap('#save-button');capture('save-error');audit('save-error')
            check('Save failure is visible and recoverable',"document.getElementById('okdev-settings-feedback').textContent.includes('Disk full')&&!document.getElementById('save-button').disabled")
            evaluate('window.__settingsQa.failSave=false')
            tap('#manage-custom-mods-dropdown');key('Home',36);key('ArrowDown',40);key('ArrowDown',40);key('Enter',13)
            wait("!!document.querySelector('#category-mods-manage-dialog .mod-rename-button')")
            capture('manage');audit('manage')
            tap('#category-mods-manage-dialog .mod-rename-button');wait("!!document.getElementById('rename-mod-dialog')")
            capture('rename');audit('rename')
            key('Escape',27)
            check('Escape closes only the top dialog',"!document.getElementById('rename-mod-dialog')&&!!document.getElementById('category-mods-manage-dialog')")
            check('Nested dismissal restores the rename action',"document.activeElement.matches('.mod-rename-button')")
            tap('#category-mods-manage-dialog .mod-delete-button');capture('delete');audit('delete')
            key('Escape',27);key('Escape',27)
            check('Closing management restores its opener',"document.activeElement.id==='manage-custom-mods-dropdown'")
            tap('#troubleshoot-button');capture('diagnostics-empty');audit('diagnostics-empty');key('Escape',27)
            evaluate("window.__settingsQa.diagnosticErrors=Array.from({length:12},(_,i)=>({key:'qa-'+i,code:'LTK_PATCHER_FAILED',text:'QA failure',detail:'Uzun yerel hata ayrıntısı '+('A'.repeat(250))}))")
            window.resize(500,460);time.sleep(.2)
            tap('#troubleshoot-button');capture('diagnostics-small');audit('diagnostics-small')
            check('Troubleshooting fits a small viewport',"(()=>{const p=document.getElementById('okdev-diagnostics-body').parentElement,r=p.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight&&r.left>=0&&r.right<=innerWidth&&p.scrollWidth<=p.clientWidth;})()")
            key('Escape',27);evaluate('window.__settingsQa.diagnosticErrors=[]')
            for width,height in ((860,640),(640,520),(500,460),(1100,820)):
                window.resize(width,height);time.sleep(.25)
                value=geometry(f'{width}x{height}')
                r=value['content'];vw,vh=value['window']
                assert r['left']>=0 and r['right']<=vw+1 and r['top']>=0 and r['bottom']<=vh+1, value
                assert value['scrollWidth']<=value['clientWidth']+1,value
                tap('#save-button');capture(f'{width}x{height}')
                report['checks'].append(f'Settings remain inside {width}x{height} and Save is reachable')
                check(f'Close remains visible after scrolling at {width}x{height}',"(()=>{const e=document.querySelector('.okdev-panel-close'),r=e.getBoundingClientRect(),h=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);return h===e||e.contains(h)})()")
            from System import Action
            for zoom in (1.25,1.5,2.0):
                window.native.webview.Invoke(Action(lambda:setattr(window.native.webview,'ZoomFactor',zoom)))
                time.sleep(.25)
                tap('#save-button');capture(f'zoom-{int(zoom*100)}')
                value=geometry(f'zoom-{zoom}');r=value['content'];vw,vh=value['window']
                assert 0<=r['left'] and r['right']<=vw+1 and 0<=r['top'] and r['bottom']<=vh+1,value
                report['checks'].append(f'Settings and Save remain usable at {int(zoom*100)}% zoom')
            window.native.webview.Invoke(Action(lambda:setattr(window.native.webview,'ZoomFactor',1.0)))
            tap('.okdev-panel-close');time.sleep(.25)
            check('Closing releases resize and tooltip listeners',"window.__settingsQa.listenerCount()===0")
            check('No unhandled plugin script errors',"window.__settingsQa.errors.length===0")
            if args.skins:
                from client_skin_qa import run
                report['skins']=run(window,evaluate,tap,key,cdp,capture,audit,ROOT)
            if args.locales:
                from client_locale_qa import run
                report['locales']=run(window,evaluate,tap,key,capture,audit,ROOT)
            if args.soak_seconds:
                from client_settings_soak import run
                report['endurance']=run(window,evaluate,tap,key,cdp,capture,ROOT,args.soak_seconds)
            report['ok']=True
        except Exception as error:
            report['errors'].append(f'{type(error).__name__}: {error}')
            try: capture('failure')
            except Exception: pass
        finally:
            report['plugin_errors']=evaluate('window.__settingsQa?.errors||[]')
            (out/f'client-native-{suffix}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            window.destroy()
    webview.start(exercise,gui='edgechromium',private_mode=True)
    print(json.dumps(report,ensure_ascii=False))
    return 0 if report['ok'] else 1


if __name__=='__main__': raise SystemExit(main())
