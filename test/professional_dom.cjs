/* Real frontend, isolated bridge: pagination, queue, previews, portability, close. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM, VirtualConsole} = require('./ui/node_modules/jsdom');
const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const sources = JSON.parse(read('hub/web/sources.json'));
const champions = JSON.parse(read('hub/web/champions.json')).champions;
const calls = [], errors = [], intervals = [];
const installed = Object.fromEntries(Array.from({length:120}, (_, index) => {
  const id = 'local-' + String(index).padStart(3, '0');
  return [id, {id, name:index === 0 ? '<script>unsafe name</script>' : 'Local mod ' + index,
    champion:'Ahri', champion_id:103+index, category:'skins', version:'1.0.0',
    description:'Fixture', enabled:false, installed_at:120-index, cover_key:'cover-'+index, files_available:true}];
}));
const state = {installed, catalog:[], profiles:{}, removed:[], settings:{favorites:[],auto_accept:false},
  preferences:{theme:'dark'}, guide:{}, companion:{}, selection_undo:{available:false},
  downloads:{jobs:[],active:0,revision:0}, activity:{events:[],warning:''}, warning:''};
const ok = value => ({ok:true,result:value});
const record = name => async (...args) => {calls.push([name,...args]);return ok();};
const api = {
  snapshot:async()=>structuredClone(state),
  diagnostics:async()=>ok({version:'1.5.0',checked_at:new Date().toISOString(),note:'Local check',checks:[],storage:[{id:'mods',name:'Mod dosyaları',bytes:2048,files:2,complete:true},{id:'backups',name:'Yerel yedekler',bytes:4096,files:4,complete:false}]}),
  guide_state:async()=>({guide:{},companion:{},preferences:state.preferences}),
  cover_previews:async ids=>{calls.push(['covers',ids]);return Object.fromEntries(ids.map(id=>[id,{key:installed[id].cover_key,data:'data:image/jpeg;base64,fixture'}]));},
  enqueue_download:async(id,source)=>{calls.push(['enqueue',id,source]);const job={id:'job-1',mod_id:id,name:'Queued fixture',status:'queued',received:0,total:0};state.downloads.jobs.push(job);return ok(job);},
  downloads_status:async()=>structuredClone(state.downloads),
  cancel_queued_download:async id=>{calls.push(['cancel',id]);state.downloads.jobs.find(j=>j.id===id).status='cancelled';return ok();},
  retry_download:async id=>{calls.push(['retry',id]);state.downloads.jobs.find(j=>j.id===id).status='queued';return ok();},
  clear_download_history:async()=>{state.downloads.jobs=state.downloads.jobs.filter(j=>['queued','downloading','installing'].includes(j.status));return ok();},
  preview_selection:async(ids,mode)=>{calls.push(['preview',ids,mode]);const before=Object.values(installed).filter(m=>m.enabled).map(m=>m.id);const after=mode==='replace'?ids:mode==='disable'?before.filter(id=>!ids.includes(id)):[...new Set([...before,...ids])];return ok({revision:'fixture-revision',requested:ids,mode,before,after,changed:JSON.stringify(before)!==JSON.stringify(after),enable:after.filter(id=>!before.includes(id)).map(id=>installed[id]),disable:before.filter(id=>!after.includes(id)).map(id=>installed[id])});},
  apply_selection:async(ids,mode,revision)=>{calls.push(['apply',ids,mode,revision]);for(const item of Object.values(installed)){if(mode==='replace')item.enabled=ids.includes(item.id);else if(ids.includes(item.id))item.enabled=mode==='enable';}state.selection_undo.available=true;return ok();},
  undo_selection:async()=>{calls.push(['undo']);for(const item of Object.values(installed))item.enabled=false;state.selection_undo.available=false;return ok();},
  choose_profile:async()=>ok({name:'Portable fixture',missing:1,different_versions:0,mods:[{id:'not-installed',name:'Missing appearance',available:false}]}),
  import_profile:async()=>{calls.push(['import-profile']);state.profiles.portable={name:'Portable fixture',mods:['not-installed']};return ok({id:'portable',missing:1});},
  export_profile:async id=>{calls.push(['export-profile',id]);return ok({saved:true});},
  minimize_window:record('minimize'),close_window:record('close'),
  favorite:record('favorite'),save_profile:record('save-profile'),
  inspect_backup:async id=>ok({id,name:'Old fixture',version:'1.0.0',bytes:2048,files:2,installed:true}),
  export_backup:async id=>{calls.push(['export-backup',id]);return ok({saved:true});},
};
const html=read('hub/web/index.html').replace('/*APP_CSS*/',read('hub/web/app.css')).replace('/*BOOTSTRAP*/','window.HUB_DATA='+JSON.stringify({sources:Array.isArray(sources)?sources:sources.mods,champions})+';').replace('/*APP_JS*/',read('hub/web/app.js'));
const vc=new VirtualConsole();vc.on('jsdomError',error=>errors.push(error.message));
const dom=new JSDOM(html,{url:'https://okdev.test',runScripts:'dangerously',virtualConsole:vc,pretendToBeVisual:true,beforeParse(window){
  window.matchMedia=()=>({matches:false,addEventListener(){}});window.scrollTo=()=>{};
  window.HTMLElement.prototype.scrollIntoView=function(){};
  window.HTMLDialogElement.prototype.showModal=function(){this.open=true;};window.HTMLDialogElement.prototype.close=function(){this.open=false;};
  window.pywebview={api};
  window.setInterval=(callback,ms)=>{intervals.push({callback,ms});return intervals.length;};
}});
const {window}=dom, document=window.document, $=id=>document.getElementById(id);
const settle=()=>new Promise(resolve=>setTimeout(resolve,25));
const click=async selector=>{const el=typeof selector==='string'?document.querySelector(selector):selector;assert.ok(el,'Missing '+selector);el.click();await settle();};
const named=(host,name)=>[...document.querySelectorAll(host+' button')].find(button=>button.textContent===name);
(async()=>{
  try {
    window.dispatchEvent(new window.Event('pywebviewready'));await settle();
    assert.deepEqual(errors,[]);
    assert.equal(document.querySelectorAll('#catalogGrid .card').length,24);
    assert.equal(document.querySelectorAll('#installedGrid .card').length,24);
    assert.ok(calls.filter(c=>c[0]==='covers').flatMap(c=>c[1]).length<=3,'Home fetches only recent covers');
    await click('[data-page="installed"]');
    assert.ok(calls.filter(c=>c[0]==='covers').every(c=>c[1].length<=48));
    assert.ok(calls.filter(c=>c[0]==='covers').flatMap(c=>c[1]).length<=27,'First page never reads all 120 covers');
    assert.equal(document.querySelector('#installedGrid script'),null,'Untrusted mod names are plain text');
    await click('#moreInstalled');assert.equal(document.querySelectorAll('#installedGrid .card').length,48);
    $('installedSearch').value='Local mod 119';$('installedSearch').dispatchEvent(new window.Event('input'));await settle();
    assert.equal(document.querySelectorAll('#installedGrid .card').length,1);assert.equal($('moreInstalled').hidden,true);
    $('installedSearch').value='';$('installedSearch').dispatchEvent(new window.Event('input'));await settle();
    assert.equal(document.querySelectorAll('#installedGrid .card').length,24,'Search resets pagination');
    await click('#selectVisible');assert.match($('bulkCount').textContent,/24 mod/);
    $('installedCategory').value='ui';$('installedCategory').dispatchEvent(new window.Event('change'));
    assert.equal(document.querySelectorAll('#installedGrid .card').length,0,'Installed category filter applies');
    assert.match($('bulkCount').textContent,/24 seçim bu görünümün dışında/,'Hidden bulk selections are explicit');
    await click(named('#installedGrid','Filtreleri temizle'));
    assert.equal($('installedCategory').value,'');
    assert.equal(document.querySelectorAll('#installedGrid .card').length,24);
    await click('#bulkEnable');assert.equal($('selectionDialog').open,true);
    assert.equal(calls.filter(c=>c[0]==='apply').length,0,'Bulk preview never applies automatically');
    await click('#cancelSelection');assert.equal(Object.values(installed).filter(m=>m.enabled).length,0);
    await click('#bulkEnable');await click('#confirmSelection');
    assert.equal(Object.values(installed).filter(m=>m.enabled).length,24);
    assert.equal(calls.find(c=>c[0]==='apply')[3],'fixture-revision');
    assert.equal($('undoSelection').hidden,false);await click('#undoSelection');
    assert.equal(Object.values(installed).filter(m=>m.enabled).length,0);
    assert.equal($('undoSelection').hidden,true);assert.equal($('bulkEnable').disabled,true);
    const selectionFocus = document.querySelector('#installedGrid .card-select input');
    const focusedModId = selectionFocus.closest('.card').dataset.modId;
    selectionFocus.focus();
    state.downloads.jobs=[{id:'background-completion',mod_id:'local-000',name:'Completed fixture',status:'completed'}];
    await intervals.find(item=>item.ms===1000).callback();
    assert.equal(document.activeElement.type,'checkbox','Background completion preserves keyboard selection focus');
    assert.equal(document.activeElement.closest('.card').dataset.modId,focusedModId);
    state.downloads.jobs=[];await intervals.find(item=>item.ms===1000).callback();
    await click('[data-page="library"]');await click('#catalogGrid .primary');
    assert.ok(calls.some(c=>c[0]==='enqueue'&&c[2]==='curated'));
    assert.match($('status').textContent,/indirme kuyruğuna eklendi/);
    const dismissNotice = document.querySelector('#status .dismiss-notice');
    assert.equal(dismissNotice.getAttribute('aria-label'),'Bildirimi kapat');
    dismissNotice.focus(); await click(dismissNotice);
    assert.equal($('status').textContent,'');
    assert.notEqual(document.activeElement,document.body,'Dismissing a focused notice restores a useful focus target');
    assert.equal($('main').getAttribute('aria-busy'),'false');
    await click('[data-page="downloads"]');assert.equal(document.querySelectorAll('.download-job.queued').length,1);
    await click('.job-actions button');assert.equal(document.querySelectorAll('.download-job.cancelled').length,1);
    await click('.job-actions button');assert.equal(document.querySelectorAll('.download-job.queued').length,1);
    document.querySelector('.job-actions button').focus();
    state.downloads.jobs[0].status='failed';state.downloads.jobs[0].error='Fixture connection failed';
    await intervals.find(item=>item.ms===1000).callback();
    assert.equal(document.activeElement.textContent,'Yeniden dene','Queue status replacement keeps a useful keyboard target');
    assert.match($('queueSummary').textContent,/tamamlanamadı/);assert.match($('downloadJobs').textContent,/Fixture connection failed/);
    await click('#clearDownloads');assert.equal(state.downloads.jobs.length,0);
    // A delayed poll must not repaint preferences saved after it began.
    let releaseGuide;
    const normalGuide=api.guide_state;
    api.guide_state=()=>new Promise(resolve=>{releaseGuide=resolve;});
    const polling=intervals.find(item=>item.ms===2000).callback();
    await click('[data-page="installed"]');await click('#installedGrid .favorite');
    releaseGuide({guide:{},companion:{},preferences:{theme:'light'}});await polling;
    assert.equal(document.documentElement.dataset.theme,'dark','Stale polling cannot undo newer preferences');
    api.guide_state=normalGuide;
    state.removed=Array.from({length:45},(_,i)=>({backup_id:'backup-'+i,name:'Old fixture '+i,version:'1.0.0',category:'skins',reason:'update'}));
    await click('#installedGrid .favorite');
    assert.equal(document.querySelectorAll('#recovery .recovery-row').length,20,'Backup list is bounded');
    await click(named('#recovery','Daha fazla yedek göster'));
    assert.equal(document.querySelectorAll('#recovery .recovery-row').length,40);
    await click(named('#recovery','Yedeği incele'));
    assert.equal($('backupDialog').open,true);assert.match($('backupDialog').textContent,/2.0 KB/);
    assert.match($('backupDialog').textContent,/şu anda kütüphanende var/);
    await click(named('#backupDialog','Paket olarak kaydet'));
    assert.ok(calls.some(call=>call[0]==='export-backup'&&call[1]==='backup-0'));
    $('backupDialog').close();
    installed['local-119'].files_available=false;
    await click('#installedGrid .favorite');
    $('installedFilter').value='missing';$('installedFilter').dispatchEvent(new window.Event('change'));
    assert.equal(document.querySelectorAll('#installedGrid .card').length,1,'Missing folders can be filtered');
    await click(named('#installedGrid','Dosyaları eksik'));
    assert.match($('detailContent').textContent,/dosya klasörü bulunamadı/);
    assert.equal(named('#detailContent','Etkinleştir'),undefined,'Missing files are not offered for activation');
    $('detailDialog').close();
    installed['local-119'].files_available=true;
    $('installedFilter').value='all';$('installedFilter').dispatchEvent(new window.Event('change'));
    await click('[data-page="profiles"]');await click(named('#profileHost','Profil dosyası içe aktar'));
    assert.equal($('portableProfileDialog').open,true);assert.equal(calls.some(c=>c[0]==='import-profile'),false);
    document.dispatchEvent(new window.KeyboardEvent('keydown',{key:'k',ctrlKey:true,bubbles:true}));
    assert.equal($('profiles').hidden,false,'Search shortcut never navigates behind a modal');
    assert.match($('portableProfileMods').textContent,/Kütüphanende yok/);
    await click('#confirmPortableProfile');assert.equal($('portableProfileDialog').open,false);
    assert.match($('profileCards').textContent,/1 mod eksik/);
    const applies=calls.filter(c=>c[0]==='apply').length;await click('#profileCards .primary');assert.equal(calls.filter(c=>c[0]==='apply').length,applies);
    await click('#profileCards .profile-card-heading button');await click(named('#editProfileDialog','Profil dosyasını dışa aktar'));
    assert.ok(calls.some(c=>c[0]==='export-profile'&&c[1]==='portable'));
    $('editProfileDialog').close();
    await click('[data-page="diagnostics"]');await click('#checkDiagnostics');
    assert.equal($('storageSummary').hidden,false);
    assert.equal(document.querySelectorAll('.storage-card').length,2);
    assert.match($('storageGrid').textContent,/En az 4.0 KB/,'Incomplete scan is explicitly a lower bound');
    await click('#showStorageBackups');
    assert.equal($('installed').hidden,false);assert.equal($('recovery').open,true);
    assert.equal(document.activeElement,document.querySelector('#recovery summary'));
    window.dispatchEvent(new window.Event('okdev-close-request'));assert.equal($('closeWindowDialog').open,true);
    assert.ok([...document.querySelectorAll('dialog')].filter(dialog=>dialog.querySelector('h2')).every(dialog=>document.getElementById(dialog.getAttribute('aria-labelledby'))),'Every dialog has an accessible heading');
    await click('#minimizeWindow');assert.ok(calls.some(c=>c[0]==='minimize'));assert.equal($('closeWindowDialog').open,false);
    window.dispatchEvent(new window.Event('okdev-close-request'));await click('#stopAndClose');assert.ok(calls.some(c=>c[0]==='close'));
    assert.equal($('stopAndClose').disabled,true);assert.match($('closeWindowTitle').textContent,/durduruluyor/);
    assert.deepEqual(errors,[],'No frontend errors in professional workflows');
    console.log('Professional UI workflows passed: 120-mod pagination, bounded covers, safe text, bulk preview/undo, background queue retry/cancel, portable profiles and safe close.');
  } finally {window.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
