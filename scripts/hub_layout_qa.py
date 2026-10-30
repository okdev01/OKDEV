"""Cross-page geometry and keyboard checks at desktop accessibility zoom levels."""
import json
import time


def run(window, evaluate, tap, cdp, capture, api, root):
    from System import Action
    results = []
    api.count = 36
    pages = ('home', 'library', 'installed', 'profiles', 'guides', 'assistants', 'diagnostics', 'downloads', 'publish')
    for theme in ('dark', 'light'):
        api.preferences['theme'] = theme
        tap('[data-page="library"]'); tap('#refresh')
        for width, height in ((1180, 800), (850, 620)):
            window.resize(width, height)
            for zoom in (1, 1.25, 1.5, 2):
                window.native.webview.Invoke(Action(lambda: setattr(window.native.webview, 'ZoomFactor', zoom)))
                time.sleep(.15)
                for page in pages:
                    # Page navigation is tested by native input elsewhere. Opening
                    # each section directly lets this sweep concentrate on its
                    # keyboard traversal, even when the sidebar scrolls.
                    selector = '#quickImport' if page == 'publish' else f'[data-page="{page}"]'
                    evaluate(f'document.querySelector({json.dumps(selector)}).click()')
                    time.sleep(.12)
                    value = evaluate('''(()=>{
                      const main=document.getElementById('main'), section=document.querySelector('.section:not([hidden])');
                      const overflow=[...section.querySelectorAll('*')].filter(e=>{
                        const s=getComputedStyle(e),r=e.getBoundingClientRect();
                        let visibleRight=r.right;
                        for(let p=e.parentElement;p&&p!==document.body;p=p.parentElement){
                          if(getComputedStyle(p).overflowX!=='visible')visibleRight=Math.min(visibleRight,p.getBoundingClientRect().right);
                        }
                        return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&visibleRight>innerWidth+2;
                      }).map(e=>({tag:e.tagName,id:e.id,classes:e.className,right:e.getBoundingClientRect().right}));
                      return {page:section.id,viewport:[innerWidth,innerHeight],documentWidth:document.documentElement.scrollWidth,overflow};
                    })()''')
                    assert value['page'] == page, (page, value)
                    assert value['documentWidth'] <= value['viewport'][0]+1, (theme, width, zoom, page, value)
                    assert not value['overflow'], (theme, width, zoom, page, value)
                    # The first visible form control receives focus; actual Tab
                    # events then exercise browser scrolling and focus order.
                    evaluate('''(()=>{const section=document.querySelector('.section:not([hidden])'),e=[...section.querySelectorAll('button,input,select,summary,a[href]')].find(e=>!e.disabled&&e.getBoundingClientRect().width>0);e?.focus();})()''')
                    focused = []
                    for _ in range(8):
                        for event in ('keyDown', 'keyUp'):
                            cdp('Input.dispatchKeyEvent', {'type': event, 'key': 'Tab', 'code': 'Tab', 'windowsVirtualKeyCode': 9, 'nativeVirtualKeyCode': 9})
                        time.sleep(.025)
                        item = evaluate('''(()=>{const e=document.activeElement,r=e.getBoundingClientRect(),s=getComputedStyle(e);
                          return {tag:e.tagName,id:e.id,width:r.width,height:r.height,top:r.top,bottom:r.bottom,left:r.left,right:r.right,visibility:s.visibility};})()''')
                        if item['tag'] != 'BODY':
                            assert item['width'] > 0 and item['height'] > 0 and item['visibility'] != 'hidden', ('Hidden keyboard target', item)
                            assert item['right'] > 0 and item['left'] < value['viewport'][0], ('Focus outside horizontal viewport', item)
                            assert item['bottom'] > 0 and item['top'] < value['viewport'][1], ('Focus outside vertical viewport', item)
                        focused.append(item)
                    results.append({'theme': theme, 'size': [width, height], 'zoom': zoom, **value, 'focus': focused})
                    if width == 850 and zoom == 2 and page in ('publish', 'guides', 'profiles', 'downloads'):
                        evaluate('window.scrollTo(0,0)')
                        capture(f'layout-{theme}-{page}-200')
                    (root/'output/ui2-20261030/hub-layout-progress.json').write_text(json.dumps({'running':True,'completed':len(results),'latest':results[-1]},ensure_ascii=False,indent=2),encoding='utf-8')
    window.native.webview.Invoke(Action(lambda: setattr(window.native.webview, 'ZoomFactor', 1)))
    output = {'ok': True, 'cases': len(results), 'keyboard_focus_checks': sum(len(row['focus']) for row in results), 'results': results}
    (root/'output/ui2-20261030/hub-layout.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'ok': True, 'cases': len(results), 'keyboard_focus_checks': output['keyboard_focus_checks']}
