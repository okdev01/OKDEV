"""Long-running native input checks for the isolated settings-plugin host."""
import hashlib
import json
import os
from pathlib import Path
import time


def run(window, evaluate, tap, key, cdp, capture, root, duration):
    import psutil
    root=Path(root)
    target=root/'output/ui2-20261030/client-endurance.json'
    report={'ok':False,'running':True,'cycles':0,'errors':[],'samples':[],
            'scope':'Real WebView2 input with the actual settings plugin; isolated fake League bridge, CSP blocks external network, no user-data writes.',
            'source_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in (
                'Pengu Loader/plugins/OKDEV-SettingsPanel/index.js','Pengu Loader/plugins/OKDEV-I18n/locales/tr.json')}}
    started=time.monotonic()
    def write():
        report['elapsed_seconds']=round(time.monotonic()-started,2)
        temporary=target.with_suffix('.tmp')
        temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(target)
    def require(expression,label):
        assert evaluate(expression),label
    try:
        write()
        while time.monotonic()-started<duration:
            cycle_started=time.monotonic()
            cycle=report['cycles']+1
            if cycle%12==0:
                window.resize(640,560)
            elif cycle%12==1:
                window.resize(1100,820)
            tap('#qa-nav')
            require("window.__settingsQa.listenerCount()===5",'Panel listener count grew after opening')
            tap('#threshold-slider');key('Home',36);key('ArrowRight',39)
            require("document.getElementById('threshold-value').textContent==='0.31 s'",'Range stopped following native keys')
            evaluate(f'window.__settingsQa.failSave={str(cycle%3==0).lower()}')
            tap('#save-button')
            require("!document.getElementById('save-button').disabled",'Save remained stuck after its response')
            if cycle%3==0:
                require("document.getElementById('okdev-settings-feedback').textContent.includes('Disk full')",'Save error disappeared')
                evaluate('window.__settingsQa.failSave=false')
                tap('#save-button')
            tap('#manage-custom-mods-dropdown');key('Home',36);key('ArrowDown',40);key('ArrowDown',40);key('Enter',13)
            require("document.querySelectorAll('#category-mods-manage-dialog .mod-manage-row').length===2",'Management list did not recover')
            tap('#category-mods-manage-dialog .mod-rename-button');key('Escape',27)
            require("document.activeElement.matches('.mod-rename-button')",'Nested focus restoration failed')
            tap('#category-mods-manage-dialog .mod-delete-button');key('Escape',27);key('Escape',27)
            require("document.activeElement.id==='manage-custom-mods-dropdown'",'Management did not restore its opener')
            if cycle%5==0:
                tap('#troubleshoot-button');key('Escape',27)
                require("document.activeElement.id==='troubleshoot-button'",'Troubleshooting did not restore its opener')
            if cycle%10==0:
                evaluate("document.getElementById('game-path-input').value='C:/QA unsaved draft';document.getElementById('game-path-input').dispatchEvent(new Event('input',{bubbles:true}));window.dispatchEvent(new Event('okdev-i18n-changed'));window.__qaInlineAssets()")
                time.sleep(.2)
                require("document.getElementById('game-path-input').value==='C:/QA unsaved draft'",'Language rebuild lost the draft')
                require("window.__settingsQa.listenerCount()===5",'Language rebuild leaked listeners')
            if cycle%40==0: capture(f'endurance-{cycle}')
            tap('.okdev-panel-close');time.sleep(.25)
            require("!document.getElementById('okdev-settings-panel')",'Closed panel remained attached')
            require("window.__settingsQa.listenerCount()===0",'Closing leaked global listeners')
            require("window.__settingsQa.errors.length===0",'Plugin raised an unhandled error')
            # Keep the fixture's recording bounded; production has no such array.
            evaluate('window.__settingsQa.calls.length=0')
            sample={'cycle':cycle,'dom_nodes':evaluate('document.querySelectorAll("*").length'),
                    'heap':cdp('Runtime.getHeapUsage',{})}
            processes=[psutil.Process(os.getpid())]
            processes+=processes[0].children(recursive=True)
            sample['rss_bytes']=0;sample['handles']=0
            for process in processes:
                try:
                    sample['rss_bytes']+=process.memory_info().rss
                    sample['handles']+=process.num_handles()
                except (psutil.NoSuchProcess,psutil.AccessDenied): pass
            report['samples'].append(sample)
            report['cycles']=cycle
            write()
            # Dwell between interactions like a person keeping the panel open
            # over a session; timers/observers remain live throughout the run.
            remaining=min(15-(time.monotonic()-cycle_started),duration-(time.monotonic()-started))
            if remaining>0: time.sleep(remaining)
        report['ok']=True
    except Exception as error:
        report['errors'].append(f'{type(error).__name__}: {error}')
        raise
    finally:
        report['running']=False
        write()
    return report
