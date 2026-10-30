/* Isolated League-host contract used by DOM and WebView tests. No real bridge. */
(function () {
  const callbacks = new Map(), calls = [], errors = [];
  const settings = {threshold: .5, monitorAutoResumeTimeout: 60, autostart: false,
    hideEmptyCategories: false, gamePath: 'C:\\Riot Games\\League of Legends\\Game', gamePathValid: true, version: '2.0.0'};
  const nativeAdd = window.addEventListener.bind(window), nativeRemove = window.removeEventListener.bind(window);
  const listeners = new Map();
  window.addEventListener = function (name, callback, options) {
    if (['resize', 'scroll'].includes(name)) {
      if (!listeners.has(name)) listeners.set(name, new Set());
      listeners.get(name).add(callback);
    }
    return nativeAdd(name, callback, options);
  };
  window.removeEventListener = function (name, callback, options) {
    listeners.get(name)?.delete(callback);
    return nativeRemove(name, callback, options);
  };
  window.__settingsQa = {
    calls, errors, settings, holdSave: false, failSave: false, failList: false, diagnosticErrors: [],
    emit: (name, payload) => callbacks.get(name)?.(payload),
    listenerCount: () => [...listeners.values()].reduce((sum, set) => sum + set.size, 0),
    open: () => window.dispatchEvent(new CustomEvent('okdev-open-settings', {detail:{navItem: document.getElementById('qa-nav')}})),
  };
  window.addEventListener('error', e => errors.push(e.message));
  window.addEventListener('unhandledrejection', e => errors.push(String(e.reason)));
  window.OKDEVI18n = {
    setting: 'tr', language: 'tr', direction:'ltr', languages: {tr:'Türkçe',en:'English',de:'Deutsch',fr:'Français'},
    t: (text, vars) => (window.__qaLocale?.[text] || text).replace(/\{(\w+)\}/g, (m,k) => vars && k in vars ? vars[k] : m),
    tAny: text => window.__qaLocale?.[text] || text,
  };
  const deliver = (name, payload) => queueMicrotask(() => callbacks.get(name)?.(payload));
  window.__okdevBridge = {
    ready: true, port: 50000,
    subscribe: (name, callback) => callbacks.set(name, callback),
    onReady: callback => callback(),
    send: payload => {
      calls.push(payload);
      if (payload.type === 'settings-save' && window.__settingsQa.throwSave) throw new Error('QA: Bridge disconnected');
      if (payload.type === 'settings-request') deliver('settings-data', {...settings});
      if (payload.type === 'diagnostics-request') deliver('diagnostics-data', {errors:window.__settingsQa.diagnosticErrors,path:'QA'});
      if (payload.type === 'path-validate') deliver('path-validation-result', {gamePath:payload.gamePath, valid:true});
      if (payload.type === 'settings-save' && !window.__settingsQa.holdSave) {
        if (!window.__settingsQa.failSave) Object.assign(settings, payload);
        deliver('settings-saved', {requestId:payload.requestId, success: !window.__settingsQa.failSave, error: window.__settingsQa.failSave ? 'QA: Disk full' : ''});
      }
      if (payload.type === 'request-manage-category-mods') {
        deliver('manage-category-mods-response', {category:payload.category, error:window.__settingsQa.failList ? 'QA: Listing failed' : null, mods:[
          {name:'QA Midnight Arena',displayName:'QA Midnight Arena',relativePath:'maps/qa-midnight',id:'maps/qa-midnight'},
          {name:'QA Long mod name — ' + 'A'.repeat(90),relativePath:'maps/qa-long',id:'maps/qa-long'},
        ]});
      }
      if (payload.type === 'delete-category-mod' || payload.type === 'rename-category-mod') {
        deliver(payload.type === 'delete-category-mod' ? 'category-mod-deleted' : 'category-mod-renamed',
          {category:payload.category, modName:payload.modName, success:false, error:'QA: Permission denied'});
      }
      if (payload.type === 'add-custom-mods-champion-selected' && payload.action === 'list') {
        deliver('champions-list-response', {champions:[{id:103,name:'Ahri'},{id:157,name:'Yasuo'}]});
      }
      if (payload.type === 'add-custom-mods-skin-selected' && payload.action === 'list' && !window.__settingsQa.holdSkins) {
        const base = Number(payload.championId) * 1000;
        deliver('champion-skins-response', {championId:payload.championId, championName:payload.championId===103?'Ahri':'Yasuo', skins:[
          {skinId:base,name:'QA Classic',isChroma:false},
          {skinId:base+1,name:'QA Midnight',isChroma:false},
          {skinId:base+2,name:'QA Midnight Violet',isChroma:true,baseSkinId:base+1},
        ]});
      }
    },
  };
})();
