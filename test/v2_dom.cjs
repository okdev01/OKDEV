'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM,VirtualConsole}=require('./ui/node_modules/jsdom');
const root=path.resolve(__dirname,'..'),read=f=>fs.readFileSync(path.join(root,f),'utf8');
const errors=[],calls=[],timers=new Map();
const mod={id:'ahri',name:'Çığ Ahri',champion:'Ahri',champion_id:103,category:'skins',version:'1.0.0',enabled:true,files_available:true,target_skin_ids:[103001],image_url:'https://example.invalid/cover.jpg'};
const state={installed:{ahri:mod},catalog:[],profiles:{missing:{name:'Eksik paket',mods:['ahri'],missing:1}},removed:[],settings:{favorites:[]},preferences:{theme:'dark',data_saver:true},guide:{},companion:{},downloads:{jobs:[],active:0},activity:{events:[]},selection_undo:{available:false},warning:'',revision:'one'};
let disconnected=false;
const api={snapshot:async()=>structuredClone(state),state_revision:async()=>{if(disconnected)throw new Error('Offline');return state.revision;},
  save_preferences:async changes=>{Object.assign(state.preferences,changes);return {ok:true};},
  guide_state:async()=>({guide:{},companion:{},preferences:state.preferences}),downloads_status:async()=>state.downloads,
  preview_selection:async()=>{calls.push('preview');return {ok:true};}};
const html=read('hub/web/index.html').replace('/*APP_CSS*/',read('hub/web/app.css')).replace('/*BOOTSTRAP*/','window.HUB_DATA='+JSON.stringify({version:'2.0.0',sources:[{...mod,id:'remote',source_url:'https://example.invalid'}],champions:[]})+';').replace('/*APP_JS*/',read('hub/web/app.js'));
const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
const dom=new JSDOM(html,{url:'https://okdev.test',runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc,beforeParse(window){
  window.matchMedia=()=>({matches:false,addEventListener(){}});window.scrollTo=()=>{};window.setInterval=(fn,ms)=>{timers.set(ms,fn);return ms;};
  window.HTMLDialogElement.prototype.showModal=function(){this.open=true;};window.HTMLDialogElement.prototype.close=function(){this.open=false;};window.pywebview={api};
}});
const {window}=dom,doc=window.document,$=id=>doc.getElementById(id),settle=()=>new Promise(r=>setTimeout(r,25));
const click=selector=>doc.querySelector(selector).click();
(async()=>{try{
  assert.equal(doc.querySelectorAll('img[src^="https:"]').length,0,'Initial render must not download covers before preferences load');
  window.dispatchEvent(new window.Event('pywebviewready'));await settle();
  assert.equal(doc.querySelectorAll('img[src^="https:"]').length,0);
  assert.match($('loadoutSummary').textContent,/1 etkin mod/);
  doc.dispatchEvent(new window.KeyboardEvent('keydown',{key:'k',ctrlKey:true,bubbles:true}));
  assert.equal($('commandDialog').open,true);assert.equal(doc.activeElement,$('commandSearch'));
  $('commandSearch').value='cig ahri';$('commandSearch').dispatchEvent(new window.Event('input'));
  assert.equal($('commandResults').children.length,2,'Search includes installed and discoverable mods');assert.match($('commandResults').textContent,/Çığ Ahri/);
  assert.match($('commandResults').lastChild.textContent,/Keşfet/);
  $('commandSearch').dispatchEvent(new window.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  assert.equal($('commandDialog').open,false);assert.equal($('detailDialog').open,true);
  $('detailDialog').close();click('#searchShortcut');
  $('commandSearch').value='zzzz';$('commandSearch').dispatchEvent(new window.Event('input'));
  assert.equal($('commandEmpty').hidden,false);assert.equal($('commandSearch').hasAttribute('aria-activedescendant'),false);
  $('commandSearch').value='';$('commandSearch').dispatchEvent(new window.Event('input'));
  $('commandSearch').dispatchEvent(new window.KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true}));
  assert.equal($('commandSearch').getAttribute('aria-activedescendant'),'command-option-1');
  click('#closeCommand');click('[data-page="assistants"]');
  $('dataSaver').checked=false;$('dataSaver').dispatchEvent(new window.Event('change'));await settle();
  assert(doc.querySelectorAll('img[src^="https:"]').length>0);
  $('dataSaver').checked=true;$('dataSaver').dispatchEvent(new window.Event('change'));await settle();
  assert.equal(doc.querySelectorAll('img[src^="https:"]').length,0);
  mod.enabled=false;state.revision='two';await timers.get(3000)();
  assert.equal($('loadoutState').textContent,'Henüz mod seçilmedi');
  disconnected=true;await timers.get(3000)();assert.equal($('bridgeNotice').hidden,false);
  disconnected=false;click('#retryConnection');await settle();assert.equal($('bridgeNotice').hidden,true);
  click('[data-page="profiles"]');click('#profileCards .primary');await settle();
  assert.equal(calls.length,0,'Unresolved profile may not apply same-ID wrong package');
  assert.match($('status').textContent,/doğru paket/);
  assert.deepEqual(errors,[]);
  console.log('2.0 UI: offline covers, Turkish command search, keyboard navigation, data saver, external selection sync, reconnect and unresolved profiles passed.');
}finally{window.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
