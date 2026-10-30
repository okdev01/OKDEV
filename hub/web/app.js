'use strict';

// Kept independent of the DOM so search, sorting and updates can be tested.
const HubView = {
  bytes(value) {
    const count = Number.isFinite(value) ? Math.max(0, value) : 0;
    if (count < 1024) return Math.round(count) + ' B';
    if (count < 1048576) return (count / 1024).toFixed(1) + ' KB';
    if (count < 1073741824) return (count / 1048576).toFixed(1) + ' MB';
    return (count / 1073741824).toFixed(1) + ' GB';
  },
  normalize(value) {
    return String(value || '').toLocaleLowerCase('tr').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/ı/g, 'i');
  },
  filter(mods, {term = '', category = '', favorites = [], onlyFavorites = false, status = 'all', sort = 'name'} = {}) {
    const tokens = this.normalize(term).trim().split(/\s+/).filter(Boolean);
    const marked = new Set(favorites);
    return mods.filter(m => (!category || (m.category || 'skins') === category)
      && (!onlyFavorites || marked.has(m.id))
      && (status !== 'enabled' || m.enabled) && (status !== 'disabled' || !m.enabled)
      && (status !== 'favorites' || marked.has(m.id))
      && (status !== 'missing' || m.files_available === false)
      && tokens.every(token => {
        const text = this.normalize([m.name, m.champion, m.author, m.description].join(' '));
        return text.includes(token) || this.normalize([m.name, m.champion].join(' ')).replace(/[\s’'._-]/g, '').includes(token.replace(/[\s’'._-]/g, ''));
      }))
      .sort((a, b) => {
        if (sort === 'favorites' && marked.has(a.id) !== marked.has(b.id)) return marked.has(a.id) ? -1 : 1;
        if (sort === 'recent' && a.installed_at !== b.installed_at) return (b.installed_at || 0) - (a.installed_at || 0);
        if (sort === 'champion') return (a.champion || '').localeCompare(b.champion || '', 'tr') || a.name.localeCompare(b.name, 'tr');
        return a.name.localeCompare(b.name, 'tr');
      });
  },
  newer(candidate, installed) {
    const a = String(candidate).split('.').map(Number), b = String(installed).split('.').map(Number);
    if (![a, b].every(v => v.length >= 3 && v.length <= 5) || [...a, ...b].some(n => !Number.isSafeInteger(n) || n < 0)) return false;
    for (let i = 0; i < Math.max(a.length, b.length); i++) { if ((a[i] || 0) !== (b[i] || 0)) return (a[i] || 0) > (b[i] || 0); }
    return false;
  },
};
if (typeof module !== 'undefined') module.exports = HubView;

if (typeof document !== 'undefined') {
  let state = {catalog: [], installed: {}, settings: {favorites: []}, preferences: {data_saver:true}, guide: {}, companion: {}}, busy = false, api = null;
  let sourceId = null, removeId = null, noticeTimer, selectedFile = false;
  let stateEpoch = 0, snapshotRequest = 0;
  const $ = id => document.getElementById(id);
  const boot = window.HUB_DATA || {sources: [], champions: []};
  if (boot.appearance && typeof boot.appearance === 'object') {
    state.preferences = {...state.preferences, ...boot.appearance};
  }
  const categories = {skins: 'Şampiyon', ui: 'HUD / Arayüz', maps: 'Harita', fonts: 'Yazı tipi', announcers: 'Spiker', voiceover: 'Seslendirme', loading_screen: 'Yükleme ekranı', vfx: 'Görsel efekt', sfx: 'Ses efekti', others: 'Diğer'};
  const titles = {home: 'Oyun alanın', library: 'Keşfet', installed: 'Modlarım', profiles: 'Profiller', assistants: 'Ayarlar', diagnostics: 'Sistem durumu', guides: 'Oyun rehberi', publish: 'Mod ekle', downloads: 'İndirmeler'};
  let currentPage = 'home';
  const selectedMods = new Set();
  let catalogLimit = 24, installedLimit = 24, recoveryLimit = 20, filterSignature = '';
  const coverCache = new Map(), pendingCovers = new Set();
  let commandEntries = [], commandIndex = 0, syncPolling = false;
  let initialized = false, connecting = false;
  const categoryIcons = {skins:'spark',ui:'grid',maps:'map',fonts:'list',announcers:'volume',voiceover:'volume',loading_screen:'layers',vfx:'spark',sfx:'volume',others:'layers'};

  function setConnection(connected) {
    $('connection').textContent = connected ? 'Yerel bağlantı hazır' : 'Bağlantı yenileniyor';
    $('bridgeNotice').hidden = connected;
    document.body.classList.toggle('bridge-offline', !connected);
    document.body.classList.toggle('bridge-ready', connected);
    if (!connected) $('loadingBanner').hidden = true;
  }
  async function readBridge(promise) {
    let timer;
    try {
      return await Promise.race([promise, new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('Uygulama yanıt vermedi. Bağlantıyı yeniden dene.')), 12000);
      })]);
    } finally { clearTimeout(timer); }
  }
  function openCommand() {
    if (document.querySelector('dialog[open]')) return;
    $('commandSearch').value = '';
    renderCommands(); $('commandDialog').showModal(); $('commandSearch').focus();
  }
  function renderCommands() {
    const term = $('commandSearch').value.trim(), tokens = HubView.normalize(term).split(/\s+/).filter(Boolean);
    const entries = Object.entries(titles).map(([id, name]) => ({name, detail:'Sayfa', kind:'page', action:()=>{
      page(id); $('title').tabIndex=-1; $('title').focus({preventScroll:true});
    }}));
    for (const mod of Object.values(state.installed)) entries.push({name:mod.name, detail:[mod.champion,categories[mod.category || 'skins'],mod.enabled?'Etkin':'Kapalı'].filter(Boolean).join(' · '), kind:'mod', action:()=>showDetail(mod,true)});
    commandEntries = entries.filter(item => tokens.every(token => HubView.normalize(item.name+' '+item.detail).includes(token)))
      .sort((a,b)=>term ? Number(b.kind==='mod')-Number(a.kind==='mod') : 0).slice(0,12);
    commandIndex=0; const target=$('commandResults'); target.replaceChildren();
    commandEntries.forEach((entry,index)=>{
      const row=button('',()=>chooseCommand(index)); row.id='command-option-'+index; row.className='command-result';
      row.tabIndex=-1; row.setAttribute('role','option');
      const text=element('span','command-result-text'); text.append(element('strong','',entry.name),element('small','',entry.detail));
      row.append(element('span','command-icon',entry.kind==='mod'?'◇':'↗'),text,element('span','command-enter','↵'));
      target.append(row);
    });
    $('commandEmpty').hidden=commandEntries.length>0; updateCommandFocus();
  }
  function updateCommandFocus() {
    [...$('commandResults').children].forEach((row,index)=>row.setAttribute('aria-selected',String(index===commandIndex)));
    if (commandEntries.length) {
      $('commandSearch').setAttribute('aria-activedescendant','command-option-'+commandIndex);
      $('commandResults').children[commandIndex]?.scrollIntoView?.({block:'nearest'});
    } else $('commandSearch').removeAttribute('aria-activedescendant');
  }
  function chooseCommand(index) {
    const entry=commandEntries[index]; if (!entry) return;
    $('commandDialog').close(); entry.action();
  }

  function element(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }
  function icon(name) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', '#i-' + name); svg.setAttribute('aria-hidden', 'true'); svg.append(use);
    return svg;
  }
  function settingTab(key, focus = false) {
    const active = document.querySelector('[data-settings-tab="' + key + '"]');
    if (!active) return;
    document.querySelectorAll('[data-settings-tab]').forEach(tab => {
      const selected = tab === active;
      tab.setAttribute('aria-selected', String(selected)); tab.tabIndex = selected ? 0 : -1;
      $(tab.getAttribute('aria-controls')).hidden = !selected;
    });
    if (focus) active.focus();
  }
  function renderFilters() {
    for (const [host, search, category, status] of [
      ['library', 'search', 'categoryFilter', 'favoritesOnly'],
      ['installed', 'installedSearch', 'installedCategory', 'installedFilter'],
    ]) {
      const target = $(host + 'Chips'); target.replaceChildren();
      const chips = [];
      if ($(search).value.trim()) chips.push(['Arama: ' + $(search).value.trim(), () => $(search).value = '']);
      if ($(category).value) chips.push([categories[$(category).value], () => $(category).value = '']);
      if (host === 'library' && $(status).checked) chips.push(['Favorilerim', () => $(status).checked = false]);
      if (host === 'installed' && $(status).value !== 'all') chips.push([$(status).selectedOptions[0].textContent, () => $(status).value = 'all']);
      chips.forEach(([label, reset]) => {
        const chip = button('', () => { reset(); render(); $(search).focus({preventScroll:true}); });
        chip.className = 'filter-chip'; chip.setAttribute('aria-label', label + ' filtresini kaldır');
        chip.append(element('span', '', label), element('span', '', '×')); target.append(chip);
      });
      target.hidden = !chips.length;
    }
  }
  function rememberFocus() {
    const focused = document.activeElement;
    const owner = focused?.closest('.card[data-mod-id],.download-job[data-job-id],.profile-card[data-profile-id],.recovery-row[data-backup-id]');
    const attribute = owner && ['data-mod-id','data-job-id','data-profile-id','data-backup-id'].find(key => owner.hasAttribute(key));
    return {focused, page:currentPage, attribute, value:attribute && owner.getAttribute(attribute),
      index:owner ? [...owner.querySelectorAll('button,input,select,textarea')].indexOf(focused) : -1};
  }
  function focusAvailable(node) {
    if (!node?.isConnected || node.disabled || node.closest('[hidden],dialog:not([open])')) return false;
    const closed = node.closest('details:not([open])');
    return !closed || closed.querySelector('summary')?.contains(node);
  }
  function restoreFocus(saved) {
    if (!saved.focused || saved.focused === document.body || currentPage !== saved.page
        || document.activeElement !== document.body || document.querySelector('dialog[open]')) return;
    if (focusAvailable(saved.focused)) {
      saved.focused.focus({preventScroll:true}); return;
    }
    if (!saved.attribute || saved.index < 0) return;
    const owner = [...$(currentPage).querySelectorAll('[' + saved.attribute + ']')].find(node => node.getAttribute(saved.attribute) === saved.value);
    const control = owner?.querySelectorAll('button,input,select,textarea')[saved.index];
    if (focusAvailable(control)) control.focus({preventScroll:true});
    else if (!busy) {
      const fallback = owner || $('title'); fallback.tabIndex = -1; fallback.focus({preventScroll:true});
    }
  }
  function page(id) {
    if (!titles[id]) return;
    currentPage = id;
    document.querySelectorAll('.section').forEach(e => e.hidden = e.id !== id);
    document.querySelectorAll('nav button').forEach(e => {
      e.classList.toggle('active', e.dataset.page === id);
      if (e.dataset.page === id) e.setAttribute('aria-current', 'page'); else e.removeAttribute('aria-current');
    });
    $('title').textContent = titles[id];
    $('breadcrumb').textContent = id === 'home' ? 'SENİN OYUN ALANIN' : 'OKDEV / ' + ({library:'KEŞFET',installed:'KÜTÜPHANEN',guides:'MOBALYTICS',profiles:'PROFİLLER',assistants:'AYARLAR',diagnostics:'DESTEK',publish:'YENİ MOD',downloads:'İNDİRMELER'}[id] || '');
    window.scrollTo(0, 0);
    loadVisibleCovers();
  }
  function notify(message, error = false, persistent = false) {
    clearTimeout(noticeTimer);
    const status = $('status'), previousFocus = document.activeElement;
    status.replaceChildren();
    status.className = 'status' + (error ? ' error' : '');
    status.setAttribute('role', error ? 'alert' : 'status');
    status.setAttribute('aria-live', error ? 'assertive' : 'polite');
    // Native modal dialogs sit above all z-index layers and make the page
    // inert. Errors must also appear inside the active dialog, not behind it.
    document.querySelectorAll('.dialog-feedback').forEach(note => { note.hidden = true; note.textContent = ''; });
    const openDialogs = [...document.querySelectorAll('dialog[open]')];
    const activeDialog = document.activeElement?.closest('dialog[open]') || openDialogs.at(-1);
    if (message && activeDialog && (error || persistent)) {
      let note = activeDialog.querySelector('.dialog-feedback');
      if (!note) {
        note = element('p', 'dialog-feedback');
        const heading = activeDialog.querySelector('h2');
        if (heading) heading.after(note); else activeDialog.prepend(note);
      }
      note.textContent = message; note.hidden = false; note.classList.toggle('error', error);
      note.setAttribute('role', error ? 'alert' : 'status');
    }
    if (!message) return;
    const dismiss = element('button', 'dismiss-notice', '×');
    dismiss.type = 'button'; dismiss.setAttribute('aria-label', 'Bildirimi kapat');
    dismiss.onclick = () => {
      const restore = status.contains(document.activeElement);
      clearTimeout(noticeTimer); status.replaceChildren();
      if (restore) {
        const target = previousFocus?.isConnected && previousFocus !== document.body
          && !previousFocus.closest('[hidden]') && !previousFocus.disabled ? previousFocus : $('title');
        if (target === $('title')) target.tabIndex = -1;
        target.focus({preventScroll:true});
      }
    };
    const statusIcon = element('span', 'status-icon');
    statusIcon.append(icon(error ? 'alert' : persistent ? 'dots' : 'check'));
    statusIcon.setAttribute('aria-hidden', 'true');
    status.append(statusIcon, element('span', 'status-message', message), dismiss);
    if (!persistent && !error) noticeTimer = setTimeout(() => {
      if (!status.contains(document.activeElement)) status.replaceChildren();
    }, 6000);
  }
  function lock() {
    document.querySelectorAll('[data-api]').forEach(e => e.disabled = busy || !api);
    document.querySelectorAll('#modForm input,#modForm textarea,#modForm select,#resetForm').forEach(e => e.disabled = busy);
    $('publishMod').disabled = busy || !api || !!sourceId;
    $('modForm').querySelector('[type="submit"]').disabled = busy || !api || !selectedFile;
    $('choose').textContent = selectedFile ? 'Dosyayı değiştir' : 'Dosya seç';
    $('showCurrentGuide').disabled = busy || !api || !state.preferences?.mobalytics_enabled || !state.guide?.pick;
    $('showManualGuide').disabled = busy || !api || !state.preferences?.mobalytics_enabled;
    $('main').setAttribute('aria-busy', String(busy));
    document.body.classList.toggle('is-busy', busy);
    renderBulk();
    $('clearDownloads').disabled = busy || !api || !(state.downloads?.jobs || []).some(j => !['queued', 'downloading', 'installing'].includes(j.status));
    renderBanPriority();
  }
  function button(label, action, {primary = false, remote = false} = {}) {
    const b = element('button', primary ? 'primary' : '', label);
    b.type = 'button'; b.onclick = action;
    if (remote) { b.dataset.api = ''; b.disabled = busy || !api; }
    return b;
  }
  function empty(target, title, description, filtered = false) {
    const e = element('div', 'empty');
    e.append(element('div', 'symbol', '◇'), element('h2', '', title), element('p', '', description));
    e.append(button(filtered ? 'Filtreleri temizle' : 'Mod ekle', () => {
      if (filtered) {
        if (target.id === 'catalogGrid') { $('search').value = ''; $('categoryFilter').value = ''; $('favoritesOnly').checked = false; }
        else { $('installedSearch').value = ''; $('installedCategory').value = ''; $('installedFilter').value = 'all'; }
        render();
      }
      else page('publish');
    })); target.append(e);
  }
  async function reload(refresh = false, background = false) {
    const request = ++snapshotRequest, epoch = stateEpoch;
    let value;
    try {
      value = await readBridge(api.snapshot(refresh));
      if (!value || typeof value.installed !== 'object' || !Array.isArray(value.catalog) || !value.settings) {
        throw new Error('Kütüphane bilgileri okunamadı. Bağlantıyı yeniden dene.');
      }
    }
    catch (error) { setConnection(false); throw error; }
    if (request !== snapshotRequest || (background && (busy || epoch !== stateEpoch))) return false;
    setConnection(true); initialized = true; $('loadingBanner').hidden = true;
    document.body.classList.remove('initializing');
    state = value;
    render();
    return true;
  }
  async function act(fn, message, {refresh = true, after} = {}) {
    if (busy || !api) return false;
    const focus = rememberFocus();
    busy = true; stateEpoch++; lock(); notify('İşlem sürüyor…', false, true);
    let success = false;
    try {
      const result = await fn();
      if (!result || !result.ok) throw new Error(result?.error || 'İşlem tamamlanamadı.');
      success = true;
      let stale = false;
      if (refresh) {
        try { await reload(); }
        catch (_) { stale = true; }
      }
      notify(stale ? 'İşlem tamamlandı, ancak liste yenilenemedi. Bağlantıyı yeniden dene; işlemi tekrar yapmana gerek yok.' : message, stale);
      if (after) after(result.result);
    } catch (e) {
      $('autoAccept').checked = !!state.settings.auto_accept;
      applyPreferences();
      notify(e.message || 'İşlem tamamlanamadı.', true);
    } finally {
      busy = false; lock();
      restoreFocus(focus);
    }
    return success;
  }
  async function download(mod, source = false) {
    if (api?.enqueue_download) {
      await act(() => api.enqueue_download(mod.id, source ? 'curated' : 'catalog'), mod.name + ' indirme kuyruğuna eklendi.');
      return;
    }
    let polling = false, finished = false;
    const poll = async () => {
      if (polling) return;
      polling = true;
      try {
        const p = await api.download_status();
        if (finished) return;
        $('downloadProgress').hidden = p.stage === 'idle';
        if (p.total > 0) { $('downloadBar').max = p.total; $('downloadBar').value = p.received; }
        else $('downloadBar').removeAttribute('value');
        $('downloadLabel').textContent = p.stage === 'installing' ? 'Paket kontrol ediliyor ve yükleniyor…' : mod.name + ' · ' + (p.received / 1048576).toFixed(1) + ' MB' + (p.total ? ' / ' + (p.total / 1048576).toFixed(1) + ' MB' : '');
        $('cancelDownload').disabled = p.stage !== 'downloading';
      } catch (_) { /* The operation itself reports any bridge failure. */ }
      finally { polling = false; }
    };
    const timer = setInterval(poll, 400);
    try { await act(() => source ? api.download_source(mod.id) : api.download(mod.id), 'Mod eklendi. Modlarım ekranından etkinleştirebilirsin.'); }
    finally { finished = true; clearInterval(timer); $('downloadProgress').hidden = true; }
  }
  function favorite(mod) {
    const marked = (state.settings.favorites || []).includes(mod.id);
    const b = button('', () => act(() => api.favorite(mod.id, !marked), marked ? 'Favorilerden çıkarıldı.' : 'Favorilere eklendi.'), {remote: true});
    b.append(icon('star'));
    b.className = 'favorite' + (marked ? ' selected' : '');
    b.setAttribute('aria-label', mod.name + (marked ? ' favorilerden çıkar' : ' favorilere ekle'));
    b.setAttribute('aria-pressed', String(marked));
    return b;
  }
  let queueSignature = '';
  function renderDownloads() {
    const focus = rememberFocus();
    const queue = state.downloads || {jobs: [], active: 0};
    const jobs = queue.jobs || [];
    const active = jobs.filter(j => ['queued', 'downloading', 'installing'].includes(j.status));
    $('navDownloads').textContent = active.length;
    $('navDownloads').hidden = active.length === 0;
    $('queueWarning').textContent = queue.warning || '';
    $('repairDownloads').hidden = !queue.warning;
    const needsRetry = jobs.filter(j => ['failed', 'interrupted'].includes(j.status)).length;
    $('queueSummary').textContent = active.length ? active.length + ' indirme devam ediyor veya sırada.' : needsRetry ? needsRetry + ' indirme tamamlanamadı veya yarım kaldı.' : jobs.length ? 'Kuyrukta bekleyen indirme yok.' : 'Henüz indirme yok.';
    const signature = JSON.stringify(jobs.map(j => [j.id, j.status, j.error]));
    if (signature !== queueSignature || !$('downloadJobs').childElementCount) {
      queueSignature = signature;
      const target = $('downloadJobs'); target.replaceChildren();
      if (!jobs.length) {
        const note = element('div', 'empty');
        note.append(element('div', 'symbol', '↓'), element('h2', '', 'Yeni bir görünüm keşfet'), element('p', '', 'Keşfet bölümünden eklediğin içerikler burada görünür.'), button('Keşfet’e git', () => page('library')));
        target.append(note);
      }
      [...jobs].reverse().forEach(job => {
        const row = element('article', 'download-job ' + job.status); row.dataset.jobId = job.id;
        const icon = element('div', 'job-icon', {completed:'✓',failed:'!',cancelled:'−',interrupted:'↻',queued:'…',downloading:'↓',installing:'◇'}[job.status]);
        icon.setAttribute('aria-hidden', 'true');
        const info = element('div', 'job-info');
        const heading = element('div', 'job-heading');
        heading.append(element('h3', '', job.name), element('span', 'badge', {completed:'Tamamlandı',failed:'Tamamlanamadı',cancelled:'İptal edildi',interrupted:'Yarım kaldı',queued:'Sırada',downloading:'İndiriliyor',installing:'Yükleniyor'}[job.status]));
        info.append(heading, element('p', 'job-detail', job.error || ''));
        if (['downloading', 'installing'].includes(job.status)) {
          const bar = element('progress', 'job-progress'); bar.setAttribute('aria-label', job.name + ' indirme ilerlemesi'); info.append(bar);
        }
        const actions = element('div', 'job-actions');
        if (['queued', 'downloading'].includes(job.status)) actions.append(button('İptal et', () => act(() => api.cancel_queued_download(job.id), 'İptal isteği alındı.'), {remote:true}));
        if (['failed', 'cancelled', 'interrupted'].includes(job.status)) actions.append(button('Yeniden dene', () => act(() => api.retry_download(job.id), 'İndirme yeniden sıraya eklendi.'), {remote:true}));
        if (job.status === 'completed') actions.append(button('Modlarımda göster', () => { $('installedSearch').value = state.installed[job.mod_id]?.name || job.name; $('installedFilter').value = 'all'; $('installedCategory').value = ''; page('installed'); render(); }));
        row.append(icon, info, actions); target.append(row);
      });
    }
    jobs.forEach(job => {
      const row = [...$('downloadJobs').children].find(el => el.dataset.jobId === job.id);
      if (!row) return;
      const bar = row.querySelector('progress');
      if (bar) {
        if (job.total > 0) { bar.max = job.total; bar.value = Math.min(job.received, job.total); }
        else bar.removeAttribute('value');
      }
      if (job.status === 'downloading') {
        const received = HubView.bytes(job.received), total = job.total ? ' / ' + HubView.bytes(job.total) : '';
        const speed = job.speed > 0 ? ' · ' + HubView.bytes(job.speed) + '/sn' : '';
        const seconds = job.speed > 0 && job.total > job.received ? Math.ceil((job.total - job.received) / job.speed) : 0;
        const remaining = seconds ? ' · Yaklaşık ' + (seconds >= 60 ? Math.ceil(seconds / 60) + ' dk' : seconds + ' sn') : '';
        row.querySelector('.job-detail').textContent = received + total + speed + remaining;
      } else if (job.status === 'installing') row.querySelector('.job-detail').textContent = 'Dosya doğrulandı. Kütüphanene ekleniyor…';
      else if (job.status === 'queued') row.querySelector('.job-detail').textContent = 'Sıradaki indirme tamamlandığında otomatik başlar.';
      else if (job.status === 'completed') row.querySelector('.job-detail').textContent = 'Hazır. Kullanmak için Modlarım’dan etkinleştir.';
      else if (job.status === 'cancelled') row.querySelector('.job-detail').textContent = 'İndirme iptal edildi. İstersen yeniden sıraya ekleyebilirsin.';
    });
    $('clearDownloads').disabled = busy || !api || !jobs.some(j => !['queued', 'downloading', 'installing'].includes(j.status));
    restoreFocus(focus);
  }
  function sourceImport(mod) {
    if (busy) return;
    act(() => api.prepare_import(mod.id), 'İndirdiğin mod dosyasını seç.', {refresh: false, after: () => {
      sourceId = mod.id;
      selectedFile = false; document.querySelector('.file-picker').classList.remove('selected');
      $('importError').hidden = true;
      const form = $('modForm'); form.reset();
      for (const key of ['id', 'name', 'champion', 'champion_id', 'version', 'description', 'category']) form.elements.namedItem(key).value = mod[key] ?? '';
      $('importSource').textContent = mod.name + ' · ' + mod.author + ' · ' + mod.license;
      $('selected').textContent = 'Dosya seçilmedi'; $('coverName').textContent = 'İsteğe bağlı';
      updateCategory(); page('publish');
    }});
  }
  function previewFor(mod) {
    const cached = coverCache.get(mod.id);
    const local = mod.preview_data || state.installed[mod.id]?.preview_data
      || (cached?.key === state.installed[mod.id]?.cover_key ? cached?.data : null);
    if (local?.startsWith('data:')) return local;
    if (state.preferences?.data_saver === true) return null;
    return local || mod.image_url || boot.sources.find(source => source.id === mod.id)?.image_url;
  }
  async function loadVisibleCovers() {
    if (!api?.cover_previews) return;
    const ids = [...new Set([...document.querySelectorAll('[data-preview-id]')]
      .filter(el => !el.closest('.section')?.hidden && (!el.closest('dialog') || el.closest('dialog').open))
      .filter(el => { const rect = el.getBoundingClientRect(); return rect.bottom >= -300 && rect.top <= window.innerHeight + 500; })
      .map(el => el.dataset.previewId))].filter(id => {
        const key = state.installed[id]?.cover_key;
        return key && coverCache.get(id)?.key !== key && !pendingCovers.has(id);
      }).slice(0, 48);
    if (!ids.length) return;
    ids.forEach(id => pendingCovers.add(id));
    try {
      const values = await api.cover_previews(ids);
      for (const [id, value] of Object.entries(values || {})) {
        if (state.installed[id]?.cover_key !== value.key) continue;
        coverCache.delete(id); coverCache.set(id, value);
        if (coverCache.size > 96) coverCache.delete(coverCache.keys().next().value);
        if (!value.data) continue;
        document.querySelectorAll('[data-preview-id]').forEach(art => {
          if (art.dataset.previewId !== id) return;
          let img = art.querySelector('img');
          if (!img) {
            [...art.childNodes].filter(node => node.nodeType === Node.TEXT_NODE).forEach(node => node.remove());
            img = element('img'); img.alt = state.installed[id]?.name || ''; art.prepend(img);
          }
          img.src = value.data;
        });
      }
    } catch (_) { /* A missing cover never blocks a mod operation. */ }
    finally { ids.forEach(id => pendingCovers.delete(id)); }
  }
  function card(mod, local = false) {
    const category = mod.category || 'skins', source = !!mod.source_url && !local;
    const e = element('article', 'card' + (local && mod.enabled ? ' is-enabled' : ''));
    e.dataset.modId = mod.id;
    const art = element('div', 'art art-' + category);
    art.dataset.previewId = mod.id;
    const fallback = element('span', 'art-letter'); fallback.setAttribute('aria-hidden', 'true');
    fallback.append(icon(category === 'skins' ? 'crest' : category === 'ui' ? 'hud' : categoryIcons[category] || 'layers')); art.append(fallback);
    const categoryMark = element('span', 'art-category'); categoryMark.setAttribute('aria-hidden', 'true');
    categoryMark.append(icon(categoryIcons[category] || 'layers'), element('span', '', categories[category])); art.append(categoryMark);
    const preview = previewFor(mod);
    if (preview) {
      const img = element('img'); img.src = preview; img.alt = mod.name; img.loading = 'lazy'; img.referrerPolicy = 'no-referrer';
      img.onerror = () => img.remove(); art.append(img);
    }
    art.append(favorite(mod));
    if (local) {
      const label = element('label', 'card-select');
      const check = element('input'); check.type = 'checkbox'; check.checked = selectedMods.has(mod.id);
      check.setAttribute('aria-label', mod.name + ' toplu işlem için seç');
      e.classList.toggle('bulk-selected', check.checked);
      check.onchange = () => { if (check.checked) selectedMods.add(mod.id); else selectedMods.delete(mod.id); e.classList.toggle('bulk-selected', check.checked); renderBulk(); };
      label.append(check); art.append(label);
    }
    const missing = local && mod.files_available === false;
    const badge = element('span', 'badge' + (missing ? ' missing' : local && mod.enabled ? ' enabled' : ''), missing ? 'Dosyaları eksik' : local ? (mod.enabled ? 'Etkin' : 'Kapalı') : (source ? (state.installed[mod.id] ? 'Yüklü · RuneForge' : 'RuneForge') : 'OKDEV kataloğu'));
    const subtitle = [categories[category], mod.champion, 'v' + mod.version].filter(Boolean).join(' · ');
    const actions = element('div', 'actions');
    if (local) {
      if (mod.files_available === false && !mod.enabled) actions.append(button('Dosyaları eksik', () => showDetail(mod, true), {primary:true}));
      else actions.append(button(mod.enabled ? 'Kapat' : 'Etkinleştir', () => requestSelection([mod.id], mod.enabled ? 'disable' : 'enable', false), {primary: !mod.enabled, remote: true}));
      actions.append(button('Detaylar', () => showDetail(mod, true)));
    } else if (source) {
      if (state.installed[mod.id]) actions.append(button('Modlarımda göster', () => { $('installedSearch').value = mod.name; $('installedFilter').value = 'all'; $('installedCategory').value = ''; page('installed'); render(); }, {primary: true}));
      if (!state.installed[mod.id]) actions.append(mod.download_url
        ? button('Kütüphaneme ekle', () => download(mod, true), {primary: true, remote: true})
        : button('İncele ve ekle', () => showDetail(mod), {primary: true}));
      actions.append(button('Detaylar', () => showDetail(mod)));
    } else {
      const saved = state.installed[mod.id];
      if (saved && !HubView.newer(mod.version, saved.version)) actions.append(button('Modlarımda göster', () => { $('installedSearch').value = saved.name; $('installedFilter').value = 'all'; $('installedCategory').value = ''; page('installed'); render(); }));
      else actions.append(button(saved ? 'Güncelle' : 'İndir', () => download(mod), {primary: true, remote: true}));
    }
    const title = button('', () => showDetail(mod, local)); title.className = 'card-title-button'; title.append(element('h3', '', mod.name));
    e.append(art, badge, element('small', 'mod-meta', subtitle), title, element('p', '', mod.description));
    if (mod.author) e.append(element('div', 'credit', mod.author + (mod.license ? ' · ' + mod.license : '')));
    e.append(actions); return e;
  }
  function showDetail(mod, local = false) {
    const content = $('detailContent'); content.replaceChildren();
    const target = element('div', 'detail-body'); content.append(target);
    const art = element('div', 'detail-art');
    art.append(icon((mod.category || 'skins') === 'skins' ? 'crest' : categoryIcons[mod.category] || 'layers'));
    art.dataset.previewId = mod.id;
    const preview = previewFor(mod);
    if (preview) { const img = element('img'); img.src = preview; img.alt = mod.name; img.referrerPolicy = 'no-referrer'; img.onerror = () => img.remove(); art.append(img); }
    target.append(art, element('span', 'badge', categories[mod.category || 'skins']), element('h2', '', mod.name), element('div', 'mod-meta', [mod.champion, 'v' + mod.version].filter(Boolean).join(' · ')), element('p', '', mod.description || 'Bu paket için açıklama eklenmemiş.'));
    target.querySelector('h2').id = 'detailTitle';
    $('detailDialog').setAttribute('aria-labelledby', 'detailTitle');
    if (mod.author) target.append(element('div', 'credit', 'Yapımcı: ' + mod.author + (mod.license ? ' · ' + mod.license : '')));
    const actions = element('div', 'actions');
    if (local) {
      if (mod.files_available === false) {
        target.append(element('div', 'help-note', 'Bu modun dosya klasörü bulunamadı. Varsa yedeğini geri yükle veya özgün paketi aynı mod kimliğiyle yeniden ekle: ' + mod.id));
        const source = boot.sources.find(item => item.id === mod.id);
        if (source?.download_url) actions.append(button('Seçkideki sürümü indir', () => { $('detailDialog').close(); download(source, true); }, {primary:true,remote:true}));
        else actions.append(button('Mod dosyası ekle', () => { $('detailDialog').close(); page('publish'); }));
      }
      if (mod.enabled || mod.files_available !== false) actions.append(button(mod.enabled ? 'Modu kapat' : 'Etkinleştir', () => { $('detailDialog').close(); requestSelection([mod.id], mod.enabled ? 'disable' : 'enable', false); }, {primary: true, remote: true}));
      if (boot.sources.some(source => source.id === mod.id)) actions.append(button('Kaynak sayfası ↗', () => act(() => api.open_source(mod.id), 'Özgün kaynak sayfası açıldı.', {refresh: false}), {remote: true}));
      const remove = button('Modu kaldır', () => { $('detailDialog').close(); removeId = mod.id; $('removeDescription').textContent = mod.name + ' kütüphanenden kaldırılacak.'; $('removeDialog').showModal(); }, {remote: true});
      remove.classList.add('danger'); actions.append(remove);
    } else if (mod.source_url) {
      const saved = state.installed[mod.id], available = !!mod.download_url && (!saved || saved.sha256 !== mod.sha256 || saved.files_available === false);
      target.append(element('div', 'help-note', mod.download_url ? 'Paket RuneForge’un özgün sunucusundan indirilir ve dosya bütünlüğü doğrulanır. ' + (mod.download_size / 1048576).toFixed(1) + ' MB' + (saved && available ? ' · Mevcut kopyan yedeklenir.' : '') : '1. Özgün sayfadan paketi indir. 2. İndirdiğin dosyayı aşağıdaki düğmeyle kütüphanene ekle.'));
      if (available) actions.append(button(saved ? 'Seçkideki sürümü ekle' : 'Kütüphaneme ekle', () => { $('detailDialog').close(); download(mod, true); }, {primary: true, remote: true}));
      actions.append(button('Kaynak sayfası ↗', () => act(() => api.open_source(mod.id), 'Özgün kaynak sayfası açıldı.', {refresh: false}), {primary: !available, remote: true}));
      actions.append(button('İndirdiğim dosyayı ekle', () => { $('detailDialog').close(); sourceImport(mod); }, {remote: true}));
    } else {
      const saved = state.installed[mod.id];
      if (saved && !HubView.newer(mod.version, saved.version)) actions.append(button('Modlarımda göster', () => { $('detailDialog').close(); $('installedSearch').value=saved.name; $('installedFilter').value='all'; $('installedCategory').value=''; page('installed'); render(); }, {primary: true}));
      else actions.append(button(saved ? 'Güncelle' : 'İndir', () => { $('detailDialog').close(); download(mod); }, {primary: true, remote: true}));
    }
    content.append(actions); $('detailDialog').showModal(); loadVisibleCovers();
  }
  const laneNames = {top:'Üst koridor',jungle:'Orman',mid:'Orta koridor',adc:'Alt koridor',support:'Destek'};
  const listSignatures = {};
  function draftProfiles() {
    return Object.fromEntries(Object.keys(laneNames).map(lane => [lane, {
      pick:[...(state.preferences.lane_profiles?.[lane]?.pick || [])],
      ban:[...(state.preferences.lane_profiles?.[lane]?.ban || [])]
    }]));
  }
  function draftList(kind) {
    const lane = $('draftLane').value;
    return lane === 'general' ? (kind === 'ban' ? state.preferences.auto_ban_priority || [] : []) : draftProfiles()[lane][kind];
  }
  function saveDraftList(kind, next) {
    const lane = $('draftLane').value, profiles = draftProfiles();
    const changes = lane === 'general' ? {auto_ban_priority:next} : {lane_profiles:profiles};
    if (lane !== 'general') profiles[lane][kind] = next;
    const bans = state.preferences.lane_automation ? Object.values(profiles).some(p=>p.ban.length) : (changes.auto_ban_priority || state.preferences.auto_ban_priority || []).length;
    if (!bans) changes.auto_ban_enabled = false;
    if (!Object.values(profiles).some(p=>p.pick.length)) changes.auto_pick_enabled = false;
    return act(() => api.save_preferences(changes), 'Öncelik listesi kaydedildi.');
  }
  function renderBanPriority() {
    const profiles = draftProfiles(), lane = $('draftLane').value;
    const bans = state.preferences.lane_automation ? Object.values(profiles).some(p=>p.ban.length) : (state.preferences.auto_ban_priority || []).length;
    $('autoBanEnabled').disabled = busy || !api || !bans;
    $('autoPickEnabled').disabled = busy || !api || !Object.values(profiles).some(p=>p.pick.length);
    $('lanePickEditor').hidden = lane === 'general';
    $('draftRoleStatus').textContent = laneNames[state.guide?.lane] ? 'Atanan koridor: ' + laneNames[state.guide.lane] : 'Atanan koridor bekleniyor. Koridor bilinmiyorsa koridora göre işlem yapılmaz.';
    for (const kind of ['ban','pick']) {
      const ids = draftList(kind), prefix = kind === 'ban' ? 'Ban' : 'Pick';
      $('add' + prefix + 'Champion').disabled = busy || !api || ids.length >= 10 || (kind === 'pick' && lane === 'general');
      document.querySelectorAll('#' + kind + 'Priority button').forEach(c=>{c.disabled=busy||!api||c.dataset.boundary==='true';});
      const signature = JSON.stringify([lane,ids]);
      if (signature === listSignatures[kind]) continue;
      listSignatures[kind] = signature;
      $(kind + 'Priority').replaceChildren();
      ids.forEach((id,index)=>{
        const name=boot.champions.find(c=>c.id===id)?.name || String(id);
        const row=element('li','ban-row');row.append(element('span','',name));
        const actions=element('div','ban-actions');
        for(const [label,delta] of [['Yukarı',-1],['Aşağı',1]]) {
          const control=button(label,()=>{const next=[...ids];[next[index],next[index+delta]]=[next[index+delta],next[index]];saveDraftList(kind,next);});
          control.setAttribute('aria-label',name+' '+label.toLocaleLowerCase('tr'));
          control.dataset.boundary=String(index+delta<0||index+delta>=ids.length);
          control.disabled=busy||!api||control.dataset.boundary==='true';actions.append(control);
        }
        const remove=button('Kaldır',()=>saveDraftList(kind,ids.filter(c=>c!==id)));
        remove.setAttribute('aria-label',name+' kaldır');remove.disabled=busy||!api;
        actions.append(remove);row.append(actions);$(kind+'Priority').append(row);
      });
      $(kind+'ListStatus').textContent=ids.length?'İlk uygun şampiyon kullanılır. En fazla 10 şampiyon.':'Bu liste boş; bu listeyle otomatik işlem yapılmaz.';
    }
  }
  function applyPreferences() {
    const prefs = state.preferences || {};
    const theme = prefs.theme || 'dark';
    document.documentElement.dataset.theme = theme === 'system' ? (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark') : theme;
    document.body.classList.toggle('compact', !!prefs.compact_cards);
    document.body.classList.toggle('reduce-motion', !!prefs.reduce_motion);
    const view = prefs.mod_view === 'list' ? 'list' : 'grid';
    ['catalogGrid', 'installedGrid'].forEach(id => $(id).classList.toggle('list-view', view === 'list'));
    document.querySelectorAll('[data-view-mode]').forEach(b => {
      b.setAttribute('aria-pressed', String(b.dataset.viewMode === view)); b.disabled = busy || !api;
    });
    document.querySelectorAll('[data-pref]').forEach(control => {
      const value = prefs[control.dataset.pref];
      if (control.type === 'checkbox') control.checked = !!value;
      else if (value !== undefined) control.value = value;
    });
    $('settingsHotkey').textContent = prefs.mobalytics_hotkey || 'Ctrl+Shift+B';
    renderBanPriority();
  }
  function renderGuide() {
    const guide = state.guide || {}, pick = guide.pick, prefs = state.preferences || {}, companion = state.companion || {};
    $('gamePhase').textContent = guide.status || 'İstemci bekleniyor';
    $('gameDot').classList.toggle('connected', !!guide.connected);
    $('homeChampion').textContent = pick ? pick.champion.name : 'Bir sonraki oyununa hazır';
    $('homeChampionIcon').textContent = $('guideChampionIcon').textContent = pick ? pick.champion.name.slice(0, 2).toUpperCase() : '?';
    $('homeGuideText').textContent = pick ? pick.role_label + ' · Build rehberin hazır.' : 'Şampiyonunu kilitlediğinde rehberin burada hazır olur.';
    $('homeHotkey').textContent = prefs.mobalytics_enabled ? 'Oyun içi kısayol · ' + prefs.mobalytics_hotkey : 'Mobalytics şu anda kapalı';
    $('guideChampion').textContent = pick ? pick.champion.name : 'Henüz şampiyon kilitlenmedi';
    $('guideRole').textContent = pick ? pick.role_label + ' · Mobalytics build rehberi' : 'League istemcisi açıkken otomatik algılanır.';
    $('guideBadge').textContent = !prefs.mobalytics_enabled ? 'Kapalı' : pick ? 'Hazır' : 'Bekleniyor';
    $('guideNavDot').hidden = !prefs.mobalytics_enabled || !pick;
    $('companionStatus').textContent = companion.error || (!prefs.mobalytics_enabled ? 'Rehberi açmak için yukarıdaki anahtarı etkinleştir.' : companion.running ? (companion.visible ? 'Rehber penceresi açık.' : 'Kısayolla açmaya hazır.') : 'OKDEV çalışırken rehber hazırlanır.');
    lock(); renderBulk();
  }
  function renderBulk() {
    for (const id of selectedMods) if (!state.installed[id]) selectedMods.delete(id);
    const visible = new Set([...document.querySelectorAll('#installedGrid [data-mod-id]')].map(card => card.dataset.modId));
    const outside = [...selectedMods].filter(id => !visible.has(id)).length;
    $('bulkCount').textContent = selectedMods.size ? selectedMods.size + ' mod seçildi' + (outside ? ' · ' + outside + ' seçim bu görünümün dışında' : '') : 'Birden fazla modu birlikte yönet';
    $('bulkToolbar').classList.toggle('has-selection', selectedMods.size > 0);
    const bulkHadFocus = $('bulkToolbar').contains(document.activeElement);
    $('bulkToolbar').hidden = selectedMods.size === 0;
    if (bulkHadFocus && $('bulkToolbar').hidden) $('selectionMenu').querySelector('summary').focus({preventScroll:true});
    $('selectVisible').disabled = busy || !api || !visible.size;
    ['bulkEnable', 'bulkDisable', 'clearBulk'].forEach(id => $(id).disabled = busy || !api || !selectedMods.size);
    $('disableAll').disabled = busy || !api || !Object.values(state.installed).some(m => m.enabled);
    $('undoSelection').disabled = busy || !api || !state.selection_undo?.available;
    $('undoSelection').hidden = !state.selection_undo?.available;
  }
  function applyPlan(plan) {
    return Object.keys(plan.targets || {}).length
      ? api.apply_selection(plan.requested, plan.mode, plan.revision, plan.targets)
      : api.apply_selection(plan.requested, plan.mode, plan.revision);
  }
  async function requestSelection(ids, mode, alwaysConfirm = true, targets = null) {
    if (!api?.preview_selection) {
      if (ids.length === 1) return act(() => api.enable(ids[0], mode === 'enable'), 'Mod seçimi kaydedildi.');
      return;
    }
    let plan = null;
    const ok = await act(() => targets ? api.preview_selection(ids, mode, targets) : api.preview_selection(ids, mode), '', {refresh:false, after: value => { plan = value; }});
    if (!ok || !plan) return;
    if (!plan.changed) { notify('Seçimlerin zaten bu durumda.'); return; }
    const replaced = mode === 'enable' && plan.disable.length > 0;
    if (!alwaysConfirm && !replaced) {
      return act(() => applyPlan(plan), 'Seçim kaydedildi. İstersen geri alabilirsin.');
    }
    const dialog = $('selectionDialog'); dialog._plan = plan;
    $('selectionTitle').textContent = replaced ? 'Etkin mod değiştirilsin mi?' : 'Mod seçimlerini uygula';
    const detail = $('selectionChanges'); detail.replaceChildren();
    for (const [label, mods, className] of [['Etkinleştirilecek', plan.enable, 'enable'], ['Kapatılacak', plan.disable, 'disable']]) {
      if (!mods.length) continue;
      const block = element('div', 'selection-change ' + className); block.append(element('h3', '', label + ' · ' + mods.length));
      const list = element('ul'); mods.forEach(mod => list.append(element('li', '', mod.name))); block.append(list); detail.append(block);
    }
    for (const mod of plan.target_changes || []) detail.append(element('p', '', mod.name + ' · Hedef kostüm: ' + mod.skin_id));
    dialog.showModal();
  }
  function renderHome(locals) {
    $('navInstalled').textContent = locals.length;
    const selected=locals.filter(mod=>mod.enabled), missing=selected.filter(mod=>mod.files_available===false);
    $('loadoutTitle').textContent=missing.length?'Seçimlerinde eksik dosya var':selected.length?'Seçimlerin kaydedildi':'Bir sonraki oyununu hazırla';
    $('loadoutSummary').textContent=missing.length?missing.length+' modun dosyası bulunamadı. Modlarını kontrol et.':selected.length?
      selected.length+' etkin mod · Seçimlerin sonraki oyun hazırlanırken kullanılır.':'Kütüphanenden bir mod etkinleştir veya hazır bir profil uygula.';
    $('loadoutState').textContent=missing.length?'Kontrol gerekli':selected.length?'Kaydedildi':'Henüz mod seçilmedi';
    $('loadoutState').className='loadout-state'+(missing.length?' attention':selected.length?' ready':'');
    const loadout=$('loadoutItems'); loadout.replaceChildren();
    selected.slice(0,4).forEach(mod=>{
      const row=button('',()=>showDetail(mod,true)); row.className='loadout-item';
      const text=element('span'); text.append(element('strong','',mod.name),element('small','',
        [mod.champion, categories[mod.category||'skins'], mod.files_available===false?'Dosyaları eksik':'Etkin'].filter(Boolean).join(' · ')));
      row.append(element('span','loadout-dot'+(mod.files_available===false?' attention':'')),text); loadout.append(row);
    });
    if (!selected.length) loadout.append(element('p','loadout-empty',locals.length?'Modların kütüphanende. Hangilerini kullanacağına sen karar ver.':'İlk modunla başla. Dosyanı ekle, bilgilerini kontrol et ve etkinleştir.'));
    $('loadoutAction').textContent=!locals.length?'İlk modunu ekle →':selected.length>4?'Tüm '+selected.length+' seçimi gör →':'Modlarımı yönet →';
    $('loadoutAction').onclick=()=>{page(locals.length?'installed':'publish');};
    const target = $('homeRecent'); target.replaceChildren();
    HubView.filter(locals, {sort: 'recent'}).slice(0, 3).forEach(mod => {
      const item = button('', () => showDetail(mod, true)); item.className = 'recent-item';
      const art = element('span', 'recent-art', (mod.champion || mod.name).slice(0, 2).toUpperCase());
      art.dataset.previewId = mod.id;
      const preview = previewFor(mod);
      if (preview) { const img = element('img'); img.src = preview; img.alt = ''; img.referrerPolicy='no-referrer'; img.onerror=()=>{art.textContent=(mod.champion || mod.name).slice(0,2).toUpperCase();}; art.replaceChildren(img); }
      const text = element('span'); text.append(element('strong', '', mod.name), element('small', '', mod.enabled ? 'Etkin · Sonraki oyun için hazır' : categories[mod.category || 'skins'])); item.append(art, text); target.append(item);
    });
    if (!locals.length) empty(target, 'Oyun alanını kişiselleştir', 'İlk modunu ekle veya Keşfet’ten sana uygun bir görünüm bul.');
  }
  let fullActivity = false;
  function renderActivity() {
    const activity = state.activity || {events: [], warning: ''};
    const labels = {import:'Mod eklendi',update:'Mod güncellendi',remove:'Mod yedeklenerek kaldırıldı',restore:'Mod geri yüklendi',selection:'Mod seçimleri değişti',undo:'Önceki seçimlere dönüldü',profile_save:'Profil kaydedildi',profile_import:'Profil içe aktarıldı',recovery:'Yarım kalan işlem kurtarıldı'};
    function fill(target, limit) {
      target.replaceChildren();
      const events = activity.events.slice(0, limit);
      if (!events.length) target.append(element('p', 'subtle', activity.warning || 'İlk işlemini yaptığında burada görünecek.'));
      events.forEach(event => {
        const row = element('div', 'activity-row');
        const mark = element('span', 'activity-mark', {import:'+',update:'↻',remove:'−',restore:'↩',selection:'✓',undo:'↩',profile_save:'◇',profile_import:'↓',recovery:'↩'}[event.kind]); mark.setAttribute('aria-hidden', 'true');
        const content = element('div', 'activity-content');
        content.append(element('strong', '', labels[event.kind] || 'İşlem tamamlandı'), element('span', '', event.name || event.count + (event.kind === 'recovery' ? ' işlem · Dosyalar korundu' : ' mod seçimi')));
        const at = new Date(event.at * 1000); const time = element('time', '', at.toLocaleString('tr', {day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})); time.dateTime = at.toISOString();
        row.append(mark, content, time); target.append(row);
      });
    }
    fill($('homeActivity'), 4); fill($('activityList'), fullActivity ? 200 : 20);
    $('showAllActivity').hidden = fullActivity || activity.events.length <= 20;
    $('activityWarning').textContent = activity.warning || '';
  }
  function renderProfiles() {
    const target = $('profileCards'); target.replaceChildren();
    $('profileCount').textContent = Object.keys(state.profiles || {}).length + ' kayıtlı profil';
    Object.entries(state.profiles || {}).forEach(([id, profile]) => {
      const panel = element('article', 'profile-card'); panel.dataset.profileId = id;
      const heading = element('div', 'profile-card-heading');
      const manage = button('⋯', () => { $('editProfileDialog').dataset.profileId = id; $('editProfileInput').value = profile.name; $('editProfileDialog').showModal(); });
      manage.setAttribute('aria-label', profile.name + ' profilini düzenle');
      heading.append(element('h3', '', profile.name), manage);
      const active = Object.values(state.installed).filter(m => m.enabled).map(m => m.id).sort();
      const matches = !profile.missing && JSON.stringify([...profile.mods].sort()) === JSON.stringify(active) &&
        Object.entries(profile.targets || {}).every(([id, target]) => {
          const mod = state.installed[id];
          return mod && (mod.selected_target_skin_id ?? mod.target_skin_ids?.[0] ?? mod.champion_id * 1000) === target;
        });
      const missing = profile.mods.filter(id => !state.installed[id] || state.installed[id].files_available === false);
      const missingCount = Math.max(missing.length, profile.missing || 0);
      panel.classList.toggle('current', matches);
      panel.append(heading, element('span', 'subtle', profile.mods.length + ' kayıtlı seçim' + (matches ? ' · Şu anki seçimlerin' : '')));
      if (missingCount) panel.append(element('p', 'profile-missing', missingCount + ' mod eksik veya paket içeriği farklı. Doğru paketleri eklediğinde profil otomatik eşleşir.'));
      const tags = element('div', 'profile-tags');
      profile.mods.slice(0, 6).forEach(modId => tags.append(element('span', '', state.installed[modId]?.name || 'Eksik mod')));
      if (profile.mods.length > 6) tags.append(element('span', '', '+' + (profile.mods.length - 6)));
      if (!profile.mods.length) tags.append(element('span', '', 'Tüm modları kapatan profil'));
      panel.append(tags, button('Bu profili uygula', () => {
        if (missingCount) { notify('Profilin doğru paketlerini ekle veya geri yükle. Seçimlerin değiştirilmedi.', true); return; }
        if (api?.preview_selection) requestSelection(profile.mods, 'replace', true, profile.targets || null);
        else act(() => api.apply_profile(id), profile.name + ' uygulandı. Sonraki oyun için hazır.');
      }, {primary: true, remote: true})); target.append(panel);
    });
    if (!Object.keys(state.profiles || {}).length) {
      const note = element('div', 'empty'); note.append(element('div', 'symbol', '◇'), element('h2', '', 'İlk kombinasyonunu kaydet'), element('p', '', 'Modlarım’dan seçimlerini etkinleştir. Sonra bu alanda bir ad verip kaydet.')); target.append(note);
    }
  }
  function render() {
    const focus = rememberFocus();
    const mods = [...boot.sources, ...state.catalog.filter(m => !boot.sources.some(s => s.id === m.id))];
    const locals = Object.values(state.installed), favorites = state.settings.favorites || [];
    $('catalogCount').textContent = mods.length; $('installedCount').textContent = locals.length;
    $('activeCount').textContent = locals.filter(m => m.enabled).length;
    applyPreferences(); renderGuide(); renderHome(locals); renderProfiles(); renderDownloads(); renderActivity();
    document.querySelectorAll('[data-category]').forEach(b => { const selected = b.dataset.category === $('categoryFilter').value; b.classList.toggle('selected', selected); b.setAttribute('aria-pressed', String(selected)); });
    $('autoAccept').checked = !!state.settings.auto_accept; $('warning').textContent = state.warning || '';
    const filtered = HubView.filter(mods, {term: $('search').value, category: $('categoryFilter').value, favorites, onlyFavorites: $('favoritesOnly').checked, sort: $('sort').value});
    const nextSignature = JSON.stringify(['search','categoryFilter','sort','installedSearch','installedCategory','installedFilter','installedSort'].map(id => $(id).value).concat($('favoritesOnly').checked));
    if (filterSignature !== nextSignature) { catalogLimit = 24; installedLimit = 24; filterSignature = nextSignature; }
    const cg = $('catalogGrid'); cg.replaceChildren(); filtered.slice(0, catalogLimit).forEach(m => cg.append(card(m)));
    $('moreCatalog').hidden = filtered.length <= catalogLimit;
    $('moreCatalog').textContent = 'Daha fazla göster · ' + Math.max(0, filtered.length - catalogLimit) + ' içerik daha';
    $('resultCount').textContent = filtered.length === mods.length ? mods.length + ' içerik' : filtered.length + ' / ' + mods.length + ' içerik';
    if (!filtered.length) empty(cg, 'Bu filtrelerle içerik bulunamadı', 'Aramayı değiştir veya filtreleri temizleyerek tüm içerikleri gör.', true);
    const selected = HubView.filter(locals, {term: $('installedSearch').value, category: $('installedCategory').value, favorites, status: $('installedFilter').value, sort: $('installedSort').value});
    const ig = $('installedGrid'); ig.replaceChildren(); selected.slice(0, installedLimit).forEach(m => ig.append(card(m, true)));
    $('moreInstalled').hidden = selected.length <= installedLimit;
    $('moreInstalled').textContent = 'Daha fazla göster · ' + Math.max(0, selected.length - installedLimit) + ' mod daha';
    $('installedResults').textContent = selected.length === locals.length ? locals.length + ' mod · ' + locals.filter(m => m.enabled).length + ' etkin' : selected.length + ' / ' + locals.length + ' mod';
    if (!selected.length) empty(ig, locals.length ? 'Bu filtrelerle mod bulunamadı' : 'İlk modunu ekle', locals.length ? 'Aramayı veya durum filtresini değiştir.' : 'Kütüphanedeki kaynakları keşfet veya bilgisayarındaki .fantome paketini içe aktar.', !!locals.length);
    let recovery = $('recovery');
    if (!recovery) { recovery = element('details', 'panel recovery'); recovery.id = 'recovery'; $('installed').append(recovery); }
    const wasOpen = recovery.open;
    recovery.replaceChildren(element('summary', '', 'Kaldırılan modlar ve sürüm yedekleri · ' + (state.removed || []).length));
    (state.removed || []).slice(0, recoveryLimit).forEach(m => {
      const row = element('div', 'recovery-row'); row.dataset.backupId = m.backup_id;
      row.append(element('span', '', m.name + ' · v' + m.version + ' · ' + categories[m.category] + (m.reason === 'update' ? ' · Önceki sürüm' : m.reason === 'interrupted' ? ' · Yarım işlemden korundu' : '')), button('Geri yükle', () => act(() => api.restore(m.backup_id), 'Mod geri yüklendi. Kullanmak için etkinleştir.'), {remote: true}));
      if (api?.inspect_backup) row.append(button('Yedeği incele', () => act(() => api.inspect_backup(m.backup_id), '', {refresh:false, after: info => {
        backupDialog.dataset.backupId = info.id;
        backupTitle.textContent = info.name + ' · v' + info.version;
        backupSummary.textContent = info.files + ' dosya · ' + HubView.bytes(info.bytes);
        backupNote.textContent = info.installed ? 'Bu mod şu anda kütüphanende var. Önce mevcut sürümü kaldırarak yedekle; sonra istediğin eski sürümü geri yükleyebilirsin.' : info.restore_conflict === 'folder' ? 'Bu yedeğin eski klasörü şu anda başka dosyalar içeriyor. Paket olarak kaydet ile dışa aktar, ardından Mod dosyası ekle ile yeniden içe aktar. Yeni klasör seçilir; mevcut dosyalar korunur.' : 'Geri yüklediğinde mod kapalı olarak eklenir. Dışa aktararak başka bir konumda da saklayabilirsin.';
        backupDialog.showModal();
      }}), {remote:true}));
      recovery.append(row);
    });
    if ((state.removed || []).length > recoveryLimit) recovery.append(button('Daha fazla yedek göster', () => { recoveryLimit += 20; render(); }));
    if (!(state.removed || []).length) recovery.append(element('p', '', 'Bu sürümde kaldırılan modların yedekleri burada görünür.'));
    recovery.open = wasOpen;
    renderFilters(); lock(); loadVisibleCovers(); restoreFocus(focus);
  }
  function updateCategory() {
    const skin = $('importCategory').value === 'skins';
    $('championLabel').hidden = !skin; $('championIdLabel').hidden = !skin;
    $('championName').required = skin; $('championId').required = false;
  }
  document.querySelectorAll('nav button').forEach(b => b.onclick = () => page(b.dataset.page));
  const profilePanel = element('dialog'); profilePanel.id = 'createProfileDialog';
  profilePanel.append(element('h2', '', 'Yeni profil oluştur'));
  profilePanel.append(element('p', '', 'Şu an etkin olan modlarını bir adla kaydet. Dosyaların kopyalanmaz; yalnızca seçimlerin saklanır.'));
  const currentSelectionNote = element('p', 'help-note'); currentSelectionNote.id = 'newProfileSummary'; profilePanel.append(currentSelectionNote);
  const saveRow = element('form', 'profile-row profile-create-form'), nameInput = element('input');
  nameInput.id = 'profileName'; nameInput.maxLength = 50; nameInput.placeholder = 'Örn. Klasik görünüm'; nameInput.setAttribute('aria-label', 'Yeni profil adı');
  nameInput.required = true; nameInput.autocomplete = 'off';
  const profileError = element('p', 'field-error'); profileError.id = 'profileError'; profileError.hidden = true; profileError.setAttribute('role', 'alert'); nameInput.setAttribute('aria-describedby', 'profileError');
  const saveProfileButton = button('Seçimleri kaydet', null, {primary:true, remote:true}); saveProfileButton.type = 'submit';
  const nameLabel = element('label', '', 'Profil adı'); nameLabel.htmlFor = 'profileName';
  saveRow.append(nameLabel, nameInput);
  saveRow.onsubmit = event => {
    event.preventDefault(); const name = nameInput.value.trim();
    if (!name) { profileError.textContent = 'Profiline bir ad ver.'; profileError.hidden = false; nameInput.setAttribute('aria-invalid', 'true'); nameInput.focus(); return; }
    act(() => api.save_profile(name), 'Profil kaydedildi.', {after: () => { nameInput.value = ''; profilePanel.close(); }});
  };
  nameInput.oninput = () => { profileError.hidden = true; nameInput.removeAttribute('aria-invalid'); };
  const profileFooter = element('div', 'form-footer'); profileFooter.append(button('Vazgeç', () => profilePanel.close()), saveProfileButton);
  saveRow.append(profileError, profileFooter);
  profilePanel.append(saveRow); document.body.append(profilePanel);
  $('profileHost').className = 'profile-toolbar';
  const newProfile = button('Yeni profil', () => {
    const active = Object.values(state.installed).filter(mod => mod.enabled);
    currentSelectionNote.textContent = active.length ? active.length + ' etkin mod kaydedilecek: ' + active.slice(0,3).map(mod=>mod.name).join(', ') + (active.length>3?' ve '+(active.length-3)+' mod daha.':'.') : 'Etkin mod yok. Bu profili uygulamak tüm mod seçimlerini kapatır.';
    profileError.hidden = true; nameInput.removeAttribute('aria-invalid');
    profilePanel.showModal(); nameInput.focus();
  }, {primary:true, remote:true}); newProfile.id = 'newProfile'; newProfile.prepend(icon('plus'));
  $('profileHost').append(element('span', 'subtle', 'Kayıtlı profiller')); $('profileHost').firstChild.id = 'profileCount';
  $('profileHost').append(newProfile);
  const portableRow = element('div', 'form-footer');
  portableRow.append(button('Profil dosyası içe aktar', () => act(() => api.choose_profile(), '', {refresh:false, after: preview => {
    if (!preview) return;
    $('portableProfileTitle').textContent = preview.name;
    $('portableProfileSummary').textContent = preview.mods.length + ' mod referansı · ' + preview.missing + ' eksik mod' + (preview.different_versions ? ' · ' + preview.different_versions + ' farklı sürüm' : '');
    const list = $('portableProfileMods'); list.replaceChildren();
    preview.mods.forEach(mod => list.append(element('li', '', mod.name + (mod.available ? (mod.version_differs ? ' · Yüklü sürüm farklı' : ' · Hazır') : ' · Kütüphanende yok'))));
    $('portableProfileDialog').showModal();
  }}), {remote:true}));
  $('profileHost').append(portableRow);
  const profileDialog = element('dialog'); profileDialog.id = 'deleteProfileDialog';
  const profileDescription = element('p'); profileDescription.id = 'deleteProfileName';
  profileDialog.append(element('h2', '', 'Profil silinsin mi?'), profileDescription,
    button('Vazgeç', () => profileDialog.close()), button('Profili sil', () => {
      const id = profileDialog.dataset.profileId; profileDialog.close(); act(() => api.remove_profile(id), 'Profil silindi.');
    })); document.body.append(profileDialog);
  const editProfileDialog = element('dialog'); editProfileDialog.id = 'editProfileDialog';
  const editProfileInput = element('input'); editProfileInput.id = 'editProfileInput'; editProfileInput.maxLength = 50; editProfileInput.setAttribute('aria-label', 'Profil adı'); editProfileInput.className = 'full-width';
  const editActions = element('div', 'form-footer');
  editActions.append(button('Adı kaydet', () => act(() => api.rename_profile(editProfileDialog.dataset.profileId, editProfileInput.value), 'Profil adı değiştirildi.', {after: () => editProfileDialog.close()}), {primary: true, remote: true}), button('Vazgeç', () => editProfileDialog.close()));
  const updateDialog = element('dialog'); updateDialog.id = 'updateProfileDialog'; const updateDescription = element('p');
  updateDialog.append(element('h2', '', 'Profil güncellensin mi?'), updateDescription, button('Vazgeç', () => updateDialog.close()), button('Seçimleri güncelle', () => { const id = updateDialog.dataset.profileId; act(() => api.update_profile(id), 'Profil etkin seçimlerinle güncellendi.', {after: () => updateDialog.close()}); }, {primary: true, remote: true})); document.body.append(updateDialog);
  const extraActions = element('div', 'form-footer');
  extraActions.append(button('Etkin seçimlerle güncelle', () => {
    const id = editProfileDialog.dataset.profileId; editProfileDialog.close(); updateDialog.dataset.profileId = id;
    updateDescription.textContent = state.profiles[id].name + ' profilindeki ' + state.profiles[id].mods.length + ' kayıtlı seçimin yerine şu an etkin olan ' + Object.values(state.installed).filter(m => m.enabled).length + ' mod kaydedilecek.'; updateDialog.showModal();
  }), button('Profili sil', () => {
    const id = editProfileDialog.dataset.profileId; editProfileDialog.close();
    $('deleteProfileName').textContent = state.profiles[id].name + ' profili silinecek. Mod dosyaları korunur.';
    profileDialog.dataset.profileId = id; profileDialog.showModal();
  }));
  extraActions.append(button('Profil dosyasını dışa aktar', () => act(() => api.export_profile(editProfileDialog.dataset.profileId), '', {refresh:false, after: result => { if (result?.saved) notify('Profil dosyası kaydedildi. Başka bir OKDEV kurulumunda içe aktarabilirsin.'); }}), {remote:true}));
  editProfileDialog.append(element('h2', '', 'Profili düzenle'), editProfileInput, editActions, element('p', 'subtle', 'Kombinasyonunu yenilemek için mevcut etkin seçimlerini bu profile kaydedebilirsin.'), extraActions); document.body.append(editProfileDialog);
  const backupDialog = element('dialog'); backupDialog.id = 'backupDialog';
  const backupTitle = element('h2'), backupSummary = element('p'), backupNote = element('p', 'subtle');
  const backupActions = element('div', 'form-footer');
  backupActions.append(button('Kapat', () => backupDialog.close()), button('Paket olarak kaydet', () => act(() => api.export_backup(backupDialog.dataset.backupId), '', {refresh:false, after: result => { if (result?.saved) notify('Yedek paket kaydedildi. Mod dosyası ekle ile yeniden içe aktarabilirsin.'); }}), {primary:true,remote:true}));
  backupDialog.append(backupTitle, backupSummary, backupNote, backupActions); document.body.append(backupDialog);
  const importReplaceDialog = element('dialog'); importReplaceDialog.id = 'importReplaceDialog';
  const importReplaceTitle = element('h2', '', 'Mevcut mod güncellenecek'), importReplaceSummary = element('p');
  const importReplaceNote = element('p', 'subtle', 'Mevcut dosyalar sürüm yedeği olarak saklanır. Etkinlik seçimin korunur. Ayrı bir mod eklemek istiyorsan vazgeçip Gelişmiş alanlardan mod kimliğini değiştir.');
  const importReplaceActions = element('div', 'form-footer');
  let pendingImport = null;
  importReplaceDialog.addEventListener('close', () => { pendingImport = null; });
  importReplaceActions.append(button('Vazgeç', () => importReplaceDialog.close()), button('Yedekleyerek güncelle', () => {
    if (!pendingImport) return;
    const pending = pendingImport;
    act(() => api.import_mod(pending.fields, pending.revision), 'Mod güncellendi. Önceki sürüm yedeklerde saklandı.', {after: () => { importReplaceDialog.close(); page('installed'); }});
  }, {primary:true,remote:true}));
  importReplaceDialog.append(importReplaceTitle, importReplaceSummary, importReplaceNote, importReplaceActions); document.body.append(importReplaceDialog);
  document.querySelectorAll('dialog').forEach(dialog => {
    const show = dialog.showModal.bind(dialog);
    dialog.showModal = (...args) => { dialog._focusOrigin = rememberFocus(); return show(...args); };
    dialog.addEventListener('close', () => {
      const note = dialog.querySelector('.dialog-feedback'); if (note) { note.hidden = true; note.textContent = ''; }
      queueMicrotask(() => {
        if (document.querySelector('dialog[open]')) return;
        if (document.activeElement !== document.body && focusAvailable(document.activeElement)) return;
        if (dialog._focusOrigin) restoreFocus(dialog._focusOrigin);
        if (document.activeElement === document.body || !focusAvailable(document.activeElement)) {
          $('title').tabIndex = -1; $('title').focus({preventScroll:true});
        }
      });
    });
    const heading = dialog.querySelector('h2');
    if (heading && !dialog.hasAttribute('aria-labelledby')) {
      heading.id ||= dialog.id + 'Title';
      dialog.setAttribute('aria-labelledby', heading.id);
    }
  });
  $('quickImport').onclick = () => page('publish');
  let closingWindow = false;
  window.addEventListener('okdev-close-request', () => {
    if (!$('closeWindowDialog').open) $('closeWindowDialog').showModal();
  });
  $('keepWindowOpen').onclick = () => { if (!closingWindow) $('closeWindowDialog').close(); };
  $('minimizeWindow').onclick = async () => {
    try {
      if (api?.minimize_window) {
        const result = await api.minimize_window();
        if (!result?.ok) throw new Error(result?.error || 'Pencere küçültülemedi.');
      }
      $('closeWindowDialog').close();
    } catch (_) { $('closeWindowMessage').textContent = 'Pencere küçültülemedi. Birazdan tekrar dene.'; }
  };
  $('closeWindowDialog').addEventListener('cancel', event => { if (closingWindow) event.preventDefault(); });
  $('stopAndClose').onclick = async () => {
    if (closingWindow || !api?.close_window) return;
    let result;
    try { result = await api.close_window(); }
    catch (_) { $('closeWindowMessage').textContent = 'Kapatma isteği iletilemedi. Birazdan tekrar dene.'; return; }
    if (!result?.ok) { $('closeWindowMessage').textContent = result?.error || 'Önce mevcut işlemin tamamlanmasını bekle.'; return; }
    closingWindow = true;
    $('closeWindowTitle').textContent = 'İşlemler güvenle durduruluyor';
    $('closeWindowMessage').textContent = 'Ağ isteği veya başlamış yükleme tamamlanınca pencere kapanacak. Bu işlem kısa bir süre alabilir.';
    $('stopAndClose').disabled = true; $('keepWindowOpen').disabled = true;
  };
  $('showAllActivity').onclick = () => { fullActivity = true; renderActivity(); };
  $('openActivity').onclick = () => { page('diagnostics'); $('activityDetails').open = true; $('activityDetails').scrollIntoView({block:'start',behavior:'smooth'}); };
  $('cancelPortableProfile').onclick = () => $('portableProfileDialog').close();
  $('confirmPortableProfile').onclick = () => act(() => api.import_profile(), 'Profil eklendi. Uygulamadan önce eksik modları tamamla.', {after: () => { $('portableProfileDialog').close(); page('profiles'); }});
  function closeSelectionMenu(restore = true) {
    const menu = $('selectionMenu'), hadFocus = menu.contains(document.activeElement);
    menu.open = false;
    if (restore && hadFocus) menu.querySelector('summary').focus({preventScroll:true});
  }
  $('selectVisible').onclick = () => {
    closeSelectionMenu();
    document.querySelectorAll('#installedGrid [data-mod-id]').forEach(card => selectedMods.add(card.dataset.modId)); render();
  };
  $('clearBulk').onclick = () => { selectedMods.clear(); render(); };
  $('bulkEnable').onclick = () => requestSelection([...selectedMods], 'enable');
  $('bulkDisable').onclick = () => requestSelection([...selectedMods], 'disable');
  $('disableAll').onclick = () => { closeSelectionMenu(); requestSelection([], 'replace'); };
  $('undoSelection').onclick = () => { closeSelectionMenu(); act(() => api.undo_selection(), 'Önceki mod seçimlerin geri yüklendi.'); };
  $('cancelSelection').onclick = () => $('selectionDialog').close();
  $('confirmSelection').onclick = () => {
    const plan = $('selectionDialog')._plan;
    act(() => applyPlan(plan), 'Seçimler kaydedildi. İstersen geri alabilirsin.', {after: () => { $('selectionDialog').close(); selectedMods.clear(); render(); }});
  };
  $('clearDownloads').onclick = () => act(() => api.clear_download_history(), 'Tamamlanan kayıtlar temizlendi. Mod dosyaların korundu.');
  $('repairDownloads').onclick = () => act(() => api.repair_download_history(), 'İndirme kaydı onarıldı. Özgün dosya veri klasöründe yedeklendi.');
  $('moreCatalog').onclick = () => { catalogLimit += 24; render(); };
  $('moreInstalled').onclick = () => { installedLimit += 24; render(); };
  let coverScrollTimer;
  window.addEventListener('scroll', () => { clearTimeout(coverScrollTimer); coverScrollTimer = setTimeout(loadVisibleCovers, 100); }, {passive:true});
  document.querySelectorAll('[data-go]').forEach(b => b.onclick = () => page(b.dataset.go));
  document.querySelectorAll('[data-category]').forEach(b => b.onclick = () => { $('categoryFilter').value = b.dataset.category; render(); });
  $('searchShortcut').onclick = openCommand;
  $('closeCommand').onclick=()=>$('commandDialog').close();
  $('commandSearch').oninput=renderCommands;
  $('commandSearch').onkeydown=event=>{
    if (event.key==='ArrowDown'||event.key==='ArrowUp') {
      event.preventDefault(); if (!commandEntries.length) return;
      commandIndex=(commandIndex+(event.key==='ArrowDown'?1:-1)+commandEntries.length)%commandEntries.length; updateCommandFocus();
    } else if(event.key==='Enter') {event.preventDefault();chooseCommand(commandIndex);}
  };
  $('retryConnection').onclick=()=> {
    if (!initialized) return connectBridge();
    return act(async()=>{await reload();return {ok:true};},'Bağlantı yenilendi.',{refresh:false});
  };
  document.querySelectorAll('[data-view-mode]').forEach(control => { control.dataset.api = ''; control.onclick = () => {
    act(() => api.save_preferences({mod_view:control.dataset.viewMode}), '', {after:()=>{
      const match = [...document.querySelectorAll('[data-view-mode]')].find(b => b.dataset.viewMode === control.dataset.viewMode && b.dataset.viewOwner === control.dataset.viewOwner);
      match?.focus({preventScroll:true});
    }});
  }; });
  document.querySelectorAll('[data-settings-tab]').forEach(tab => {
    tab.onclick = () => settingTab(tab.dataset.settingsTab);
    tab.onkeydown = event => {
      const tabs = [...document.querySelectorAll('[data-settings-tab]')];
      let index = tabs.indexOf(tab);
      if (event.key === 'ArrowRight') index = (index + 1) % tabs.length;
      else if (event.key === 'ArrowLeft') index = (index - 1 + tabs.length) % tabs.length;
      else if (event.key === 'Home') index = 0;
      else if (event.key === 'End') index = tabs.length - 1;
      else return;
      event.preventDefault(); settingTab(tabs[index].dataset.settingsTab, true);
    };
  });
  $('closeDetail').onclick = () => $('detailDialog').close();
  document.querySelectorAll('[data-pref]').forEach(control => control.onchange = () => {
    const value = control.type === 'checkbox' ? control.checked : control.value;
    act(() => api.save_preferences({[control.dataset.pref]: value}), 'Tercihin kaydedildi.');
  });
  window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', applyPreferences);
  $('showCurrentGuide').onclick = () => act(() => api.show_guide(), 'Şampiyonunun rehberi açıldı.', {refresh: false});
  $('hideGuide').onclick = () => act(() => api.hide_guide(), 'Rehber gizlendi.', {refresh: false});
  $('showManualGuide').onclick = () => {
    const c = boot.champions.find(c => HubView.normalize(c.name) === HubView.normalize($('guideManualChampion').value));
    if (!c) { notify('Listeden bir şampiyon seç.', true); $('guideManualChampion').focus(); return; }
    act(() => api.show_guide(c.id, $('guideManualRole').value), c.name + ' rehberi açıldı.', {refresh: false});
  };
  ['search', 'installedSearch'].forEach(id => $(id).oninput = render);
  ['categoryFilter', 'sort', 'favoritesOnly', 'installedCategory', 'installedFilter', 'installedSort'].forEach(id => $(id).onchange = render);
  $('refresh').onclick = () => act(async () => { await reload(true); return {ok: true}; }, 'Kütüphane yenilendi.', {refresh: false});
  $('autoAccept').onchange = () => { const value = $('autoAccept').checked; act(() => api.auto_accept(value), 'Tercihin kaydedildi.'); };
  $('choose').onclick = () => act(async () => ({ok: true, result: await api.choose_mod()}), '', {refresh: false, after: result => {
    if (!result) return;
    selectedFile = true; document.querySelector('.file-picker').classList.add('selected');
    $('importError').hidden = true;
    $('selected').textContent = result.name;
    if (sourceId && result.suggested.version) $('modForm').elements.namedItem('version').value = result.suggested.version;
    if (!sourceId) {
      for (const key of ['name', 'id', 'description', 'version', 'champion', 'champion_id', 'category']) {
        if (result.suggested[key] !== undefined) $('modForm').elements.namedItem(key).value = result.suggested[key];
      }
      updateCategory();
    }
    if (result.warning) $('importSource').textContent = result.warning;
    notify('Dosya seçildi. Bilgileri kontrol edip kütüphanene ekleyebilirsin.');
  }});
  $('chooseCover').onclick = () => act(async () => ({ok: true, result: await api.choose_cover()}), '', {refresh: false, after: name => { if (name) { $('coverName').textContent = name; notify('Kapak görseli seçildi.'); } }});
  $('resetForm').onclick = () => act(() => api.prepare_import(null), 'Form temizlendi.', {refresh: false, after: () => {
    selectedFile = false; document.querySelector('.file-picker').classList.remove('selected'); $('importError').hidden = true;
    sourceId = null; $('modForm').reset(); $('selected').textContent = 'Dosya seçilmedi'; $('coverName').textContent = 'İsteğe bağlı'; $('importSource').textContent = ''; updateCategory();
  }});
  $('modForm').onsubmit = async e => {
    e.preventDefault();
    if (!selectedFile) {
      $('importError').textContent = 'Önce eklemek istediğin .fantome, .zip veya .modpkg dosyasını seç.';
      $('importError').hidden = false; $('choose').focus(); return;
    }
    $('importError').hidden = true;
    const fields = Object.fromEntries(new FormData(e.target));
    let preview;
    if (api?.preview_import) {
      const valid = await act(() => api.preview_import(fields), '', {refresh:false, after: value => { preview = value; }});
      if (!valid || !preview) return;
      if (preview.existing) {
        pendingImport = {fields, revision:preview.revision};
        importReplaceSummary.textContent = preview.existing.name + ' · v' + preview.existing.version + ' → ' + preview.name + ' · v' + preview.version;
        importReplaceDialog.showModal(); return;
      }
    }
    act(() => api.import_mod(fields, preview?.revision), 'Mod eklendi. Etkinleştirmek için seçimini aç.', {after: () => page('installed')});
  };
  $('modForm').addEventListener('invalid', e => { if ($('importAdvanced').contains(e.target)) $('importAdvanced').open = true; }, true);
  $('publishMod').onclick = () => {
    if (!$('modForm').reportValidity() || sourceId) return;
    const fields = Object.fromEntries(new FormData($('modForm'))), token = $('token').value; $('token').value = '';
    act(() => api.publish_mod(fields, token), 'Mod yayımlandı. Katalog birkaç dakika içinde yenilenebilir.');
  };
  $('importCategory').onchange = updateCategory;
  $('draftLane').onchange = () => { $('banChampion').value='';$('pickChampion').value='';renderBanPriority(); };
  $('laneAutomation').onchange = () => {
    const enabled=$('laneAutomation').checked;
    const ready=enabled?Object.values(draftProfiles()).some(p=>p.ban.length):(state.preferences.auto_ban_priority||[]).length;
    act(()=>api.save_preferences({lane_automation:enabled,...(ready?{}:{auto_ban_enabled:false})}), 'Ban listesi tercihi kaydedildi.');
  };
  for(const kind of ['ban','pick']) {
    const prefix=kind==='ban'?'Ban':'Pick';
    $('add'+prefix+'Champion').onclick=()=>{
      const champion=boot.champions.find(c=>HubView.normalize(c.name)===HubView.normalize($(kind+'Champion').value.trim()));
      const ids=draftList(kind);
      if(!champion||ids.includes(champion.id)||ids.length>=10) {$(kind+'ListStatus').textContent='Listede olmayan geçerli bir şampiyon seç (en fazla 10).';return;}
      saveDraftList(kind,[...ids,champion.id]);$(kind+'Champion').value='';
    };
    $(kind+'Champion').onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();$('add'+prefix+'Champion').click();}};
  }
  boot.champions.forEach(c => { const o = element('option'); o.value = c.name; $('championList').append(o); });
  $('championName').oninput = () => {
    const c = boot.champions.find(c => HubView.normalize(c.name) === HubView.normalize($('championName').value));
    $('championId').value = c ? c.id : '';
  };
  $('mobalytics').onclick = () => act(() => api.mobalytics(false), 'Mobalytics açıldı.', {refresh: false});
  $('mobalyticsBrowser').onclick = () => act(() => api.mobalytics(true), 'Mobalytics tarayıcıda açıldı.', {refresh: false});
  $('openData').onclick = () => act(() => api.open_data_folder(), 'Veri klasörü açıldı.', {refresh: false});
  $('appVersion').textContent = 'Sürüm ' + (boot.version || '—') + ' · Windows masaüstü uygulaması';
  $('releaseTag').textContent=(boot.version||'2.0.0').split('.').slice(0,2).join('.');
  for (const [id, destination] of [['openReleases','releases'], ['openSupport','support'], ['openProject','source']]) {
    $(id).onclick = () => act(() => api.open_project_page(destination), 'Proje sayfası tarayıcıda açıldı.', {refresh:false});
  }
  $('recoverLibrary').onclick = () => act(() => api.recover_library(), 'Yarım kalan işlemler kontrol edildi. Dosyaların korundu.');
  $('exportDiagnostics').onclick = () => act(() => api.export_diagnostics(), '', {refresh: false, after: result => { if (result.saved) notify('Destek raporu kaydedildi. İstersen destek alırken paylaşabilirsin.'); }});
  $('checkDiagnostics').onclick = () => act(() => api.diagnostics(), 'Kontroller tamamlandı.', {refresh: false, after: report => {
    $('diagnosticsTime').textContent = 'OKDEV ' + report.version + ' · ' + new Date(report.checked_at).toLocaleString('tr') + ' · ' + report.note;
    const storage = $('storageGrid'); storage.replaceChildren();
    for (const item of report.storage || []) {
      const card = element('div', 'storage-card');
      card.append(element('h3', '', item.name), element('strong', '', (item.complete ? '' : 'En az ') + HubView.bytes(item.bytes)), element('span', 'subtle', item.files.toLocaleString('tr') + ' dosya'));
      storage.append(card);
    }
    $('storageSummary').hidden = !storage.children.length;
    const target = $('diagnosticsGrid'); target.replaceChildren();
    report.checks.forEach(c => { const panel = element('article', 'panel diagnostic ' + c.status); panel.append(element('span', 'badge', {ok: 'Hazır', warning: 'Kontrol gerekli', info: 'Bilgi'}[c.status]), element('h3', '', c.name), element('p', '', c.detail)); target.append(panel); });
  }});
  $('showStorageBackups').onclick = () => { page('installed'); $('recovery').open = true; $('recovery').querySelector('summary').focus(); $('recovery').scrollIntoView({block:'center'}); };
  $('cancelRemove').onclick = () => $('removeDialog').close();
  $('cancelDownload').onclick = async () => {
    $('cancelDownload').disabled = true;
    try { const r = await api.cancel_download(); notify(r.ok ? 'İptal isteği alındı. Ağ işlemi tamamlanınca durdurulacak.' : r.error, !r.ok, true); }
    catch (_) { notify('İptal isteği iletilemedi.', true); }
  };
  $('confirmRemove').onclick = () => { const id = removeId; $('removeDialog').close(); act(() => api.remove(id), 'Mod kaldırıldı; dosyalar yerel yedekte saklandı.'); };
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k' && !document.querySelector('dialog[open]')) { e.preventDefault(); openCommand(); }
    if (e.key === 'Escape') { $('status').textContent = ''; if ($('selectionMenu').open) closeSelectionMenu(); }
  });
  document.addEventListener('click', event => { if (!$('selectionMenu').contains(event.target)) closeSelectionMenu(false); });
  async function connectBridge() {
    if (connecting || busy) return;
    const available = window.pywebview?.api;
    if (!available?.snapshot) { setConnection(false); return; }
    connecting = true; api = available;
    $('loadingBanner').hidden = false;
    try { await act(async () => { await reload(); return {ok: true}; }, '', {refresh: false}); }
    finally { connecting = false; $('loadingBanner').hidden = true; }
  }
  window.addEventListener('pywebviewready', connectBridge);
  setTimeout(() => { if (!initialized && !connecting) setConnection(false); }, 8000);
  let guidePolling = false;
  let downloadPolling = false;
  setInterval(async()=>{
    if (!api?.state_revision || busy || syncPolling || document.hidden) return;
    syncPolling=true;
    try {
      const revision=await readBridge(api.state_revision());
      if (busy) return;
      if (revision!==state.revision) await reload(false,true);
      else setConnection(true);
    } catch (_) { setConnection(false); }
    finally {syncPolling=false;}
  },3000);
  setInterval(async () => {
    if (!api?.downloads_status || busy || downloadPolling || document.hidden) return;
    downloadPolling = true;
    const epoch = stateEpoch;
    try {
      const queue = await readBridge(api.downloads_status());
      if (busy || epoch !== stateEpoch) return;
      const completedBefore = new Set((state.downloads?.jobs || []).filter(j => j.status === 'completed').map(j => j.id));
      const newlyCompleted = queue.jobs.some(j => j.status === 'completed' && !completedBefore.has(j.id));
      if (newlyCompleted) {
        if (await reload(false, true)) notify('İndirme tamamlandı. Modlarım’dan etkinleştirebilirsin.');
      } else { state.downloads = queue; renderDownloads(); }
    } catch (_) { /* Keep the last visible state during bridge reconnection. */ }
    finally { downloadPolling = false; }
  }, 1000);
  setInterval(async () => {
    if (!api || busy || guidePolling || document.hidden) return;
    guidePolling = true;
    const epoch = stateEpoch;
    try {
      const value = await readBridge(api.guide_state());
      if (busy || epoch !== stateEpoch) return;
      Object.assign(state, value); applyPreferences(); renderGuide();
    }
    catch (_) { /* Full actions report bridge errors; polling never interrupts a task. */ }
    finally { guidePolling = false; }
  }, 2000);
  updateCategory(); render();
  if (window.pywebview?.api?.snapshot) queueMicrotask(() => { if (!initialized) connectBridge(); });
}
