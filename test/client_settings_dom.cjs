'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const {JSDOM, VirtualConsole} = require('./ui/node_modules/jsdom');
const root = path.resolve(__dirname, '..');
const read = name => fs.readFileSync(path.join(root, name), 'utf8');
const errors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => errors.push(e.message));
const dom = new JSDOM('<!doctype html><html><head></head><body><lol-uikit-navigation-item id="qa-nav" class="menu_item_Golden OKDEV" tabindex="0">OKDEV</lol-uikit-navigation-item></body></html>', {
  url:'https://okdev.test', runScripts:'dangerously', pretendToBeVisual:true, virtualConsole:vc,
});
const w = dom.window, d = w.document, $ = id => d.getElementById(id);
w.matchMedia = () => ({matches:false,addEventListener(){}});
w.HTMLElement.prototype.scrollIntoView = function () {};
w.__qaLocale = JSON.parse(read('Pengu Loader/plugins/OKDEV-I18n/locales/tr.json'));
w.eval(read('test/fixtures/client_settings.js'));
w.eval(read('Pengu Loader/plugins/OKDEV-SettingsPanel/index.js'));
const settle = (ms=40) => new Promise(resolve => setTimeout(resolve, ms));
const checks = [];
function check(value, text) { assert.ok(value, text); checks.push(text); }
function change(id, value) { $(id).value=value; $(id).dispatchEvent(new w.Event('change',{bubbles:true})); }
function key(name, target=d.activeElement, options={}) { target.dispatchEvent(new w.KeyboardEvent('keydown',{key:name,bubbles:true,cancelable:true,...options})); }
(async () => {
  try {
    await settle();
    const baseline = w.__settingsQa.listenerCount();
    w.__settingsQa.open(); await settle(140);
    check($('threshold-slider').value==='50', 'Saved settings fill the native ranges');
    check($('threshold-slider').getAttribute('aria-label'), 'Ranges have accessible names');
    check($('autostart-checkbox').labels.length, 'Clicking a checkbox label is supported');
    check($('game-path-input').labels.length, 'Game path has a real label');
    change('add-custom-mods-dropdown','maps'); await settle();
    check(w.__settingsQa.calls.filter(c=>c.type==='add-custom-mods-category-selected').length===1, 'Adding a category sends exactly one bridge request');
    check($('add-custom-mods-dropdown').value==='', 'Category select resets without invalid selector exceptions');
    $('game-path-input').value='C:\\QA draft'; $('game-path-input').dispatchEvent(new w.Event('input',{bubbles:true}));
    w.__settingsQa.emit('settings-data',{...w.__settingsQa.settings});
    check($('game-path-input').value==='C:\\QA draft','A late settings response preserves unsaved edits');
    w.dispatchEvent(new w.Event('okdev-i18n-changed'));await settle(140);
    check($('game-path-input').value==='C:\\QA draft','Changing language preserves an unsaved form draft');
    $('game-path-input').value=''; $('game-path-input').dispatchEvent(new w.Event('input',{bubbles:true}));
    const validationCount=w.__settingsQa.calls.filter(c=>c.type==='path-validate').length;
    await settle(550);
    check(w.__settingsQa.calls.filter(c=>c.type==='path-validate').length===validationCount,'Clearing a path cancels its stale validation request');
    $('threshold-slider').value='200'; $('threshold-slider').dispatchEvent(new w.Event('input',{bubbles:true}));
    check($('threshold-value').textContent==='2.00 s','Native range updates its visible value');
    check($('threshold-slider').getAttribute('aria-valuetext')==='2.00 s','Native range announces its formatted value');
    check($('threshold-slider').closest('.lol-settings-slider').querySelector('.lol-uikit-slider-button').style.left==='calc(100% - 30px)','Range maximum stays within a responsive track');
    w.__settingsQa.holdSave=true;
    $('save-button').click();$('save-button').click();await settle();
    const saves=w.__settingsQa.calls.filter(c=>c.type==='settings-save');
    check(saves.length===1 && $('save-button').disabled,'Repeated saving is blocked while awaiting acknowledgement');
    w.__settingsQa.emit('settings-saved',{requestId:'stale-request',success:true});
    check($('save-button').disabled,'A stale acknowledgement cannot complete the current save');
    $('game-path-input').value='C:\\New draft';$('game-path-input').dispatchEvent(new w.Event('input',{bubbles:true}));
    w.__settingsQa.emit('settings-saved',{requestId:saves[0].requestId,success:true});await settle();
    check($('game-path-input').value==='C:\\New draft','Editing during a save preserves the newer draft after acknowledgement');
    w.__settingsQa.holdSave=false;w.__settingsQa.failSave=true;
    $('save-button').click();await settle();
    check(!$('save-button').disabled && $('okdev-settings-feedback').textContent==='QA: Disk full','Save failures appear inline and restore retry');
    w.__settingsQa.failSave=false;$('save-button').click();await settle();
    check($('okdev-settings-feedback').textContent===w.OKDEVI18n.t('Saved!'),'Retry succeeds after a save failure');
    w.__settingsQa.throwSave=true;$('save-button').click();await settle();
    check(!$('save-button').disabled && $('okdev-settings-feedback').textContent.includes('Bridge disconnected'),'A synchronous bridge failure restores Save without an uncaught error');
    w.__settingsQa.throwSave=false;
    $('manage-custom-mods-dropdown').focus();change('manage-custom-mods-dropdown','maps');await settle();
    check($('category-mods-manage-dialog') && $('okdev-settings-flyout').inert,'Nested mod management makes the settings panel inert');
    $('category-mods-manage-dialog').querySelector('.mod-delete-button').click();await settle();
    $('delete-mod-confirm-dialog').querySelector('.mod-delete-button').click();await settle();
    check($('category-mods-manage-dialog').querySelector('.okdev-management-feedback').textContent.includes('Permission denied'),'A failed deletion is visible in its owning management dialog');
    check(!$('category-mods-manage-dialog').querySelector('.mod-delete-button').disabled,'A failed deletion restores the list actions');
    const rename=$('category-mods-manage-dialog').querySelector('.mod-rename-button');rename.focus();rename.click();await settle();
    check($('rename-mod-dialog').getAttribute('aria-modal')==='true','Rename is an accessible nested dialog');
    key('Escape');await settle();
    check(!$('rename-mod-dialog') && d.activeElement===rename,'Escape dismisses only rename and restores its opener');
    key('Escape');await settle();
    check(!$('category-mods-manage-dialog') && !$('okdev-settings-flyout').inert,'Dismissing management reactivates settings');
    w.__settingsQa.failList=true;change('manage-custom-mods-dropdown','maps');await settle();
    check($('category-mods-manage-dialog').querySelector('.okdev-management-feedback').textContent.includes('Listing failed'),'A list error is not misreported as an empty library');
    w.__settingsQa.failList=false;$('category-mods-manage-dialog').querySelector('.okdev-management-feedback button').click();await settle();
    check($('category-mods-manage-dialog').querySelectorAll('.mod-manage-row').length===2,'Reload list recovers after a listing error');
    key('Escape');await settle();
    change('add-custom-mods-dropdown','skins');await settle();
    $('champions-grid').querySelector('button').click();await settle();
    const skinButton=$('skins-list').querySelector('.skin-target');
    check(skinButton.tagName==='BUTTON' && skinButton.tabIndex===0,'Base skins use keyboard-accessible native buttons');
    skinButton.click();await settle();
    check(skinButton.getAttribute('aria-pressed')==='true' && !$('skin-selection-confirm').disabled,'Selecting a base skin enables confirmation');
    const chromaCard=$('skins-list').querySelector('.skin-chroma-button').closest('.skin-card');
    check(chromaCard.querySelector('.skin-card-back').inert,'Hidden chroma controls are excluded from keyboard focus');
    chromaCard.querySelector('.skin-chroma-button').click();await settle();
    check(chromaCard.querySelector('.skin-card-front').inert && !chromaCard.querySelector('.skin-card-back').inert,'Flipping exposes only the visible card face to keyboard navigation');
    chromaCard.querySelector('.skin-option:last-child').click();await settle();
    check($('skin-selection-count').textContent.includes('2'),'Base and chroma targets can be selected together');
    chromaCard.querySelector('.skin-card-back-close').click();await settle();
    check(d.activeElement===chromaCard.querySelector('.skin-chroma-button'),'Closing chromas restores the visible opener');
    const beforeSkins=$('skins-list').innerHTML;
    w.__settingsQa.emit('champion-skins-response',{championId:157,championName:'Wrong champion',skins:[{skinId:157000,name:'Wrong target'}]});
    check($('skins-list').innerHTML===beforeSkins,'A late response for another champion cannot replace targets');
    $('skin-selection-confirm').click();await settle();
    const importRequest=w.__settingsQa.calls.findLast(c=>c.type==='add-custom-mods-skin-selected'&&c.action==='create');
    check(importRequest.championId===103 && JSON.stringify(importRequest.skinIds)==='[103000,103002]','Confirmation sends the exact selected base and chroma IDs');
    documentClose(); await settle(20); w.__settingsQa.open(); await settle(260);
    check($('okdev-settings-panel') && $('save-button'),'Reopening during the close animation preserves the new panel');
    documentClose(); await settle(240);
    check(w.__settingsQa.listenerCount()===baseline,'Closing releases all panel-owned global listeners');
    for (let n=0;n<12;n++) { w.__settingsQa.open();await settle(10);documentClose();await settle(230); }
    check(w.__settingsQa.listenerCount()===baseline,'Repeated opening and closing does not grow listeners');
    check(errors.length===0 && w.__settingsQa.errors.length===0,'Full plugin execution has no script errors');
    console.log(JSON.stringify({ok:true,checks}));
  } catch (error) { console.error(error.stack); console.error(JSON.stringify({checks,errors,pluginErrors:w.__settingsQa.errors})); process.exitCode=1; }
  finally { w.close(); }
})();
function documentClose() { d.querySelector('.okdev-panel-close').click(); }
