'use strict';
// User journeys added during the two-hour UI refinement. Real application JS,
// isolated bridge, no network; native geometry is tested by hub_polish_qa.py.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const{JSDOM,VirtualConsole}=require('./ui/node_modules/jsdom');
const root=path.resolve(__dirname,'..'),read=f=>fs.readFileSync(path.join(root,f),'utf8');
const calls=[],errors=[],state={installed:{
  skin:{id:'skin',name:'Kış Ahri',champion:'Ahri',champion_id:103,category:'skins',version:'1.0.0',enabled:true,files_available:true},
  hud:{id:'hud',name:'Gece HUD',category:'ui',version:'1.0.0',enabled:false,files_available:true},
},catalog:[],profiles:{},removed:[],settings:{favorites:[]},preferences:{theme:'dark',data_saver:true,mod_view:'grid'},guide:{},companion:{},downloads:{jobs:[],active:0},activity:{events:[]},selection_undo:{available:false},revision:'one'};
let watchdog,failSnapshot=false,file=null;
const api={snapshot:async()=>{if(failSnapshot)throw Error('Bridge interrupted');return structuredClone(state);},
  save_preferences:async changes=>{Object.assign(state.preferences,changes);calls.push(['preferences',changes]);return{ok:true};},
  save_profile:async name=>{calls.push(['save',name]);state.profiles.saved={name,mods:['skin']};return{ok:true};},
  choose_mod:async()=>file,prepare_import:async()=>({ok:true}),preview_import:async()=>{calls.push(['preview-import']);return{ok:true,result:{name:'Test',version:'1.0.0'}};},
  import_mod:async()=>{calls.push(['import']);return{ok:true};},guide_state:async()=>({guide:{},companion:{},preferences:state.preferences}),
  favorite:async()=>({ok:true}),state_revision:async()=>state.revision,downloads_status:async()=>state.downloads};
const html=read('hub/web/index.html').replace('/*APP_CSS*/',read('hub/web/app.css')).replace('/*BOOTSTRAP*/','window.HUB_DATA='+JSON.stringify({version:'2.0.0',sources:[],champions:[]})+';').replace('/*APP_JS*/',read('hub/web/app.js'));
const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
const dom=new JSDOM(html,{url:'https://okdev.test',runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
  const timeout=w.setTimeout.bind(w);w.setTimeout=(fn,ms,...args)=>{if(ms===8000){watchdog=fn;return 0;}return timeout(fn,ms,...args);};
  w.setInterval=()=>0;w.matchMedia=()=>({matches:false,addEventListener(){}});w.scrollTo=()=>{};
  w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;};
}});
const{window:w}=dom,d=w.document,$=id=>d.getElementById(id),settle=()=>new Promise(r=>setTimeout(r,25));
async function click(selector){const e=typeof selector==='string'?d.querySelector(selector):selector;assert(e,selector);e.focus();e.click();await settle();}
function change(id,value){$(id).value=value;$(id).dispatchEvent(new w.Event('change'));}
function input(id,value){$(id).value=value;$(id).dispatchEvent(new w.Event('input'));}
(async()=>{try{
  assert.equal($('loadingBanner').hidden,false);assert.equal($('modForm').querySelector('[type=submit]').disabled,true);
  watchdog();assert.equal($('bridgeNotice').hidden,false);assert.equal($('loadingBanner').hidden,true);
  w.pywebview={api};await click('#retryConnection');assert.equal($('bridgeNotice').hidden,true);assert.equal(d.body.classList.contains('initializing'),false);
  await click('[data-page="assistants"]');
  const appearance=$('settingsTab-appearance');appearance.focus();appearance.dispatchEvent(new w.KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));
  assert.equal(d.activeElement,$('settingsTab-play'));assert.equal($('settingsPanel-play').hidden,false);assert.equal($('settingsPanel-appearance').hidden,true);
  $('settingsTab-play').dispatchEvent(new w.KeyboardEvent('keydown',{key:'End',bubbles:true}));assert.equal(d.activeElement,$('settingsTab-about'));
  $('settingsTab-about').dispatchEvent(new w.KeyboardEvent('keydown',{key:'Home',bubbles:true}));assert.equal(d.activeElement,appearance);
  await click('[data-page="installed"]');await click('[data-view-owner="installed"][data-view-mode="list"]');
  assert.equal(state.preferences.mod_view,'list');assert($('installedGrid').classList.contains('list-view'));assert($('catalogGrid').classList.contains('list-view'));
  assert.equal($('modView').value,'list');assert.equal(d.activeElement.dataset.viewMode,'list');assert.equal(d.activeElement.disabled,false);
  assert.equal($('bulkToolbar').hidden,true);await click('#selectVisible');assert.equal($('bulkToolbar').hidden,false);assert.match($('bulkCount').textContent,/2 mod/);
  await click('#clearBulk');assert.equal($('bulkToolbar').hidden,true);
  input('search','retained library search');input('installedSearch','missing name');change('installedCategory','ui');await settle();
  assert.equal($('installedChips').children.length,2);assert.equal($('libraryChips').children.length,1);
  await click($('installedGrid').querySelector('button'));assert.equal($('installedSearch').value,'');assert.equal($('installedCategory').value,'');assert.equal($('search').value,'retained library search','Clearing installed filters preserves discovery filters');
  change('installedCategory','ui');input('installedSearch','Gece');await settle();
  await click($('installedChips').children[0]);assert.equal($('installedSearch').value,'');assert.equal($('installedCategory').value,'ui','Removing one chip preserves other filters');
  await click('[data-page="profiles"]');await click('#newProfile');assert.equal($('createProfileDialog').open,true);assert.equal(d.activeElement,$('profileName'));
  assert.match($('newProfileSummary').textContent,/1 etkin mod/);
  $('profileName').value='   ';$('createProfileDialog').querySelector('form').dispatchEvent(new w.Event('submit',{cancelable:true}));await settle();
  assert.equal($('profileError').hidden,false);assert.equal(calls.filter(c=>c[0]==='save').length,0);
  input('profileName','  Gece oyunu  ');assert.equal($('profileError').hidden,true);
  failSnapshot=true;$('createProfileDialog').querySelector('form').dispatchEvent(new w.Event('submit',{cancelable:true}));await settle();
  assert.deepEqual(calls.find(c=>c[0]==='save'),['save','Gece oyunu']);assert.equal($('createProfileDialog').open,false,'Committed save closes even if the snapshot fails');assert.match($('status').textContent,/tekrar yapmana gerek yok/);
  failSnapshot=false;await click('#retryConnection');assert.match($('profileCards').textContent,/Gece oyunu/);
  await click('#quickImport');$('modForm').dispatchEvent(new w.Event('submit',{cancelable:true}));await settle();
  assert.equal($('importError').hidden,false);assert.equal(calls.filter(c=>c[0]==='preview-import').length,0);
  await click('#choose');assert.equal($('status').textContent,'','Cancelling the picker is not reported as a success');
  assert.equal($('modForm').querySelector('[type=submit]').disabled,true);
  file={name:'new.fantome',suggested:{name:'Test HUD',category:'ui',version:'1.0.0'}};await click('#choose');
  assert.equal($('importError').hidden,true);assert.equal($('choose').textContent,'Dosyayı değiştir');assert.equal($('modForm').querySelector('[type=submit]').disabled,false);
  await click('#resetForm');assert.equal($('modForm').querySelector('[type=submit]').disabled,true);assert.equal($('choose').textContent,'Dosya seç');
  assert.deepEqual(errors,[]);console.log('UI polish journeys passed: bridge startup/retry, settings keyboard tabs, persisted grid/list, contextual bulk, independent filter reset, profile validation/save-refresh failure, file readiness and cancelled pickers.');
}finally{w.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
