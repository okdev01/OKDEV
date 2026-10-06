"""Long-running native WebView exercise, used only by isolated QA fixtures."""
import hashlib
import json
import os
from pathlib import Path
import time

import psutil


def run(window, evaluate, click, wait_for, root, duration, interval=15, output=None):
    output = Path(output) if output else root / 'build/hub-webview-endurance.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {'ok': False, 'running': True, 'cycles': 0, 'samples': [], 'errors': [],
        'scope': 'Real isolated WebView2 window, bridge, preferences, filters and focus. No game started.',
        'source_sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in ('hub/web/app.js', 'hub/web/index.html', 'hub/web/app.css', 'hub/desktop.py')}}
    started = time.monotonic()
    process = psutil.Process(os.getpid())
    def persist():
        report['elapsed_seconds'] = round(time.monotonic() - started, 2)
        temporary = output.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, indent=2), encoding='utf-8')
        temporary.replace(output)
    def resources():
        rss, handles, threads = 0, 0, 0
        for child in [process, *process.children(recursive=True)]:
            try:
                rss += child.memory_info().rss
                handles += child.num_handles()
                threads += child.num_threads()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return {'rss_bytes': rss, 'handles': handles, 'threads': threads}
    pages = ('home', 'library', 'installed', 'profiles', 'guides', 'assistants', 'diagnostics', 'downloads')
    persist()
    try:
        while time.monotonic() - started < duration:
            cycle = report['cycles']
            click('[data-page="installed"]')
            evaluate("document.getElementById('installedCategory').value='';document.getElementById('installedFilter').value='all';document.getElementById('installedSearch').value='';document.getElementById('installedSearch').dispatchEvent(new Event('input'))")
            evaluate("document.querySelector('#installedGrid .favorite').focus();window.__soakFocus=document.activeElement.closest('.card').dataset.modId")
            click('#installedGrid .favorite')
            assert evaluate("document.activeElement.classList.contains('favorite') && document.activeElement.closest('.card').dataset.modId === window.__soakFocus"), 'Focus lost after bridge action'
            click('[data-page="library"]')
            category = ('', 'skins', 'ui', 'maps', 'fonts', 'announcers')[cycle % 6]
            evaluate("document.getElementById('categoryFilter').value=" + json.dumps(category) + ";document.getElementById('categoryFilter').dispatchEvent(new Event('change'))")
            click('[data-page="assistants"]')
            theme = 'light' if cycle % 2 else 'dark'
            evaluate("document.getElementById('theme').value=" + json.dumps(theme) + ";document.getElementById('theme').dispatchEvent(new Event('change'))")
            wait_for("document.getElementById('main').getAttribute('aria-busy') === 'false'")
            assert evaluate('document.documentElement.dataset.theme === ' + json.dumps(theme)), 'Theme write not reflected'
            if cycle % 6 == 0:
                width, height = ((850, 620), (1180, 800), (1600, 950))[(cycle // 6) % 3]
                window.resize(width, height)
                time.sleep(.2)
            if cycle % 12 == 0:
                click('#quickImport')
                evaluate("document.getElementById('modForm').dispatchEvent(new Event('submit',{cancelable:true}))")
                wait_for("document.getElementById('importReplaceDialog').open")
                assert evaluate("document.getElementById('importReplaceDialog').contains(document.activeElement)"), 'Replacement dialog focus escaped'
                click('#importReplaceDialog button:not(.primary)')
                assert evaluate("!document.getElementById('importReplaceDialog').open"), 'Cancelled preview stayed open'
            click('[data-page="' + pages[cycle % len(pages)] + '"]')
            assert evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Horizontal overflow'
            assert evaluate('window.__qaErrors.length === 0'), 'Uncaught JavaScript error'
            nodes = evaluate('document.getElementsByTagName("*").length')
            assert nodes < 10000, 'DOM grew beyond bounded fixture size'
            report['cycles'] += 1
            report['samples'].append({'cycle': report['cycles'], 'dom_nodes': nodes, **resources()})
            persist()
            time.sleep(min(interval, max(0, duration - (time.monotonic() - started))))
        # Ignore browser warmup and short-lived render processes. Compare a
        # window of samples rather than treating one transient peak as a leak.
        samples = report['samples']
        if len(samples) >= 40:
            baseline = samples[10:20]
            final = samples[-10:]
            for key, maximum_growth in (('rss_bytes', 256 * 1024**2), ('handles', 500), ('threads', 50)):
                growth = sum(s[key] for s in final) / len(final) - sum(s[key] for s in baseline) / len(baseline)
                report[key + '_growth'] = round(growth)
                assert growth < maximum_growth, 'Resource growth exceeded bound: ' + key
        report['ok'] = True
    except Exception as exc:
        report['errors'].append(str(exc))
        raise
    finally:
        report['running'] = False
        persist()
