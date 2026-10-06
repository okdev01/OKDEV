"""Exercise the real WebView2 bridge against isolated fixture storage.

No game client is started and no real user mods/settings are read or written.
Run: python scripts/check_hub_webview.py
"""
import json
import sys
import tempfile
import time
import threading
import zipfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hub import library
from hub.desktop import Api, build_html
from hub.sources import entries


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', action='store_true')
    parser.add_argument('--zoom-check', action='store_true')
    parser.add_argument('--report', type=Path, default=ROOT / 'build/hub-webview-check.json')
    parser.add_argument('--accessibility', action='store_true')
    parser.add_argument('--keep-open', action='store_true')
    parser.add_argument('--soak-seconds', type=int, default=0)
    parser.add_argument('--soak-report', type=Path)
    options = parser.parse_args()
    if not 0 <= options.soak_seconds <= 24 * 3600:
        parser.error('--soak-seconds must be between 0 and 86400')
    import webview
    results = {'checks': [], 'errors': []}
    with tempfile.TemporaryDirectory(prefix='okdev-hub-qa-') as tmp, ExitStack() as stack:
        data = Path(tmp)
        for name in ('hub.library.get_user_data_dir', 'injection.mods.storage.get_user_data_dir',
                     'utils.core.historic.get_user_data_dir', 'utils.core.mod_historic.get_user_data_dir'):
            stack.enter_context(patch(name, return_value=data))
        library.write_json(library.root() / 'catalog.json', {'schema': 1, 'mods': []})
        package = data / 'fixture.fantome'
        with zipfile.ZipFile(package, 'w') as archive:
            archive.writestr('WAD/Ahri.wad.client', b'QA fixture, not a playable mod')
        library.import_archive(package, {'id': 'fixture', 'name': 'QA Ahri', 'champion': 'Ahri',
            'champion_id': 103, 'version': '1.0.0', 'description': 'Isolated test fixture'})
        api = Api()
        download_release = threading.Event()
        def fixture_download(job, progress, cancelled):
            progress({'stage': 'downloading', 'received': 1024, 'total': 4096})
            if not download_release.wait(15) or cancelled():
                raise ValueError('QA download cancelled')
            progress({'stage': 'installing', 'received': 4096, 'total': 4096})
            return library.import_archive(package, {'id': job['mod_id'], 'name': job['name'],
                'champion': 'Ahri', 'champion_id': 103, 'version': '1.0.0',
                'description': 'Isolated queue fixture, not a playable mod'})
        api._downloads()._operation = fixture_download
        window = webview.create_window('OKDEV • Arayüz testi', html=build_html(), js_api=api,
                                       width=1180, height=800, min_size=(850, 620))
        api._window = window
        window.events.closing += api._before_close

        def evaluate(script):
            return window.evaluate_js(script)

        def wait_for(expression, timeout=20):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    if evaluate(expression):
                        return
                except Exception:
                    pass
                time.sleep(.1)
            raise AssertionError('Timed out: ' + expression)

        def check(name, expression):
            assert evaluate(expression), name
            results['checks'].append(name)

        def click(selector):
            evaluate(f'document.querySelector({json.dumps(selector)}).click()')
            wait_for("document.getElementById('main').getAttribute('aria-busy') === 'false'")

        def capture(name):
            """Use WebView2's own renderer to export the test page, not the desktop."""
            from System import Func, Object
            from System.IO import FileStream, FileMode
            from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat
            time.sleep(.25)  # Let the page-entry transition reach its final frame.
            folder = ROOT / 'build/ui-preview'
            folder.mkdir(parents=True, exist_ok=True)
            stream = FileStream(str(folder / (name + '.png')), FileMode.Create)
            try:
                task = window.native.webview.Invoke(Func[Object](lambda:
                    window.native.webview.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, stream)))
                if not task.Wait(10000):
                    raise TimeoutError('WebView capture timed out')
            finally:
                stream.Dispose()

        def exercise():
            try:
                wait_for("document.querySelector('.favorite') && !document.querySelector('.favorite').disabled")
                evaluate("window.__qaErrors=[]; window.addEventListener('error',e=>window.__qaErrors.push(e.message)); window.addEventListener('unhandledrejection',e=>window.__qaErrors.push(String(e.reason)))")
                check('curated source entries', f"document.querySelectorAll('#catalogGrid .card').length === {min(24,len(entries()))}")
                check('no horizontal overflow', 'document.documentElement.scrollWidth <= window.innerWidth')
                evaluate("document.getElementById('categoryFilter').value='ui';document.getElementById('categoryFilter').dispatchEvent(new Event('change'))")
                hud_count = sum(m['category'] == 'ui' for m in entries())
                check('HUD category filter', f"document.querySelectorAll('#catalogGrid .card').length === {hud_count}")
                click('[data-mod-id="rf-dark-mode-hud"] .favorite')
                assert library.settings()['favorites'] == ['rf-dark-mode-hud']
                results['checks'].append('favorite persisted through Python bridge')
                click('[data-page="installed"]')
                click('#installedGrid .actions button')
                assert library.installed()['fixture']['enabled']
                results['checks'].append('enable persisted through Python bridge')
                click('[data-page="profiles"]')
                evaluate("document.getElementById('profileName').value='QA Profile'")
                click('.profile-row button')
                check('profile saved', "document.querySelectorAll('#profileCards .profile-card').length === 1")
                click('[data-page="installed"]')
                click('#installedGrid .actions button')
                click('[data-page="profiles"]')
                click('#profileCards .primary')
                wait_for("document.getElementById('selectionDialog').open")
                check('profile selection preview', "document.getElementById('selectionChanges').textContent.includes('QA Ahri')")
                click('#confirmSelection')
                assert library.installed()['fixture']['enabled']
                results['checks'].append('profile restores selection')
                evaluate("Array.from(document.querySelectorAll('#profileCards button')).find(b=>b.textContent==='⋯').click()")
                evaluate("document.getElementById('editProfileInput').value='Updated QA'")
                click('#editProfileDialog .primary')
                from hub import profiles
                assert next(iter(profiles.list_profiles().values()))['name'] == 'Updated QA'
                results['checks'].append('profile renamed through Python bridge')
                click('[data-page="installed"]')
                click('#disableAll')
                wait_for("document.getElementById('selectionDialog').open")
                click('#confirmSelection')
                assert not library.installed()['fixture']['enabled']
                click('#undoSelection')
                assert library.installed()['fixture']['enabled']
                results['checks'].append('disable all and undo selection through bridge')
                click('#installedGrid .actions button:last-child')
                check('mod detail opens', "document.getElementById('detailDialog').open")
                click('#detailContent .actions button:last-child')
                check('remove confirmation', "document.getElementById('removeDialog').open")
                click('#confirmRemove')
                assert not library.installed()
                assert len(library.removed()) == 1
                click('#recovery summary')
                click('#recovery button')
                assert not library.installed()['fixture']['enabled']
                results['checks'].append('remove and restore through UI')
                click('[data-page="library"]')
                click('[data-mod-id="rf-dark-mode-hud"] .actions button:last-child')
                click('#detailContent .actions button:last-child')
                check('source import selects HUD category', "document.getElementById('importCategory').value === 'ui' && document.getElementById('championLabel').hidden")
                check('source import preserves author', "document.getElementById('importSource').textContent.includes('p1mek')")
                check('source republish disabled', "document.getElementById('publishMod').disabled")
                click('#resetForm')
                evaluate("document.getElementById('championName').value='Ahri'; document.getElementById('championName').dispatchEvent(new Event('input'))")
                check('champion ID autocomplete', "document.getElementById('championId').value === '103'")
                api._selected = package
                evaluate("const f=document.getElementById('modForm');f.elements.namedItem('id').value='fixture';f.elements.namedItem('name').value='QA Ahri updated';f.elements.namedItem('version').value='2.0.0';f.dispatchEvent(new Event('submit',{cancelable:true}))")
                wait_for("document.getElementById('importReplaceDialog').open")
                check('replacement preview compares versions', "document.getElementById('importReplaceDialog').textContent.includes('v1.0.0 → QA Ahri updated · v2.0.0')")
                assert library.installed()['fixture']['version'] == '1.0.0'
                click('#importReplaceDialog button:not(.primary)')
                assert library.installed()['fixture']['version'] == '1.0.0'
                results['checks'].append('cancelling replacement preserves existing files')
                evaluate("document.getElementById('modForm').dispatchEvent(new Event('submit',{cancelable:true}))")
                wait_for("document.getElementById('importReplaceDialog').open")
                click('#importReplaceDialog .primary')
                wait_for("!document.getElementById('importReplaceDialog').open")
                assert library.installed()['fixture']['version'] == '2.0.0'
                assert any(item['mod_id'] == 'fixture' and item['version'] == '1.0.0' for item in library.removed())
                results['checks'].append('confirmed replacement retains original backup')

                click('[data-page="diagnostics"]')
                click('#checkDiagnostics')
                check('local diagnostics rendered', "document.querySelectorAll('#diagnosticsGrid article').length >= 7")
                check('storage usage renders six local categories', "!document.getElementById('storageSummary').hidden && document.querySelectorAll('#storageGrid .storage-card').length === 6")
                click('#showStorageBackups')
                check('storage shortcut opens and focuses local backups', "document.getElementById('recovery').open && document.activeElement === document.querySelector('#recovery summary')")
                click('[data-page="assistants"]')
                evaluate("document.getElementById('theme').value='light';document.getElementById('theme').dispatchEvent(new Event('change'))")
                wait_for("document.documentElement.dataset.theme === 'light'")
                check('light theme applied', "getComputedStyle(document.body).color === 'rgb(36, 33, 45)'")
                evaluate("document.getElementById('theme').value='dark';document.getElementById('theme').dispatchEvent(new Event('change'))")
                wait_for("document.documentElement.dataset.theme === 'dark'")
                click('[data-page="library"]')
                click('[data-mod-id="rf-dark-mode-hud"] .primary')
                click('[data-page="downloads"]')
                wait_for("document.querySelector('.download-job.downloading')")
                check('background download does not lock settings', "!document.getElementById('theme').disabled")
                check('download progress renders', "document.querySelector('.job-progress') !== null")
                window.destroy()
                wait_for("document.getElementById('closeWindowDialog').open")
                check('native close during download offers safe choices', "document.getElementById('closeWindowDialog').contains(document.activeElement)")
                click('#keepWindowOpen')
                check('continue keeps native window and download alive', "!document.getElementById('closeWindowDialog').open && document.querySelector('.download-job.downloading')")
                if '--capture' in sys.argv:
                    time.sleep(.3)
                    capture('downloads-active')
                click('[data-page="installed"]')
                evaluate("document.querySelector('#installedGrid .card-select input').focus();window.__focusedMod=document.activeElement.closest('.card').dataset.modId")
                download_release.set()
                wait_for("document.querySelector('.download-job.completed')")
                check('background completion preserves native checkbox focus', "document.activeElement.type === 'checkbox' && document.activeElement.closest('.card').dataset.modId === window.__focusedMod")
                assert 'rf-dark-mode-hud' in library.installed()
                results['checks'].append('background queue installs and refreshes real library')
                for section in ('home', 'library', 'installed', 'profiles', 'guides', 'assistants', 'diagnostics', 'downloads'):
                    click(f'[data-page="{section}"]')
                    check(section + ': no horizontal overflow', 'document.documentElement.scrollWidth <= window.innerWidth')
                    if '--capture' in sys.argv:
                        time.sleep(.3)
                        capture(section)
                for width, height in ((850, 620), (1600, 950)):
                    window.resize(width, height)
                    time.sleep(.4)
                    for section in ('home', 'library', 'profiles', 'guides', 'assistants', 'publish', 'installed', 'downloads'):
                        click(f'[data-page="{section}"]' if section != 'publish' else '#quickImport')
                        check(f'{section} at {width}px: no overflow', 'document.documentElement.scrollWidth <= window.innerWidth')
                    if '--capture' in sys.argv:
                        click('[data-page="guides"]')
                        time.sleep(.3)
                        capture(f'guides-{width}')
                if options.zoom_check:
                    from System import Action
                    for width in (850, 1180):
                        window.resize(width, 800)
                        for zoom in (1.25, 1.5, 2.0):
                            window.native.webview.Invoke(Action(lambda: setattr(window.native.webview, 'ZoomFactor', zoom)))
                            time.sleep(.3)
                            for section in ('home', 'library', 'installed', 'profiles', 'guides', 'assistants', 'publish', 'diagnostics', 'downloads'):
                                click(f'[data-page="{section}"]' if section != 'publish' else '#quickImport')
                                overflow = evaluate("({viewport:innerWidth,width:document.documentElement.scrollWidth,offenders:Array.from(document.querySelectorAll('main *')).filter(e=>e.getBoundingClientRect().width>0&&e.getBoundingClientRect().right>innerWidth+1).slice(0,12).map(e=>({tag:e.tagName,id:e.id,cls:e.className,right:e.getBoundingClientRect().right}))})")
                                assert overflow['width'] <= overflow['viewport'] + 1, f'{section} at {width}px/{zoom}: {overflow}'
                                results['checks'].append(f'{section} at {width}px/{int(zoom*100)}% zoom: no overflow')
                            if options.capture:
                                click('[data-page="installed"]')
                                capture(f'installed-{width}-zoom-{int(zoom*100)}')
                    window.native.webview.Invoke(Action(lambda: setattr(window.native.webview, 'ZoomFactor', 1.0)))
                    window.resize(1180, 800)
                click('[data-page="home"]')
                if '--accessibility' in sys.argv:
                    axe = ROOT / 'test/ui/node_modules/axe-core/axe.min.js'
                    evaluate(axe.read_text(encoding='utf-8'))
                    audits = []
                    for theme in ('dark', 'light'):
                        click('[data-page="assistants"]')
                        evaluate(f"document.getElementById('theme').value='{theme}';document.getElementById('theme').dispatchEvent(new Event('change'))")
                        wait_for("document.getElementById('main').getAttribute('aria-busy') === 'false'")
                        for section in ('home', 'library', 'installed', 'profiles', 'guides', 'assistants', 'publish', 'diagnostics', 'downloads'):
                            click(f'[data-page="{section}"]' if section != 'publish' else '#quickImport')
                            evaluate("window.__axeResult=null; axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}},(error,result)=>{window.__axeResult=error?{error:String(error)}:{violations:result.violations.map(v=>({id:v.id,impact:v.impact,description:v.description,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),passes:result.passes.length,incomplete:result.incomplete.map(v=>({id:v.id,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}))};})")
                            wait_for('window.__axeResult !== null')
                            audits.append({'theme': theme, 'section': section, **evaluate('window.__axeResult')})
                    audit_path = ROOT / 'build/accessibility-check.json'
                    audit_path.write_text(json.dumps(audits, ensure_ascii=False, indent=2), encoding='utf-8')
                    violations = sum(len(audit.get('violations', [])) for audit in audits)
                    assert all(not audit.get('error') and audit.get('passes', 0) > 0 for audit in audits), 'Accessibility engine failed'
                    # The two-letter decorative logo is exempt from text
                    # contrast requirements; axe asks for human review of it.
                    for audit in audits:
                        for item in audit['incomplete']:
                            assert item['id'] == 'color-contrast' and all(node['target'] in [['.mark'], ['.mark > span']]
                                for node in item['nodes']), 'Unreviewed accessibility finding: ' + str(item)
                    check('18 accessibility page/theme audits', str(violations == 0).lower())
                check('no JavaScript errors', 'window.__qaErrors.length === 0')
                if options.soak_seconds:
                    from hub_soak import run as soak
                    soak(window, evaluate, click, wait_for, ROOT, options.soak_seconds, output=options.soak_report)
                    results['checks'].append('Native WebView endurance completed')
                results['ok'] = True
            except Exception as exc:
                results['ok'] = False
                results['errors'].append(str(exc))
            finally:
                download_release.set()
                api._downloads().close()
                api._downloads().wait_closed(10)
                report = options.report
                report.parent.mkdir(exist_ok=True)
                report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
                if '--keep-open' not in sys.argv:
                    api._allow_close = True
                    window.destroy()

        webview.start(exercise, gui='edgechromium', storage_path=str(data / 'webview'), private_mode=True)
    print(json.dumps(results, ensure_ascii=False))
    return 0 if results.get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(main())
