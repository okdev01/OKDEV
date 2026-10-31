'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM,VirtualConsole}=require('./ui/node_modules/jsdom');
const sent=[],sockets=[],ticks=[],errors=[];
const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
const dom=new JSDOM('<!doctype html><body><div class="skin-name-text">Solmuş Gül Zeri</div></body>',{url:'https://okdev.test',runScripts:'outside-only',virtualConsole:vc});
const w=dom.window;
w.fetch=async()=>({ok:true,text:async()=>'50000'});
w.setInterval=fn=>{ticks.push(fn);return ticks.length};w.clearInterval=()=>{};
class Socket extends w.EventTarget {static OPEN=1;static CONNECTING=0;constructor(){super();this.readyState=0;sockets.push(this)}send(s){sent.push(JSON.parse(s))}close(){this.readyState=3}}
w.WebSocket=Socket;
const settle=()=>new Promise(r=>setTimeout(r,25));
(async()=>{try{
  w.eval(fs.readFileSync(path.join(__dirname,'../Pengu Loader/plugins/OKDEV-SkinMonitor/index.js'),'utf8'));
  await settle();assert.equal(sockets.length,1);const socket=sockets[0];socket.readyState=1;socket.dispatchEvent(new w.Event('open'));await settle();
  assert(sent.some(p=>p.type==='skin-hover'&&p.skin==='Solmuş Gül Zeri'));
  assert(sent.some(p=>p.type==='skin-sync'&&p.skin==='Solmuş Gül Zeri'));
  w.document.querySelector('.skin-name-text').textContent='Fırtınanın Efendisi Ornn';
  ticks.forEach(fn=>fn());await settle();
  const changed=sent.find(p=>p.type==='skin-hover'&&p.skin==='Fırtınanın Efendisi Ornn');
  assert(changed,'Changing champion sends a typed skin selection');
  assert(sent.filter(p=>p.skin).every(p=>typeof p.type==='string'));
  const count=sent.length;ticks.forEach(fn=>fn());assert.equal(sent.length,count,'Unchanged labels do not flood the bridge');
  assert.deepEqual(errors,[]);
  if(process.argv[2])fs.writeFileSync(process.argv[2],JSON.stringify(sent.filter(p=>p.skin),null,2));
  console.log('Actual SkinMonitor plugin: initial hover, reconnect sync, Zeri-to-Ornn exchange and duplicate suppression passed.');
}finally{w.dispatchEvent(new w.Event('beforeunload'));w.close();}})().catch(e=>{console.error(e);process.exitCode=1});
