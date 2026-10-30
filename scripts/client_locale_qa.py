"""Native rendering sweep of every shipped settings-panel translation."""
import hashlib
import json
from pathlib import Path
import time


def run(window,evaluate,tap,key,capture,audit,root):
    root=Path(root)
    from utils.core.i18n import LANGUAGES
    catalog_dir=root/'Pengu Loader/plugins/OKDEV-I18n/locales'
    results=[]
    window.resize(860,640)
    for code in LANGUAGES:
        catalog={} if code=='en' else json.loads((catalog_dir/f'{code}.json').read_text(encoding='utf-8'))
        evaluate('window.__qaLocale='+json.dumps(catalog)+';window.OKDEVI18n.languages='+json.dumps(LANGUAGES)+';window.OKDEVI18n.language='+json.dumps(code)+';window.OKDEVI18n.setting='+json.dumps(code)+';window.OKDEVI18n.direction='+json.dumps('rtl' if code=='ar' else 'ltr')+';')
        tap('#qa-nav')
        time.sleep(.12)
        box=evaluate('''(()=>{const c=document.querySelector('#okdev-settings-flyout lc-flyout-content'),r=c.getBoundingClientRect(),title=document.querySelector('#okdev-settings-flyout .settings-title'),close=document.querySelector('.okdev-panel-close');
          return {scrollWidth:c.scrollWidth,clientWidth:c.clientWidth,rect:r.toJSON(),title:title.getBoundingClientRect().toJSON(),close:close.getBoundingClientRect().toJSON(),viewport:[innerWidth,innerHeight],direction:document.getElementById('okdev-settings-flyout').dir};})()''')
        assert box['scrollWidth']<=box['clientWidth']+1,(code,'horizontal overflow',box)
        assert box['rect']['bottom']<=box['viewport'][1]+1,(code,'vertical overflow',box)
        a,b=box['title'],box['close']
        assert min(a['right'],b['right'])<=max(a['left'],b['left']),(code,'title overlaps close',box)
        assert box['direction']==('rtl' if code=='ar' else 'ltr'),(code,'text direction')
        assert evaluate("[...document.querySelectorAll('.lol-settings-slider')].every(e=>getComputedStyle(e).direction==='ltr')"),(code,'range direction')
        tap('#save-button')
        assert evaluate("document.getElementById('okdev-settings-feedback').textContent===window.OKDEVI18n.t('Saved!')"),(code,'save acknowledgement')
        # Audit all content in a tall viewport; a sticky header intentionally
        # covers scrolled-out text in the constrained-geometry pass above.
        window.resize(1100,1000)
        time.sleep(.15)
        evaluate("document.querySelector('#okdev-settings-flyout lc-flyout-content').scrollTop=0")
        audit('locale-'+code)
        if code in ('tr','de','el','ar','ja','th','zh_CN'):
            evaluate("document.querySelector('#okdev-settings-flyout lc-flyout-content').scrollTop=0")
            capture('locale-'+code)
        tap('.okdev-panel-close');time.sleep(.24)
        window.resize(860,640)
        results.append({'language':code,'geometry':box,'ok':True,'catalog_sha256':hashlib.sha256(json.dumps(catalog,sort_keys=True,ensure_ascii=False).encode()).hexdigest()})
    (root/'output/ui2-20261030/client-locales.json').write_text(json.dumps({'ok':True,'results':results},ensure_ascii=False,indent=2),encoding='utf-8')
    return results
