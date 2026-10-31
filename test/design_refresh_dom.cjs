'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM,VirtualConsole}=require('./ui/node_modules/jsdom');
const root=path.resolve(__dirname,'..'),read=f=>fs.readFileSync(path.join(root,f),'utf8');
const errors=[],calls=[];
const installed={
  first:{id:'first',name:'Uzun Türkçe Mod Adı — Karanlık Vadi Şampiyon Koleksiyonu',category:'ui',version:'1.0.0',enabled:true,files_available:true,installed_at:2},
  second:{id:'second',name:'Yazı tipi',category:'fonts',version:'1.0.0',enabled:true,files_available:true,installed_at:1},
};
const state={installed,catalog:[],profiles:{default:{name:'Varsayılan',mods:['first','second']},minimal:{name:'Sade',mods:['second']},missing:{name:'Eksik',mods:['gone'],missing:1}},settings:{favorites:[]},preferences:{theme:'dark',data_saver:true},removed:[],guide:{connected:false},companion:{},downloads:{jobs:[]},activity:{events:[]}};
let failure=false,release=null;
const api={snapshot:async()=>structuredClone(state),guide_state:async()=>({guide:state.guide,companion:state.companion,preferences:state.preferences}),
  enable:async(id,value)=>{calls.push(['enable',id,value]);if(release)await new Promise(r=>release=r);if(failure)return {ok:false,error:'Disk dolu. Seçim kaydedilemedi.'};installed[id].enabled=value;return {ok:true};},
  favorite:async(id,value)=>{state.settings.favorites=value?[id]:[];return {ok:true};},
  apply_profile:async(id)=>{calls.push(['profile',id]);if(failure)return {ok:false,error:'Profil kaydedilemedi.'};Object.values(installed).forEach(m=>m.enabled=state.profiles[id].mods.includes(m.id));return {ok:true};},
  choose_mod:async()=>null,
  select_mod:async(path)=>{calls.push(['drop',path]);return {name:'ornek.fantome',suggested:{id:'ornek',name:'Örnek paket',category:'ui',version:'1.0.0'}};},
  bind_dropzones:async()=>true,
};
const boot={sources:[{id:'remote',name:'Uzak koleksiyon',champion:'Ahri',category:'skins',version:'1.0.0'}],champions:[]};
const html=read('hub/web/index.html').replace('/*APP_CSS*/',read('hub/web/app.css')).replace('/*BOOTSTRAP*/','window.HUB_DATA='+JSON.stringify(boot)+';').replace('/*APP_JS*/',read('hub/web/app.js'));
const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
const dom=new JSDOM(html,{url:'https://okdev.test',runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){w.matchMedia=()=>({matches:false,addEventListener(){}});w.scrollTo=()=>{};w.HTMLDialogElement.prototype.showModal=function(){this.open=true};w.HTMLDialogElement.prototype.close=function(){this.open=false};w.pywebview={api};}});
const w=dom.window,d=w.document,$=id=>d.getElementById(id),settle=()=>new Promise(r=>setTimeout(r,30));
const click=async selector=>{d.querySelector(selector).click();await settle();};
const choose=async id=>{$('homeProfile').value=id;$('homeProfile').dispatchEvent(new w.Event('change'));await settle();};
const drop=async paths=>{w.dispatchEvent(new w.CustomEvent('okdev-file-drop',{detail:{paths}}));await settle();};
(async()=>{try{
  await settle();assert.deepEqual(errors,[]);
  assert.equal($('homeProfile').value,'default');assert.equal($('activeCount').textContent,'2');
  assert.equal($('homeProfile').querySelector('[value="missing"]').disabled,true);
  assert.match($('gamePhase').textContent,/bekleniyor/);assert.match($('connection').textContent,/hazır/);
  failure=true;await click('#homeRecent .recent-toggle');
  assert.equal(installed.first.enabled,true);assert.equal(d.querySelector('#homeRecent .recent-toggle').getAttribute('aria-pressed'),'true');
  assert.match($('status').textContent,/Disk dolu/);assert.equal($('activeCount').textContent,'2');
  failure=false;release=true;const toggle=d.querySelector('#homeRecent .recent-toggle');toggle.focus();toggle.click();await settle();
  assert.equal(toggle.disabled,true);const before=calls.length;toggle.click();assert.equal(calls.length,before);
  const finish=release;release=null;finish();await settle();
  assert.equal(installed.first.enabled,false);assert.equal($('activeCount').textContent,'1');assert.equal($('homeProfile').value,'minimal');
  assert(d.activeElement.closest('.recent-item'),'Focus stays on the card after successful rerender');
  failure=true;await click('#loadoutItems .mod-switch');assert.equal(installed.second.enabled,true);
  assert.equal(d.querySelector('#loadoutItems .mod-switch').getAttribute('aria-checked'),'true');
  await choose('default');assert.equal($('homeProfile').value,'minimal');assert.equal($('activeCount').textContent,'1');
  failure=false;await choose('default');assert.equal($('homeProfile').value,'default');assert.equal($('activeCount').textContent,'2');
  await click('#homeRecent .favorite');assert.equal(state.settings.favorites[0],'first');
  await click('#searchShortcut');$('commandSearch').value='uzak koleksiyon';$('commandSearch').dispatchEvent(new w.Event('input'));
  assert.equal($('commandResults').children.length,1);assert.match($('commandResults').textContent,/Keşfet/);
  await click('#closeCommand');await drop(['test.rar']);assert.match($('status').textContent,/Yalnızca/);assert.equal(calls.filter(c=>c[0]==='drop').length,0);
  await drop(['a.zip','b.zip']);assert.match($('status').textContent,/Tek bir/);
  await drop([null]);assert.match($('status').textContent,/Dosya seç/);
  await drop(['C:\\fixtures\\ornek.fantome']);assert.equal($('publish').hidden,false);assert.equal($('selected').textContent,'ornek.fantome');
  assert.equal($('modForm').elements.namedItem('name').value,'Örnek paket');assert.equal($('modForm').querySelector('[type=submit]').disabled,false);
  await click('#choose');assert.equal($('selected').textContent,'ornek.fantome','Cancelled picker preserves a dropped draft');
  await click('[data-page="home"]');Object.defineProperty(w,'innerWidth',{value:850,configurable:true});
  $('menuToggle').style.display='inline-flex'; // jsdom has no responsive layout engine.
  await click('#menuToggle');assert.equal($('menuToggle').getAttribute('aria-expanded'),'true');
  d.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));assert.equal($('menuToggle').getAttribute('aria-expanded'),'false');assert.equal(d.activeElement.id,'menuToggle');
  state.patcher={ready:false,message:'LTK oyun derlemesini desteklemiyor.'};await click('#retryConnection');
  assert.equal($('patcherNotice').hidden,false);assert.match($('loadoutTitle').textContent,/hazır değil/);
  assert.match($('loadoutState').textContent,/LTK bekleniyor/);assert.equal($('loadoutState').classList.contains('ready'),false);
  state.patcher={ready:true,message:'Uyumlu'};await click('#retryConnection');assert.equal($('patcherNotice').hidden,true);
  assert.deepEqual(errors,[]);console.log('Design refresh: real-state cards, failure rollback, duplicate-click lock, focus, profiles, catalog search, favorites, drop validation, retained drafts, menu keyboard and LTK blocking status passed.');
}finally{w.close();}})().catch(e=>{console.error(e);process.exitCode=1});
