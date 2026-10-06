/**
 * @name OKDEV-Guide
 * @author OKDEV
 * @description Optional champion-lock Mobalytics guide controls.
 */
(() => {
  'use strict';
  if (typeof document === 'undefined' || window.__okdevGuideLoaded) return;
  window.__okdevGuideLoaded = true;
  let bridge, host, panel, trigger, champion, detail, toggle, show, message, shortcut;
  let timer, waiting, lastReply = 0, expanded = false, currentPhase = null;
  const allowed = new Set(['Lobby', 'Matchmaking', 'ReadyCheck', 'ChampSelect']);
  const el = (tag, className, text) => {
    const node = document.createElement(tag); if (className) node.className = className;
    if (text !== undefined) node.textContent = text; return node;
  };
  function send(type, values = {}) {
    if (!bridge?.ready) { message.textContent = 'OKDEV bağlantısı bekleniyor.'; return; }
    bridge.send({type, ...values});
  }
  function request() { if (bridge?.ready && !document.hidden) send('guide-request'); }
  function render(data) {
    if (!data || data.type !== 'guide-state') return;
    lastReply = Date.now();
    const guide = data.guide || {}, pick = guide.pick;
    currentPhase = guide.phase;
    host.hidden = !allowed.has(currentPhase);
    toggle.checked = !!data.enabled;
    trigger.classList.toggle('enabled', !!data.enabled);
    trigger.textContent = data.enabled && pick ? pick.champion.name + ' · Rehber' : 'Mobalytics · ' + (data.enabled ? 'Açık' : 'Kapalı');
    champion.textContent = pick ? pick.champion.name : 'Şampiyonunu kilitle';
    detail.textContent = pick ? (pick.role_label || 'Build rehberi') : 'Seçimin kesinleşince build’in hazırlanır.';
    show.disabled = !data.enabled || !pick;
    shortcut.textContent = data.hotkey || 'Ctrl+Shift+B';
    message.textContent = data.error || data.companion?.error || (data.enabled ? 'Maç başlayınca gizlenir. Oyunda kısayolla aç.' : 'Kullanmak istediğinde rehberi etkinleştir.');
  }
  function mount() {
    host = el('div'); host.id = 'okdev-guide-widget'; host.hidden = true;
    const root = host.attachShadow({mode:'open'}), style = el('style');
    style.textContent = `:host{position:fixed;right:248px;bottom:12px;z-index:9998;font-family:'Segoe UI',sans-serif;color:#eee8f7}:host([hidden]){display:none}*{box-sizing:border-box}button{font:inherit;cursor:pointer}button:focus-visible,input:focus-visible{outline:2px solid #c5aaff;outline-offset:3px}.trigger{border:1px solid #665675;background:#17141fea;color:#b8a9c9;border-radius:18px;padding:8px 13px;font-size:11px;box-shadow:0 3px 15px #0005}.trigger.enabled{border-color:#9974c0;color:#d8b7ff}.panel{position:absolute;bottom:43px;right:0;width:260px;background:#18151fed;border:1px solid #554263;border-radius:12px;padding:18px;box-shadow:0 14px 35px #0007}.panel[hidden]{display:none}.heading{font-size:10px;letter-spacing:1.7px;color:#b49bce;margin:0 0 17px}.champion{font-size:18px;font-weight:600;margin-bottom:6px}.detail,.message{font-size:11px;line-height:1.5;color:#b7aabe}.setting{display:flex;align-items:center;justify-content:space-between;font-size:11px;margin:17px 0;padding:13px 0;border-top:1px solid #3c3047;border-bottom:1px solid #3c3047}.setting input{accent-color:#b99ae4;width:17px;height:17px;cursor:pointer}.show{width:100%;border:0;border-radius:7px;background:#b99ae4;color:#251a32;padding:9px;font-size:12px;font-weight:600}.show:disabled{opacity:.4;cursor:default}.message{margin:12px 0}.keys{font-size:10px;color:#c5acd9;display:flex;justify-content:space-between}kbd{font:10px 'Segoe UI',sans-serif;border:1px solid #554263;padding:3px 5px;border-radius:4px}.close{float:right;border:0;background:none;color:#b7aabe;font-size:17px;padding:0 1px}.trigger:hover{background:#2a2034}@media(max-width:1050px){:host{right:215px}}`;
    trigger = el('button','trigger','Mobalytics'); trigger.type = 'button'; trigger.setAttribute('aria-expanded','false'); trigger.setAttribute('aria-controls','guide-panel');
    panel = el('section','panel'); panel.id='guide-panel'; panel.hidden=true; panel.setAttribute('aria-label','OKDEV oyun rehberi');
    const close = el('button','close','×'); close.type='button'; close.setAttribute('aria-label','Rehber menüsünü kapat');
    const setExpanded = value => { expanded=value;panel.hidden=!value;trigger.setAttribute('aria-expanded',String(value));if(value)request(); };
    close.onclick=()=>{setExpanded(false);trigger.focus();}; trigger.onclick=()=>setExpanded(!expanded);
    champion=el('div','champion','Şampiyonunu kilitle'); detail=el('div','detail');
    const setting=el('label','setting','Rehberi etkinleştir');toggle=el('input');toggle.type='checkbox';toggle.onchange=()=>send('guide-toggle',{enabled:toggle.checked});setting.append(toggle);
    show=el('button','show','Build rehberini aç');show.type='button';show.disabled=true;show.onclick=()=>send('guide-show');
    message=el('p','message');message.setAttribute('role','status');
    const keys=el('div','keys','Oyunda aç / gizle');shortcut=el('kbd','','Ctrl+Shift+B');keys.append(shortcut);
    panel.append(close,el('div','heading','OKDEV / MOBALYTICS'),champion,detail,setting,show,message,keys);
    root.append(style,panel,trigger);document.body.append(host);
    root.addEventListener('keydown',event=>{if(event.key==='Escape'){setExpanded(false);trigger.focus();event.stopPropagation();}});
  }
  function start() {
    if (!document.body || !window.__okdevBridge) { waiting=setTimeout(start,500);return; }
    bridge=window.__okdevBridge;mount();bridge.subscribe('guide-state',render);
    bridge.subscribe('phase-change', data=>{const phase=data.phase||data.gameflowPhase;if(phase){currentPhase=phase;host.hidden=!allowed.has(phase);}request();});
    bridge.onReady(request);request();
    timer=setInterval(()=>{if(!bridge.ready||Date.now()-lastReply>12000)host.hidden=true;request();},3000);
  }
  window.addEventListener('beforeunload',()=>{clearTimeout(waiting);clearInterval(timer);if(bridge)bridge.unsubscribe('guide-state',render);},{once:true});
  start();
})();
