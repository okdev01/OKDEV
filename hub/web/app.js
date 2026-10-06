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
  let state = {catalog: [], installed: {}, settings: {favorites: []}, preferences: {}, guide: {}, companion: {}}, busy = false, api = null;
  let sourceId = null, removeId = null, noticeTimer;
  let stateEpoch = 0, snapshotRequest = 0;
  const $ = id => document.getElementById(id);
  const boot = window.HUB_DATA || {sources: [], champions: []};
  const categories = {skins: 'Şampiyon', ui: 'HUD / Arayüz', maps: 'Harita', fonts: 'Yazı tipi', announcers: 'Spiker'};
  const titles = {home: 'Oyuna kendi tarzını kat.', library: 'Keşfet', installed: 'Senin modların', profiles: 'Mod profillerin', assistants: 'Tam sana göre.', diagnostics: 'Sistem durumu', guides: 'Oyun rehberin', publish: 'Mod ekle', downloads: 'İndirmelerin'};
  let currentPage = 'home';
  const selectedMods = new Set();
  let catalogLimit = 24, installedLimit = 24, recoveryLimit = 20, filterSignature = '';
  const coverCache = new Map(), pendingCovers = new Set();

  function element(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }
  function rememberFocus() {
    const focused = document.activeElement;
    const owner = focused?.closest('.card[data-mod-id],.download-job[data-job-id],.profile-card[data-profile-id],.recovery-row[data-backup-id]');
    const attribute = owner && ['data-mod-id','data-job-id','data-profile-id','data-backup-id'].find(key => owner.hasAttribute(key));
    return {focused, page:currentPage, attribute, value:attribute && owner.getAttribute(attribute),
      index:owner ? [...owner.querySelectorAll('button,input,select,textarea')].indexOf(focused) : -1};
  }
  function restoreFocus(saved) {
    if (!saved.focused || saved.focused === document.body || currentPage !== saved.page
        || document.activeElement !== document.body || document.querySelector('dialog[open]')) return;
    if (saved.focused.isConnected && !saved.focused.disabled && !saved.focused.closest('[hidden]')) {
      saved.focused.focus({preventScroll:true}); return;
    }
    if (!saved.attribute || saved.index < 0) return;
    const owner = [...$(currentPage).querySelectorAll('[' + saved.attribute + ']')].find(node => node.getAttribute(saved.attribute) === saved.value);
    const control = owner?.querySelectorAll('button,input,select,textarea')[saved.index];
    if (control && !control.disabled) control.focus({preventScroll:true});
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
    status.append(element('span', 'status-message', message), dismiss);
    if (!persistent && !error) noticeTimer = setTimeout(() => {
      if (!status.contains(document.activeElement)) status.replaceChildren();
    }, 6000);
  }
  function lock() {
    document.querySelectorAll('[data-api]').forEach(e => e.disabled = busy || !api);
    document.querySelectorAll('#modForm input,#modForm textarea,#modForm select,#resetForm').forEach(e => e.disabled = busy);
    $('publishMod').disabled = busy || !api || !!sourceId;
    $('showCurrentGuide').disabled = busy || !api || !state.preferences?.mobalytics_enabled || !state.guide?.pick;
    $('showManualGuide').disabled = busy || !api || !state.preferences?.mobalytics_enabled;
    $('main').setAttribute('aria-busy', String(busy));
    renderBulk();
    $('clearDownloads').disabled = busy || !api || !(state.downloads?.jobs || []).some(j => !['queued', 'downloading', 'installing'].includes(j.status));
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
      if (filtered) { ['search', 'installedSearch', 'categoryFilter', 'installedCategory'].forEach(id => $(id).value = ''); $('favoritesOnly').checked = false; $('installedFilter').value = 'all'; $('installedCategory').value = ''; render(); }
      else page('publish');
    })); target.append(e);
  }
  async function reload(refresh = false, background = false) {
    const request = ++snapshotRequest, epoch = stateEpoch;
    const value = await api.snapshot(refresh);
    if (request !== snapshotRequest || (background && (busy || epoch !== stateEpoch))) return false;
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
      if (refresh) {
        try { await reload(); }
        catch (_) { notify('İşlem tamamlandı, ancak liste yenilenemedi. Kütüphaneyi yenile.', true); return true; }
      }
      notify(message);
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
    const b = button(marked ? '★' : '☆', () => act(() => api.favorite(mod.id, !marked), marked ? 'Favorilerden çıkarıldı.' : 'Favorilere eklendi.'), {remote: true});
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
      const form = $('modForm'); form.reset();
      for (const key of ['id', 'name', 'champion', 'champion_id', 'version', 'description', 'category']) form.elements.namedItem(key).value = mod[key] ?? '';
      $('importSource').textContent = mod.name + ' · ' + mod.author + ' · ' + mod.license;
      $('selected').textContent = 'Dosya seçilmedi'; $('coverName').textContent = 'İsteğe bağlı';
      updateCategory(); page('publish');
    }});
  }
  function previewFor(mod) {
    const cached = coverCache.get(mod.id);
    return mod.preview_data || state.installed[mod.id]?.preview_data
      || (cached?.key === state.installed[mod.id]?.cover_key ? cached?.data : null)
      || mod.image_url || boot.sources.find(source => source.id === mod.id)?.image_url;
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
    const e = element('article', 'card');
    e.dataset.modId = mod.id;
    const art = element('div', 'art art-' + category);
    art.dataset.previewId = mod.id;
    const monogram = category === 'skins' ? (mod.champion || mod.name).slice(0, 2).toUpperCase() : ({ui: 'HUD', fonts: 'Aa', maps: 'MAP', announcers: 'VO'}[category] || 'MOD');
    art.append(element('span', 'art-letter', monogram));
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
    const badge = element('span', 'badge' + (local && mod.enabled ? ' enabled' : ''), local ? (mod.enabled ? 'Etkin' : 'Kapalı') : (source ? (state.installed[mod.id] ? 'Yüklü · RuneForge' : 'RuneForge') : 'OKDEV kataloğu'));
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
    const target = $('detailContent'); target.replaceChildren();
    const art = element('div', 'detail-art', (mod.champion || mod.name).slice(0, 2).toUpperCase());
    art.dataset.previewId = mod.id;
    const preview = previewFor(mod);
    if (preview) { const img = element('img'); img.src = preview; img.alt = mod.name; img.referrerPolicy = 'no-referrer'; img.onerror = () => { art.textContent = (mod.champion || mod.name).slice(0, 2).toUpperCase(); }; art.replaceChildren(img); }
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
      actions.append(button('Modu kaldır', () => { $('detailDialog').close(); removeId = mod.id; $('removeDescription').textContent = mod.name + ' kütüphanenden kaldırılacak.'; $('removeDialog').showModal(); }, {remote: true}));
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
    target.append(actions); $('detailDialog').showModal(); loadVisibleCovers();
  }
  function applyPreferences() {
    const prefs = state.preferences || {};
    const theme = prefs.theme || 'dark';
    document.documentElement.dataset.theme = theme === 'system' ? (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark') : theme;
    document.body.classList.toggle('compact', !!prefs.compact_cards);
    document.body.classList.toggle('reduce-motion', !!prefs.reduce_motion);
    document.querySelectorAll('[data-pref]').forEach(control => {
      const value = prefs[control.dataset.pref];
      if (control.type === 'checkbox') control.checked = !!value;
      else if (value !== undefined) control.value = value;
    });
    $('settingsHotkey').textContent = prefs.mobalytics_hotkey || 'Ctrl+Shift+B';
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
    ['bulkEnable', 'bulkDisable', 'clearBulk'].forEach(id => $(id).disabled = busy || !api || !selectedMods.size);
    $('disableAll').disabled = busy || !api || !Object.values(state.installed).some(m => m.enabled);
    $('undoSelection').disabled = busy || !api || !state.selection_undo?.available;
    $('undoSelection').hidden = !state.selection_undo?.available;
  }
  async function requestSelection(ids, mode, alwaysConfirm = true) {
    if (!api?.preview_selection) {
      if (ids.length === 1) return act(() => api.enable(ids[0], mode === 'enable'), 'Mod seçimi kaydedildi.');
      return;
    }
    let plan = null;
    const ok = await act(() => api.preview_selection(ids, mode), '', {refresh:false, after: value => { plan = value; }});
    if (!ok || !plan) return;
    if (!plan.changed) { notify('Seçimlerin zaten bu durumda.'); return; }
    const replaced = mode === 'enable' && plan.disable.length > 0;
    if (!alwaysConfirm && !replaced) {
      return act(() => api.apply_selection(plan.requested, plan.mode, plan.revision), 'Seçim kaydedildi. İstersen geri alabilirsin.');
    }
    const dialog = $('selectionDialog'); dialog._plan = plan;
    $('selectionTitle').textContent = replaced ? 'Etkin mod değiştirilsin mi?' : 'Mod seçimlerini uygula';
    const detail = $('selectionChanges'); detail.replaceChildren();
    for (const [label, mods, className] of [['Etkinleştirilecek', plan.enable, 'enable'], ['Kapatılacak', plan.disable, 'disable']]) {
      if (!mods.length) continue;
      const block = element('div', 'selection-change ' + className); block.append(element('h3', '', label + ' · ' + mods.length));
      const list = element('ul'); mods.forEach(mod => list.append(element('li', '', mod.name))); block.append(list); detail.append(block);
    }
    dialog.showModal();
  }
  function renderHome(locals) {
    $('navInstalled').textContent = locals.length;
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
    Object.entries(state.profiles || {}).forEach(([id, profile]) => {
      const panel = element('article', 'profile-card'); panel.dataset.profileId = id;
      const heading = element('div', 'profile-card-heading');
      const manage = button('⋯', () => { $('editProfileDialog').dataset.profileId = id; $('editProfileInput').value = profile.name; $('editProfileDialog').showModal(); });
      manage.setAttribute('aria-label', profile.name + ' profilini düzenle');
      heading.append(element('h3', '', profile.name), manage);
      const active = Object.values(state.installed).filter(m => m.enabled).map(m => m.id).sort();
      const matches = JSON.stringify([...profile.mods].sort()) === JSON.stringify(active);
      const missing = profile.mods.filter(id => !state.installed[id] || state.installed[id].files_available === false);
      panel.append(heading, element('span', 'subtle', profile.mods.length + ' kayıtlı seçim' + (matches ? ' · Şu anki seçimlerin' : '')));
      if (missing.length) panel.append(element('p', 'profile-missing', missing.length + ' mod eksik. Uygulamadan önce modları ekle veya geri yükle.'));
      const tags = element('div', 'profile-tags');
      profile.mods.slice(0, 6).forEach(modId => tags.append(element('span', '', state.installed[modId]?.name || 'Eksik mod')));
      if (profile.mods.length > 6) tags.append(element('span', '', '+' + (profile.mods.length - 6)));
      if (!profile.mods.length) tags.append(element('span', '', 'Tüm modları kapatan profil'));
      panel.append(tags, button('Bu profili uygula', () => {
        if (missing.length) { notify('Bu profilde eksik modlar var. Önce modları ekle veya geri yükle.', true); return; }
        if (api?.preview_selection) requestSelection(profile.mods, 'replace');
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
    $('resultCount').textContent = filtered.length + ' / ' + mods.length + ' içerik';
    if (!filtered.length) empty(cg, 'Bu filtrelerle içerik bulunamadı', 'Aramayı değiştir veya filtreleri temizleyerek tüm içerikleri gör.', true);
    const selected = HubView.filter(locals, {term: $('installedSearch').value, category: $('installedCategory').value, favorites, status: $('installedFilter').value, sort: $('installedSort').value});
    const ig = $('installedGrid'); ig.replaceChildren(); selected.slice(0, installedLimit).forEach(m => ig.append(card(m, true)));
    $('moreInstalled').hidden = selected.length <= installedLimit;
    $('moreInstalled').textContent = 'Daha fazla göster · ' + Math.max(0, selected.length - installedLimit) + ' mod daha';
    $('installedResults').textContent = selected.length + ' / ' + locals.length + ' mod';
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
    lock(); loadVisibleCovers(); restoreFocus(focus);
  }
  function updateCategory() {
    const skin = $('importCategory').value === 'skins';
    $('championLabel').hidden = !skin; $('championIdLabel').hidden = !skin;
    $('championName').required = skin; $('championId').required = false;
  }
  document.querySelectorAll('nav button').forEach(b => b.onclick = () => page(b.dataset.page));
  const profilePanel = element('div', 'panel profile-panel');
  profilePanel.append(element('h2', '', 'Yeni profil oluştur'));
  profilePanel.append(element('p', '', 'Şu an etkin olan modlarını bir adla kaydet. Dosyaların kopyalanmaz; yalnızca seçimlerin saklanır.'));
  const saveRow = element('div', 'profile-row'), nameInput = element('input');
  nameInput.id = 'profileName'; nameInput.maxLength = 50; nameInput.placeholder = 'Örn. Klasik görünüm'; nameInput.setAttribute('aria-label', 'Yeni profil adı');
  saveRow.append(nameInput, button('Seçimleri kaydet', () => act(() => api.save_profile(nameInput.value), 'Profil kaydedildi.', {after: () => nameInput.value = ''}), {remote: true}));
  profilePanel.append(saveRow); $('profileHost').append(profilePanel);
  const portableRow = element('div', 'form-footer');
  portableRow.append(button('Profil dosyası içe aktar', () => act(() => api.choose_profile(), '', {refresh:false, after: preview => {
    if (!preview) return;
    $('portableProfileTitle').textContent = preview.name;
    $('portableProfileSummary').textContent = preview.mods.length + ' mod referansı · ' + preview.missing + ' eksik mod' + (preview.different_versions ? ' · ' + preview.different_versions + ' farklı sürüm' : '');
    const list = $('portableProfileMods'); list.replaceChildren();
    preview.mods.forEach(mod => list.append(element('li', '', mod.name + (mod.available ? (mod.version_differs ? ' · Yüklü sürüm farklı' : ' · Hazır') : ' · Kütüphanende yok'))));
    $('portableProfileDialog').showModal();
  }}), {remote:true}), element('span', 'subtle', 'Profil dosyaları yalnızca seçimleri içerir; mod paketlerini içermez.'));
  profilePanel.append(portableRow);
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
  $('selectVisible').onclick = () => {
    document.querySelectorAll('#installedGrid [data-mod-id]').forEach(card => selectedMods.add(card.dataset.modId)); render();
  };
  $('clearBulk').onclick = () => { selectedMods.clear(); render(); };
  $('bulkEnable').onclick = () => requestSelection([...selectedMods], 'enable');
  $('bulkDisable').onclick = () => requestSelection([...selectedMods], 'disable');
  $('disableAll').onclick = () => requestSelection([], 'replace');
  $('undoSelection').onclick = () => act(() => api.undo_selection(), 'Önceki mod seçimlerin geri yüklendi.');
  $('cancelSelection').onclick = () => $('selectionDialog').close();
  $('confirmSelection').onclick = () => {
    const plan = $('selectionDialog')._plan;
    act(() => api.apply_selection(plan.requested, plan.mode, plan.revision), 'Seçimler kaydedildi. İstersen geri alabilirsin.', {after: () => { $('selectionDialog').close(); selectedMods.clear(); render(); }});
  };
  $('clearDownloads').onclick = () => act(() => api.clear_download_history(), 'Tamamlanan kayıtlar temizlendi. Mod dosyaların korundu.');
  $('repairDownloads').onclick = () => act(() => api.repair_download_history(), 'İndirme kaydı onarıldı. Özgün dosya veri klasöründe yedeklendi.');
  $('moreCatalog').onclick = () => { catalogLimit += 24; render(); };
  $('moreInstalled').onclick = () => { installedLimit += 24; render(); };
  let coverScrollTimer;
  window.addEventListener('scroll', () => { clearTimeout(coverScrollTimer); coverScrollTimer = setTimeout(loadVisibleCovers, 100); }, {passive:true});
  document.querySelectorAll('[data-go]').forEach(b => b.onclick = () => page(b.dataset.go));
  document.querySelectorAll('[data-category]').forEach(b => b.onclick = () => { $('categoryFilter').value = b.dataset.category; render(); });
  $('searchShortcut').onclick = () => { page('library'); $('search').focus(); };
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
  $('choose').onclick = () => act(async () => ({ok: true, result: await api.choose_mod()}), 'Dosya seçimi tamamlandı.', {refresh: false, after: result => {
    if (!result) return;
    $('selected').textContent = result.name;
    if (sourceId && result.suggested.version) $('modForm').elements.namedItem('version').value = result.suggested.version;
    if (!sourceId) {
      for (const key of ['name', 'id', 'description', 'version', 'champion', 'champion_id', 'category']) {
        if (result.suggested[key] !== undefined) $('modForm').elements.namedItem(key).value = result.suggested[key];
      }
      updateCategory();
    }
    if (result.warning) $('importSource').textContent = result.warning;
  }});
  $('chooseCover').onclick = () => act(async () => ({ok: true, result: await api.choose_cover()}), 'Görsel seçimi tamamlandı.', {refresh: false, after: name => { if (name) $('coverName').textContent = name; }});
  $('resetForm').onclick = () => act(() => api.prepare_import(null), 'Form temizlendi.', {refresh: false, after: () => {
    sourceId = null; $('modForm').reset(); $('selected').textContent = 'Dosya seçilmedi'; $('coverName').textContent = 'İsteğe bağlı'; $('importSource').textContent = ''; updateCategory();
  }});
  $('modForm').onsubmit = async e => {
    e.preventDefault(); const fields = Object.fromEntries(new FormData(e.target));
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
  boot.champions.forEach(c => { const o = element('option'); o.value = c.name; $('championList').append(o); });
  $('championName').oninput = () => {
    const c = boot.champions.find(c => HubView.normalize(c.name) === HubView.normalize($('championName').value));
    $('championId').value = c ? c.id : '';
  };
  $('mobalytics').onclick = () => act(() => api.mobalytics(false), 'Mobalytics açıldı.', {refresh: false});
  $('mobalyticsBrowser').onclick = () => act(() => api.mobalytics(true), 'Mobalytics tarayıcıda açıldı.', {refresh: false});
  $('openData').onclick = () => act(() => api.open_data_folder(), 'Veri klasörü açıldı.', {refresh: false});
  $('appVersion').textContent = 'Sürüm ' + (boot.version || '—') + ' · Windows masaüstü uygulaması';
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
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k' && !document.querySelector('dialog[open]')) { e.preventDefault(); page('library'); $('search').focus(); }
    if (e.key === 'Escape') $('status').textContent = '';
  });
  window.addEventListener('pywebviewready', async () => {
    api = window.pywebview.api; $('connection').textContent = 'OKDEV ile bağlı';
    await act(async () => { await reload(); return {ok: true}; }, 'Kütüphane hazır.', {refresh: false});
  });
  let guidePolling = false;
  let downloadPolling = false;
  setInterval(async () => {
    if (!api?.downloads_status || busy || downloadPolling || document.hidden) return;
    downloadPolling = true;
    const epoch = stateEpoch;
    try {
      const queue = await api.downloads_status();
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
      const value = await api.guide_state();
      if (busy || epoch !== stateEpoch) return;
      Object.assign(state, value); applyPreferences(); renderGuide();
    }
    catch (_) { /* Full actions report bridge errors; polling never interrupts a task. */ }
    finally { guidePolling = false; }
  }, 2000);
  updateCategory(); render();
}
