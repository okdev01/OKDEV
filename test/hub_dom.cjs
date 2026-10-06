/* Runs the real UI in an in-memory DOM. No browser, windows, LCU or network. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM, VirtualConsole} = require('./ui/node_modules/jsdom');
const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const sources = JSON.parse(read('hub/web/sources.json'));
const champions = JSON.parse(read('hub/web/champions.json')).champions;
const mods = [
  {id:'test-hud',name:'Test HUD',category:'ui',champion:'',version:'1.0.0',description:'A fixture HUD.',enabled:false,installed_at:20},
  {id:'test-yi',name:'Yi fixture',category:'skins',champion:'Master Yi',champion_id:11,version:'1.0.0',description:'Champion fixture.',enabled:true,installed_at:10},
];
const prefs = {mobalytics_enabled:false,mobalytics_auto_show:true,mobalytics_hotkey:'Ctrl+Shift+B',mobalytics_position:'right',theme:'dark',compact_cards:false,reduce_motion:false,start_minimized:false};
const state = {catalog:[],installed:Object.fromEntries(mods.map(m=>[m.id,m])),settings:{favorites:[],auto_accept:false},preferences:prefs,profiles:{fixture:{name:'Test profile',mods:['test-yi']}},removed:[],warning:'',guide:{connected:false,pick:null},companion:{running:false}};
const calls = [], errors = [];
const result = action => async (...args) => { calls.push([action,...args]); return {ok:true}; };
const api = {
  snapshot:async()=>structuredClone(state), guide_state:async()=>({guide:state.guide,preferences:prefs,companion:state.companion}),
  prepare_import:result('prepare_import'), choose_mod:async()=>({name:'Fixture.fantome',suggested:{name:'Fixture',id:'fixture',category:'skins',champion:'Master Yi',champion_id:11},warning:''}),
  import_mod:result('import_mod'), favorite:result('favorite'), show_guide:result('show_guide'), hide_guide:result('hide_guide'),
  save_profile:result('save_profile'), apply_profile:result('apply_profile'), remove_profile:result('remove_profile'),
  rename_profile:result('rename_profile'), update_profile:result('update_profile'),
  download_source:result('download_source'), download_status:async()=>({stage:'idle',received:0,total:0}),
  export_diagnostics:async()=>({ok:true,result:{saved:true}}),
  open_source:result('open_source'), enable:result('enable'), remove:result('remove'), restore:result('restore'),
  auto_accept:async value=>{state.settings.auto_accept=value;return {ok:true};},
  save_preferences:async changes=>{Object.assign(prefs,changes);return {ok:true};},
};
const html = read('hub/web/index.html').replace('/*APP_CSS*/', read('hub/web/app.css')).replace('/*BOOTSTRAP*/', 'window.HUB_DATA='+JSON.stringify({sources:Array.isArray(sources)?sources:sources.mods,champions})+';').replace('/*APP_JS*/', read('hub/web/app.js'));
const virtualConsole = new VirtualConsole();
virtualConsole.on('jsdomError', e => errors.push(e.message));
const dom = new JSDOM(html, {url:'https://okdev.test',runScripts:'dangerously',virtualConsole,pretendToBeVisual:true,beforeParse(window){
  window.matchMedia=()=>({matches:false,addEventListener(){}});window.scrollTo=()=>{};
  window.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
  window.HTMLDialogElement.prototype.close=function(){this.open=false;};
  window.pywebview={api};
}});
const {window} = dom, document=window.document, $=id=>document.getElementById(id);
const settle = ()=>new Promise(resolve=>setTimeout(resolve,20));
const click=async selector=>{const el=typeof selector==='string'?document.querySelector(selector):selector;assert.ok(el,'Missing control '+selector);el.click();await settle();};
const change=async (id,value)=>{const el=$(id);if(el.type==='checkbox')el.checked=value;else el.value=value;el.dispatchEvent(new window.Event('change'));await settle();};
(async()=>{
  try {
    window.dispatchEvent(new window.Event('pywebviewready'));await settle();
    assert.deepEqual(errors,[], 'UI startup exceptions');
    assert.equal($('home').hidden,false);assert.equal($('installedCount').textContent,'2');
    assert.equal(document.querySelectorAll('#homeRecent .recent-item').length,2);
    await click('[data-page="installed"]');assert.equal($('installed').hidden,false);assert.equal($('home').hidden,true);
    assert.equal(document.querySelectorAll('#installedGrid .card').length,2);
    await change('installedFilter','enabled');assert.equal(document.querySelectorAll('#installedGrid .card').length,1);
    await click('#installedGrid .card-title-button');assert.equal($('detailDialog').open,true);assert.match($('detailContent').textContent,/Yi fixture/);
    await click('#closeDetail');assert.equal($('detailDialog').open,false);
    await click('[data-page="library"]');await click('[data-category="ui"]');
    assert.equal($('categoryFilter').value,'ui');
    assert.ok([...document.querySelectorAll('#catalogGrid .mod-meta')].every(e=>e.textContent.includes('HUD')));
    await click('#catalogGrid .primary');assert.ok(calls.some(c=>c[0]==='download_source'));
    assert.equal($('downloadProgress').hidden,true);
    await click('#catalogGrid .card-title-button');assert.equal($('detailDialog').open,true);
    const importButton=[...document.querySelectorAll('#detailContent button')].find(e=>e.textContent.includes('İndirdiğim'));
    await click(importButton);assert.equal($('publish').hidden,false);assert.ok(calls.some(c=>c[0]==='prepare_import'));
    await click('#resetForm');await click('#choose');
    assert.equal($('championName').value,'Master Yi');assert.equal($('championId').value,'11');
    assert.equal($('modForm').elements.namedItem('name').value,'Fixture');
    $('modForm').dispatchEvent(new window.Event('submit',{cancelable:true}));await settle();
    assert.ok(calls.some(c=>c[0]==='import_mod'&&c[1].champion_id==='11'));
    api.preview_import=async()=>({ok:true,result:{name:'Fixture',version:'2.0.0',existing:{name:'Fixture',version:'1.0.0',enabled:true},revision:'reviewed-import'}});
    await click('#quickImport');
    const beforeReplacement=calls.filter(c=>c[0]==='import_mod').length;
    $('modForm').dispatchEvent(new window.Event('submit',{cancelable:true}));await settle();
    assert.equal($('importReplaceDialog').open,true);
    assert.match($('importReplaceDialog').textContent,/v1.0.0 → Fixture · v2.0.0/);
    assert.equal(calls.filter(c=>c[0]==='import_mod').length,beforeReplacement,'Preview never updates a mod');
    await click([...document.querySelectorAll('#importReplaceDialog button')].find(e=>e.textContent==='Vazgeç'));
    assert.equal(calls.filter(c=>c[0]==='import_mod').length,beforeReplacement,'Cancel preserves current version');
    $('modForm').dispatchEvent(new window.Event('submit',{cancelable:true}));await settle();
    await click('#importReplaceDialog .primary');
    assert.equal(calls.filter(c=>c[0]==='import_mod').at(-1)[2],'reviewed-import');
    assert.equal($('importReplaceDialog').open,false);
    api.preview_import=async()=>({ok:true,result:{name:'New',version:'1.0.0',existing:null,revision:'new-import'}});
    await click('#quickImport');
    $('modForm').dispatchEvent(new window.Event('submit',{cancelable:true}));await settle();
    assert.equal(calls.filter(c=>c[0]==='import_mod').at(-1)[2],'new-import');
    assert.equal($('importReplaceDialog').open,false,'New mods do not require a replacement dialog');

    await click('[data-page="guides"]');assert.equal($('showCurrentGuide').disabled,true);
    await change('guideEnabled',true);assert.equal(prefs.mobalytics_enabled,true);
    await change('guideSize','compact');assert.equal(prefs.mobalytics_size,'compact');
    await change('guideSize','wide');assert.equal(prefs.mobalytics_size,'wide');
    $('guideManualChampion').value='Master Yi';await change('guideManualRole','jungle');await click('#showManualGuide');
    assert.ok(calls.some(c=>c[0]==='show_guide'&&c[1]===11&&c[2]==='jungle'));
    await click('[data-page="assistants"]');await change('theme','light');assert.equal(document.documentElement.dataset.theme,'light');
    await change('compactCards',true);assert.equal(document.body.classList.contains('compact'),true);
    await change('autoAccept',true);assert.equal(state.settings.auto_accept,true);
    await click('[data-page="profiles"]');assert.equal(document.querySelectorAll('#profileCards .profile-card').length,1);
    await click('#profileCards .primary');assert.ok(calls.some(c=>c[0]==='apply_profile'&&c[1]==='fixture'));
    await click([...document.querySelectorAll('#profileCards button')].find(e=>e.textContent==='⋯'));
    $('editProfileInput').value='Yeni kombinasyon';await click('#editProfileDialog .primary');
    assert.ok(calls.some(c=>c[0]==='rename_profile'&&c[1]==='fixture'&&c[2]==='Yeni kombinasyon'));
    await click([...document.querySelectorAll('#profileCards button')].find(e=>e.textContent==='⋯'));
    await click([...document.querySelectorAll('#editProfileDialog button')].find(e=>e.textContent==='Etkin seçimlerle güncelle'));
    assert.equal($('updateProfileDialog').open,true);await click('#updateProfileDialog .primary');
    assert.ok(calls.some(c=>c[0]==='update_profile'&&c[1]==='fixture'));
    await click('[data-page="diagnostics"]');await click('#exportDiagnostics');assert.match($('status').textContent,/Destek raporu kaydedildi/);
    await click('[data-page="installed"]');
    const toggle=document.querySelector('#installedGrid .actions button');toggle.focus();await click(toggle);
    assert.ok(document.activeElement.closest('#installedGrid'),'Keyboard focus is restored after a mod action');
    document.dispatchEvent(new window.KeyboardEvent('keydown',{key:'k',ctrlKey:true,bubbles:true}));assert.equal(document.activeElement.id,'search');
    assert.deepEqual(errors,[], 'UI interaction exceptions');
    console.log('UI flows passed: navigation, filters, detail, source import, file metadata, guide toggle/manual build, theme, compact mode, auto-accept, profiles, keyboard search. No windows opened.');
  } finally { window.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});

