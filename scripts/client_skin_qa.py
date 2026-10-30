"""Native keyboard, focus and viewport checks for the actual skin picker."""
import json
import time


def run(window, evaluate, tap, key, cdp, capture, audit, root):
    from System import Action
    checks=[]
    def check(name, expression):
        assert evaluate(expression), name
        checks.append(name)
    def choose_skins():
        evaluate("document.getElementById('add-custom-mods-dropdown').value='skins';document.getElementById('add-custom-mods-dropdown').dispatchEvent(new Event('change',{bubbles:true}))")
        time.sleep(.15)
    tap('#qa-nav');choose_skins()
    for width,height,zoom in ((860,640,1.5),(500,460,1),(500,460,2)):
        window.resize(width,height)
        window.native.webview.Invoke(Action(lambda:setattr(window.native.webview,'ZoomFactor',zoom)))
        time.sleep(.2)
        check(f'Champion picker fits {width}px at {int(zoom*100)}%',"(()=>{const e=document.querySelector('#champion-selection-flyout .lc-flyout-content'),r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1&&r.top>=0&&r.bottom<=innerHeight+1&&e.scrollWidth<=e.clientWidth+1;})()")
        evaluate("document.getElementById('champion-search-input').value='yas';document.getElementById('champion-search-input').dispatchEvent(new Event('input'))")
        check('Champion search filters the visible list',"document.querySelectorAll('#champions-grid button').length===1&&document.querySelector('#champions-grid button').textContent==='Yasuo'")
        evaluate("document.getElementById('champion-search-input').value='';document.getElementById('champion-search-input').dispatchEvent(new Event('input'))")
    window.native.webview.Invoke(Action(lambda:setattr(window.native.webview,'ZoomFactor',1)))
    window.resize(1100,820);time.sleep(.2)
    audit('champion-picker');capture('champion-picker')
    tap('#champions-grid button:first-child')
    evaluate("document.querySelector('.skin-target').focus()")
    key('Enter',13)
    check('Native Enter selects the base skin',"document.querySelector('.skin-target').getAttribute('aria-pressed')==='true'&&!document.getElementById('skin-selection-confirm').disabled")
    audit('skin-picker');capture('skin-picker')
    tap('.skin-chroma-button');time.sleep(.5)
    check('Opening chromas transfers focus to their visible face',"document.activeElement.classList.contains('skin-card-back-close')&&document.querySelector('.is-flipped .skin-card-front').inert")
    audit('chroma-picker');capture('chroma-picker')
    key('Tab',9);key('Tab',9);key(' ',32)
    check('Native Space selects a chroma',"document.querySelector('.skin-option:last-child').getAttribute('aria-pressed')==='true'")
    tap('.skin-card-back-close');time.sleep(.5)
    check('Returning to base skin restores its chroma opener',"document.activeElement.classList.contains('skin-chroma-button')")
    for width,height in ((860,640),(500,460)):
        window.resize(width,height)
        for zoom in (1,1.5,2):
            window.native.webview.Invoke(Action(lambda:setattr(window.native.webview,'ZoomFactor',zoom)))
            time.sleep(.2)
            value=evaluate('''(()=>{const f=document.querySelector('#skin-selection-flyout .lc-flyout-content'),r=f.getBoundingClientRect(),confirm=document.getElementById('skin-selection-confirm').getBoundingClientRect();return {rect:r.toJSON(),confirm:confirm.toJSON(),viewport:[innerWidth,innerHeight],scrollWidth:f.scrollWidth,clientWidth:f.clientWidth};})()''')
            r=value['rect'];vw,vh=value['viewport']
            assert r['left']>=0 and r['right']<=vw+1 and r['top']>=0 and r['bottom']<=vh+1,value
            assert value['scrollWidth']<=value['clientWidth']+1,value
            check(f'{width}px at {int(zoom*100)}%: confirm remains reachable',"(()=>{const e=document.getElementById('skin-selection-confirm');e.scrollIntoView({block:'nearest'});const r=e.getBoundingClientRect(),h=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);return h===e||e.contains(h)})()")
            capture(f'skins-{width}-{int(zoom*100)}')
    window.native.webview.Invoke(Action(lambda:setattr(window.native.webview,'ZoomFactor',1)))
    window.resize(1100,820);time.sleep(.2)
    tap('#skin-selection-confirm')
    check('Native confirmation sends both selected targets',"(()=>{const r=window.__settingsQa.calls.findLast(c=>c.action==='create'&&c.type==='add-custom-mods-skin-selected');return r.championId===103&&JSON.stringify(r.skinIds)==='[103000,103002]'})()")
    check('Confirm closes the owned selection modal',"!document.getElementById('skin-selection-dialog')")
    choose_skins();tap('#champions-grid button:first-child')
    evaluate("window.__settingsQa.emit('champion-skins-response',{championId:157,championName:'Wrong response',skins:[]})")
    check('Stale champion response is ignored in native host',"document.querySelectorAll('.skin-target').length===2&&document.getElementById('skin-selection-header').textContent.includes('Ahri')")
    key('Escape',27);tap('.okdev-panel-close');time.sleep(.25)
    check('Skin picker leaves no orphaned dialog or listener',"!document.querySelector('[data-okdev-dialog]')&&window.__settingsQa.listenerCount()===0")
    result={'ok':True,'checks':checks,'scope':'Actual plugin and native WebView keyboard; fake League bridge, no game or public network.'}
    (root/'output/ui2-20261030/client-skins.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result
