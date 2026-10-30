/* Real frontend regressions: all lane/category controls and target-only profiles. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM, VirtualConsole} = require('./ui/node_modules/jsdom');
const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const calls = [], errors = [];
const mod = {id:'ahri',name:'Ahri fixture',champion:'Ahri',champion_id:103,category:'skins',version:'1.0.0',enabled:true,files_available:true,target_skin_ids:[103001,103002],selected_target_skin_id:103002};
const state = {installed:{ahri:mod},catalog:[],profiles:{first:{name:'First target',mods:['ahri'],targets:{ahri:103001}}},removed:[],settings:{favorites:[],auto_accept:false},preferences:{theme:'dark'},guide:{},companion:{},selection_undo:{available:false},downloads:{jobs:[],active:0,revision:0},activity:{events:[],warning:''},warning:''};
const ok = result => ({ok:true,result});
const api = {
  snapshot:async()=>structuredClone(state),
  guide_state:async()=>({guide:{},companion:{},preferences:state.preferences}),
  downloads_status:async()=>structuredClone(state.downloads),
  save_preferences:async changes=>{calls.push(['preferences',changes]);Object.assign(state.preferences,changes);return ok(state.preferences);},
  preview_selection:async(ids,mode,targets)=>{calls.push(['preview',ids,mode,targets]);return ok({revision:'before-target-change',requested:ids,mode,targets,changed:true,enable:[],disable:[],target_changes:[{id:'ahri',name:mod.name,skin_id:targets.ahri}]});},
  apply_selection:async(ids,mode,revision,targets)=>{calls.push(['apply',ids,mode,revision,targets]);mod.selected_target_skin_id=targets.ahri;return ok();},
};
const champions = JSON.parse(read('hub/web/champions.json')).champions;
const html = read('hub/web/index.html').replace('/*APP_CSS*/', read('hub/web/app.css')).replace('/*BOOTSTRAP*/', 'window.HUB_DATA='+JSON.stringify({sources:[],champions})+';').replace('/*APP_JS*/', read('hub/web/app.js'));
const vc = new VirtualConsole();vc.on('jsdomError', e=>errors.push(e.message));
const dom = new JSDOM(html,{url:'https://okdev.test',runScripts:'dangerously',virtualConsole:vc,pretendToBeVisual:true,beforeParse(window){
  window.matchMedia=()=>({matches:false,addEventListener(){}});window.scrollTo=()=>{};
  window.HTMLElement.prototype.scrollIntoView=function(){};
  window.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
  window.HTMLDialogElement.prototype.close=function(){this.open=false;};
  window.pywebview={api};window.setInterval=()=>1;
}});
const {window}=dom, doc=window.document, $=id=>doc.getElementById(id);
const settle=()=>new Promise(resolve=>setTimeout(resolve,30));
(async()=>{try{
  window.dispatchEvent(new window.Event('pywebviewready'));await settle();
  assert.deepEqual(Array.from($('draftLane').options,o=>o.value),['general','top','jungle','mid','adc','support']);
  const categories=['skins','ui','maps','fonts','announcers','voiceover','loading_screen','vfx','sfx','others'];
  for(const id of ['installedCategory','categoryFilter','importCategory']) {
    const values=Array.from($(id).options,o=>o.value);
    for(const category of categories) assert(values.includes(category),`${id} missing ${category}`);
  }
  for(const category of categories) assert(doc.querySelector(`[data-category="${category}"]`));
  $('draftLane').value='top';$('draftLane').dispatchEvent(new window.Event('change'));
  assert.equal($('lanePickEditor').hidden,false);
  $('pickChampion').value='Ahri';$('addPickChampion').click();await settle();
  assert.equal(state.preferences.lane_profiles.top.pick[0],103);
  assert.equal(state.preferences.lane_profiles.jungle.pick.length,0);
  assert(!$('profileCards').textContent.includes('Şu anki seçimlerin'));
  doc.querySelector('#profileCards .primary').click();await settle();
  assert.equal($('selectionDialog').open,true,'Target-only profile changes must open preview');
  assert.match($('selectionChanges').textContent,/103001/);
  assert.deepEqual(JSON.parse(JSON.stringify(calls.find(c=>c[0]==='preview')[3])),{ahri:103001});
  $('confirmSelection').click();await settle();
  assert.equal(mod.selected_target_skin_id,103001);
  assert.deepEqual(JSON.parse(JSON.stringify(calls.find(c=>c[0]==='apply')[4])),{ahri:103001});
  assert($('profileCards').textContent.includes('Şu anki seçimlerin'));
  assert.deepEqual(errors,[]);
  console.log('Audit 2 DOM: five lanes, ten categories, top-lane editing, profile target preview/apply passed');
}finally{window.close();}})().catch(error=>{console.error(error);process.exitCode=1;});
