/* OKDEV's in-page navigation. The official page keeps its own content and links.
   No Python bridge, account data access or build scraping is used here. */
(() => {
  'use strict';
  if (location.hostname !== 'mobalytics.gg' || !location.pathname.startsWith('/lol/champions/')) return;
  const previous = document.getElementById('okdev-guide-navigation');
  if (previous) {
    const key = previous.shadowRoot?.querySelector('.key');
    if (key) key.textContent = window.OKDEV_GUIDE_HOTKEY || 'Ctrl+Shift+B';
    return;
  }
  const host = document.createElement('div'); host.id = 'okdev-guide-navigation';
  host.style.cssText = 'position:fixed;top:0;left:0;right:0;height:46px;z-index:2147480000;';
  const root = host.attachShadow({mode:'open'}), style = document.createElement('style');
  style.textContent = `*{box-sizing:border-box}.bar{height:46px;display:flex;align-items:center;gap:5px;background:#19151fee;border-bottom:1px solid #665075;padding:0 10px;color:#d9c9ed;font:11px 'Segoe UI',sans-serif;box-shadow:0 3px 16px #0005}.brand{font-size:10px;font-weight:750;letter-spacing:1px;margin-right:6px;color:#c1a2ed}button{font:inherit;color:#d9c9ed;background:transparent;border:1px solid transparent;border-radius:6px;padding:7px 9px;cursor:pointer;white-space:nowrap}button:hover,button:focus-visible{background:#3a2b4a;border-color:#9272b1;outline:none}.key{margin-left:auto;color:#a999b7;font-size:9px;white-space:nowrap}.feedback{display:none;position:absolute;top:49px;left:10px;background:#251e30;border:1px solid #665075;color:#d9c9ed;font:11px 'Segoe UI',sans-serif;padding:10px 12px;border-radius:7px}.feedback.show{display:block}@media(max-width:400px){.bar{gap:1px;padding:0 7px}.brand{font-size:9px;margin-right:3px}button{padding:7px 6px}.key{font-size:8px}}`;
  const bar = document.createElement('nav'); bar.className = 'bar'; bar.setAttribute('aria-label','OKDEV rehber gezintisi');
  const brand = document.createElement('span'); brand.className='brand';brand.textContent='OKDEV';bar.append(brand);
  const feedback = document.createElement('div');feedback.className='feedback';feedback.setAttribute('role','status');
  let dismiss;
  function jump(heading, manual=false) {
    const names = new Set([heading, 'aram ' + heading]);
    if (heading === 'ability order') { names.add('skill order'); names.add('aram skill order'); names.add('aram abilities'); }
    const target = [...document.querySelectorAll('h3'), ...document.querySelectorAll('h2,h4')].find(e=>names.has(e.textContent.trim().toLowerCase()));
    if (target) { target.style.scrollMarginTop='180px';target.scrollIntoView({behavior:'auto',block:'start'});return true; }
    if (manual) {feedback.textContent='Sayfa henüz hazır değil. Birazdan tekrar dene.';feedback.classList.add('show');clearTimeout(dismiss);dismiss=setTimeout(()=>feedback.classList.remove('show'),4000);}
    return false;
  }
  [['Rünler','runes'],['Eşyalar','items'],['Yetenek','ability order']].forEach(([label,heading])=>{
    const button=document.createElement('button');button.type='button';button.textContent=label;button.onclick=()=>jump(heading,true);bar.append(button);
  });
  const key=document.createElement('span');key.className='key';key.textContent=window.OKDEV_GUIDE_HOTKEY||'Ctrl+Shift+B';key.title='Rehberi göster / gizle';bar.append(key);
  root.append(style,bar,feedback);document.documentElement.append(host);
  let attempts=0, stopped=false;
  // Stop automatic scrolling as soon as the user interacts with the page.
  const stop=()=>{stopped=true;};
  window.addEventListener('wheel',stop,{once:true,passive:true});window.addEventListener('pointerdown',stop,{once:true,passive:true});
  const timer=setInterval(()=>{if(stopped||!host.isConnected||++attempts>30||jump('runes'))clearInterval(timer);},350);
})();
