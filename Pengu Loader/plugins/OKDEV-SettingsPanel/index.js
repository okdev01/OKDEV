/**
 * @name OKDEV-SettingsPanel
 * @author Rose Team
 * @description Settings panel for OKDEV
 * @link https://github.com/FlorentTariolle/ROSE-SettingsPanel
 */
(function initSettingsPanel() {
  const LOG_PREFIX = "[OKDEV-SettingsPanel]";
  const SUPPORT_URL = "https://github.com/okdev01/OKDEV/issues";
  const GITHUB_URL = "https://github.com/okdev01/OKDEV";

  const PANEL_ID = "okdev-settings-panel";
  const FLYOUT_ID = "okdev-settings-flyout";

  // OKDEV's menu language (OKDEV-I18n); English until it has loaded
  const t = (text, vars) =>
    window.OKDEVI18n
      ? window.OKDEVI18n.t(text, vars)
      : text.replace(/\{(\w+)\}/g, (m, k) => (vars && k in vars ? String(vars[k]) : m));
  // A finished English text from OKDEV (error message...), translated when it is a known one
  const tAny = (text) => (window.OKDEVI18n ? window.OKDEVI18n.tAny(text) : text);

  /**
   * Escape HTML special characters to prevent XSS (CWE-79)
   * @param {string} str - String to escape
   * @returns {string} Escaped string safe for innerHTML
   */
  function escapeHtml(str) {
    if (typeof str !== 'string') return str;
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function createActionButton() {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "okdev-client-button";
    return button;
  }

  function topOwnedDialog() {
    return [...document.querySelectorAll('[data-okdev-dialog]')].filter(node => node.isConnected)
      .sort((a, b) => (Number(getComputedStyle(a).zIndex) || 0) - (Number(getComputedStyle(b).zIndex) || 0)).pop();
  }

  function dialogControls(dialog) {
    return [...dialog.querySelectorAll('button, input, select, textarea, a[href], [tabindex]')]
      .filter(node => !node.disabled && node.tabIndex >= 0 && node.getClientRects().length &&
        getComputedStyle(node).visibility !== 'hidden' && !node.closest('[inert]'));
  }

  function prepareOwnedDialog(dialog, label, onClose) {
    dialog.dir = window.OKDEVI18n?.direction === 'rtl' ? 'rtl' : 'ltr';
    dialog.dataset.okdevDialog = 'true';
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    dialog.setAttribute('aria-label', t(label));
    dialog.tabIndex = -1;
    dialog._returnFocus = document.activeElement;
    dialog._dismiss = onClose || (() => removeOwnedDialog(dialog));
    queueMicrotask(() => {
      if (!dialog.isConnected || topOwnedDialog() !== dialog) return;
      syncOwnedDialogs();
      const target = dialog.querySelector('input[type="search"], input[type="text"]') || dialogControls(dialog)[0] || dialog;
      target.focus();
    });
  }

  function syncOwnedDialogs() {
    const top = topOwnedDialog();
    document.querySelectorAll('[data-okdev-dialog]').forEach(node => {
      node.inert = node !== top;
      if (node !== top) node.setAttribute('aria-hidden', 'true');
      else node.removeAttribute('aria-hidden');
    });
  }

  function removeOwnedDialog(dialog) {
    if (!dialog) return;
    clearTimeout(dialog._requestTimer);
    const origin = dialog._returnFocus;
    dialog.remove();
    syncOwnedDialogs();
    if (dialog.id === 'okdev-diagnostics-dialog') diagnosticsDialog = null;
    queueMicrotask(() => {
      const top = topOwnedDialog();
      if (origin?.isConnected && (!top || top.contains(origin))) origin.focus();
      else if (top && !top.contains(document.activeElement)) (dialogControls(top)[0] || top).focus();
    });
  }

  document.addEventListener('keydown', event => {
    const dialog = topOwnedDialog();
    if (!dialog || event.defaultPrevented) return;
    if (event.key === 'Escape') {
      // A native select owns Escape while its popup is open.
      if (event.target.tagName === 'SELECT') return;
      event.preventDefault();
      event.stopPropagation();
      dialog._dismiss?.();
    } else if (event.key === 'Tab') {
      const controls = dialogControls(dialog), first = controls[0], last = controls.at(-1);
      if (!first) { event.preventDefault(); dialog.focus(); }
      else if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {
        event.preventDefault(); first.focus();
      }
    }
  });

  function showSettingsFeedback(message, error = false) {
    const status = document.getElementById('okdev-settings-feedback');
    if (!status) return;
    status.dataset.error = String(error);
    status.setAttribute('role', error ? 'alert' : 'status');
    status.textContent = message;
  }

  function showPathStatus(kind) {
    const status = document.getElementById('path-status');
    if (!status) return;
    const labels = {valid:'Game path is valid', invalid:'Game path is invalid', pending:'Validating game path…'};
    const paths = {valid:'M5 12l4 4L19 6', invalid:'M6 6l12 12M18 6L6 18', pending:'M12 7v5l3 2'};
    const label = labels[kind] ? t(labels[kind]) : '';
    status.title = label;
    status.setAttribute('aria-label', label);
    status.dataset.state = kind;
    status.innerHTML = paths[kind] ? `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[kind]}"/></svg>` : '';
  }

  function finishManagedRequest(dialog) {
    if (!dialog) return;
    clearTimeout(dialog._requestTimer);
    dialog._requestTimer = null;
    dialog.dataset.pending = 'false';
    dialog.setAttribute('aria-busy', 'false');
    for (const [button, text] of dialog._pendingButtons || []) {
      button.disabled = false;
      button.textContent = text;
    }
    dialog._pendingButtons = [];
  }

  function showManagedFailure(dialog, message) {
    const status = dialog?.querySelector('.okdev-management-feedback');
    if (!status) return;
    status.hidden = false;
    status.replaceChildren(document.createTextNode(tAny(message) + ' '));
    const retry = createActionButton();
    retry.textContent = t('Reload list');
    retry.addEventListener('click', () => {
      if (dialog.id === 'champion-mods-manage-dialog') openChampionModsList(window.__okdevManageChampionId);
      else openCategoryModsList(window.__okdevManageCategory);
    });
    status.appendChild(retry);
  }

  function sendManagedRequest(dialog, payload) {
    if (!dialog || dialog.dataset.pending === 'true') return;
    if (!bridge?.ready) {
      showManagedFailure(dialog, t('Connection lost. Reopen OKDEV and try again.'));
      return;
    }
    dialog.dataset.pending = 'true';
    dialog.setAttribute('aria-busy', 'true');
    dialog._pendingButtons = [...dialog.querySelectorAll('.mod-delete-button,.mod-rename-button')].map(button => [button, button.textContent]);
    for (const [button] of dialog._pendingButtons) button.disabled = true;
    dialog._requestTimer = setTimeout(() => {
      if (!dialog.isConnected) return;
      finishManagedRequest(dialog);
      showManagedFailure(dialog, t('No response received. Reload the list to check the result.'));
    }, 15000);
    try { bridge.send(payload); }
    catch (error) { finishManagedRequest(dialog); showManagedFailure(dialog, String(error)); }
  }

  let bridge = null;

  function waitForBridge() {
    return new Promise((resolve, reject) => {
      const timeout = 10000;
      const interval = 50;
      let elapsed = 0;
      const check = () => {
        if (window.__okdevBridge) return resolve(window.__okdevBridge);
        elapsed += interval;
        if (elapsed >= timeout) return reject(new Error("Bridge not available"));
        setTimeout(check, interval);
      };
      check();
    });
  }

  let settingsPanel = null;
  let currentSettings = {
    threshold: 0.5,
    monitorAutoResumeTimeout: 60,
    autostart: false,
    hideEmptyCategories: false,
    gamePath: "",
    gamePathValid: false,
    version: "",
  };
  let pathValidationTimeout = null;

  function getCSSRules() {
    return `
    @keyframes okdevWarningPulse {
      0%   { filter: drop-shadow(0 0 0 rgba(255, 70, 70, 0.00)) drop-shadow(0 0 0 rgba(255, 70, 70, 0.00)); opacity: 0.95; }
      50%  { filter: drop-shadow(0 0 6px rgba(255, 70, 70, 0.90)) drop-shadow(0 0 12px rgba(255, 70, 70, 0.45)); opacity: 1.00; }
      100% { filter: drop-shadow(0 0 0 rgba(255, 70, 70, 0.00)) drop-shadow(0 0 0 rgba(255, 70, 70, 0.00)); opacity: 0.95; }
    }

    .okdev-warning-glow {
      animation: okdevWarningPulse 1.35s ease-in-out infinite;
      will-change: filter, opacity;
    }

    @font-face {
      font-family: "Beaufort for LOL";
      src: url("http://127.0.0.1:${window.__okdevBridge ? window.__okdevBridge.port : 50000}/asset/BeaufortforLOL-Regular.ttf") format("truetype");
      font-weight: normal;
      font-style: normal;
      font-display: swap;
    }
    
    @font-face {
      font-family: "Beaufort for LOL";
      src: url("http://127.0.0.1:${window.__okdevBridge ? window.__okdevBridge.port : 50000}/asset/BeaufortforLOL-Bold.ttf") format("truetype");
      font-weight: bold;
      font-style: normal;
      font-display: swap;
    }

    /* Diagnostics / Troubleshooting dialog scrollbar (avoid native Windows scrollbar look) */
    #okdev-diagnostics-body {
      scrollbar-width: thin;
      scrollbar-color: #463714 rgba(0, 0, 0, 0.25);
    }

    #okdev-diagnostics-body::-webkit-scrollbar {
      width: 10px;
    }

    #okdev-diagnostics-body::-webkit-scrollbar:horizontal {
      display: none !important;
      height: 0 !important;
    }

    #okdev-diagnostics-body::-webkit-scrollbar-track {
      background: rgba(0, 0, 0, 0.25);
      border-left: 1px solid rgba(70, 55, 20, 0.55);
    }

    #okdev-diagnostics-body::-webkit-scrollbar-thumb {
      background: linear-gradient(to bottom, rgba(200, 155, 60, 0.22), rgba(70, 55, 20, 0.85));
      border: 1px solid rgba(70, 55, 20, 0.95);
      border-radius: 10px;
      min-height: 28px;
    }

    #okdev-diagnostics-body::-webkit-scrollbar-thumb:hover {
      background: linear-gradient(to bottom, rgba(200, 155, 60, 0.32), rgba(70, 55, 20, 0.95));
    }

    #okdev-diagnostics-body::-webkit-scrollbar-corner {
      background: transparent;
    }
    
    #${PANEL_ID} {
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      z-index: 10000;
      pointer-events: none;
    }
    
    #${PANEL_ID} .flyout-container {
      pointer-events: all;
    }
    
    lol-uikit-flyout-frame#${FLYOUT_ID},
    #${FLYOUT_ID} {
      min-width: 0 !important;
      max-width: calc(100vw - 24px) !important;
      background: transparent !important;
      background-color: transparent !important;
      background-image: none !important;
      border-radius: 0 !important;
      padding: 0 !important;
      color: #cdbe91;
      font-family: "Segoe UI", sans-serif;
      display: flex !important;
      flex-direction: column !important;
      align-items: center !important;
      box-shadow: none !important;
      border: none !important;
      margin: 0 !important;
      overflow: visible !important;
      transform-origin: top center !important;
    }
    
    lol-uikit-flyout-frame#${FLYOUT_ID}::before,
    lol-uikit-flyout-frame#${FLYOUT_ID}::after,
    #${FLYOUT_ID}::before,
    #${FLYOUT_ID}::after {
      display: none !important;
      background: none !important;
      background-color: transparent !important;
      background-image: none !important;
      content: none !important;
    }
    
    lol-uikit-flyout-frame#${FLYOUT_ID} lc-flyout-content,
    lol-uikit-flyout-frame#${FLYOUT_ID} .lc-flyout-content,
    #${FLYOUT_ID} lc-flyout-content,
    #${FLYOUT_ID} .lc-flyout-content {
      background: #010a13 !important;
      background-color: #010a13 !important;
      background-image: none !important;
      border-radius: 0 !important;
      padding: 20px !important;
      width: 100% !important;
      box-sizing: border-box !important;
      border: none !important;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5) !important;
      margin: 0 !important;
      overflow-y: auto;
      overflow-x: hidden;
      overscroll-behavior: contain;
      scrollbar-width: thin;
      scrollbar-color: #695625 #010a13;
    }
    
    #${FLYOUT_ID} .settings-title {
      font-size: 18px;
      font-weight: bold !important;
      margin-bottom: 12px;
      color: #c8aa6e;
      text-align: center;
      width: 100%;
    }
    
    #${FLYOUT_ID} .settings-section {
      margin-bottom: 12px;
      width: 100%;
    }
    
    #${FLYOUT_ID} .settings-label {
      display: block;
      margin-bottom: 8px;
      font-size: 14px;
      color: #cdbe91;
    }
    
    #${FLYOUT_ID} .settings-value {
      display: inline-block;
      margin-left: 10px;
      font-size: 14px;
      color: #c8aa6e;
      min-width: 50px;
    }

    #${FLYOUT_ID} .okdev-tooltip-wrapper {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      position: relative;
      margin-right: 8px;
      top: 3px;
    }

    #${FLYOUT_ID} .okdev-tooltip-icon {
      width: 24px;
      height: 24px;
      background-image: url("http://127.0.0.1:${window.__okdevBridge ? window.__okdevBridge.port : 50000}/asset/tooltip.png");
      background-size: 14px;
      background-repeat: no-repeat;
      background-position: center;
      opacity: 0.85;
      cursor: help;
      border: none;
      padding: 0;
      margin: 0;
      outline: none;
      background-color: transparent;
    }

    #${FLYOUT_ID} .okdev-tooltip-icon:hover {
      opacity: 1;
    }

    #${FLYOUT_ID} .okdev-tooltip-icon:focus-visible {
      outline: 1px solid #c8aa6e;
      outline-offset: 2px;
      border-radius: 3px;
    }

    /* Tooltip bubble is rendered globally (outside flyout) */
    #okdev-global-tooltip {
      position: fixed;
      left: 0;
      top: 0;
      width: 340px;
      max-width: calc(100vw - 24px);
      box-sizing: border-box;
      padding: 10px 12px;
      background: #0b1a2a;
      border: 1px solid #5c5b56;
      color: #cdbe91;
      font-size: 12px;
      line-height: 1.35;
      white-space: pre-line;
      text-align: start;
      box-shadow: 0 10px 28px rgba(0, 0, 0, 0.65);
      opacity: 0;
      visibility: hidden;
      transform: translateY(2px);
      transition: opacity 0.12s ease, transform 0.12s ease;
      z-index: 100050;
      pointer-events: none;
      font-family: "Beaufort for LOL", serif;
    }

    #okdev-global-tooltip[data-show="true"] {
      opacity: 1;
      visibility: visible;
      transform: translateY(0px);
    }

    #okdev-global-tooltip::after {
      content: "";
      position: absolute;
      left: var(--okdev-tooltip-arrow-x, 50%);
      transform: translateX(-50%);
      width: 0;
      height: 0;
      border-left: 7px solid transparent;
      border-right: 7px solid transparent;
    }

    #okdev-global-tooltip::before {
      content: "";
      position: absolute;
      left: var(--okdev-tooltip-arrow-x, 50%);
      transform: translateX(-50%);
      width: 0;
      height: 0;
      border-left: 8px solid transparent;
      border-right: 8px solid transparent;
      z-index: -1;
    }

    /* Tooltip ABOVE the icon (arrow on bottom) */
    #okdev-global-tooltip[data-placement="top"]::after {
      top: 100%;
      border-top: 7px solid #0b1a2a;
    }

    #okdev-global-tooltip[data-placement="top"]::before {
      top: 100%;
      border-top: 8px solid #5c5b56;
      margin-top: 1px;
    }

    /* Tooltip BELOW the icon (arrow on top) */
    #okdev-global-tooltip[data-placement="bottom"]::after {
      top: -7px;
      border-bottom: 7px solid #0b1a2a;
    }

    #okdev-global-tooltip[data-placement="bottom"]::before {
      top: -8px;
      border-bottom: 8px solid #5c5b56;
      margin-top: -1px;
    }
    
    #${FLYOUT_ID} .settings-slider {
      width: 100%;
      height: 6px;
      background: #3c3c41;
      border-radius: 3px;
      outline: none;
      -webkit-appearance: none;
      margin: 6px 0;
    }
    
    #${FLYOUT_ID} .settings-slider::-webkit-slider-thumb {
      -webkit-appearance: none;
      appearance: none;
      width: 16px;
      height: 16px;
      background: #c8aa6e;
      border-radius: 50%;
      cursor: pointer;
    }
    
    #${FLYOUT_ID} .settings-slider::-moz-range-thumb {
      width: 16px;
      height: 16px;
      background: #c8aa6e;
      border-radius: 50%;
      cursor: pointer;
      border: none;
    }
    
    #${FLYOUT_ID} .settings-checkbox {
      width: 18px;
      height: 18px;
      margin-right: 8px;
      cursor: pointer;
    }
    
    #${FLYOUT_ID} .settings-input {
      width: 100%;
      padding: 8px;
      background: #3c3c41;
      border: 1px solid #5c5b56;
      border-radius: 4px;
      color: #cdbe91;
      font-size: 14px;
      font-family: "Beaufort for LOL", serif;
      box-sizing: border-box;
    }
    
    #${FLYOUT_ID} .settings-input::placeholder {
      font-family: "Beaufort for LOL", serif;
      color: #7d7d7d;
      opacity: 1;
    }
    
    #${FLYOUT_ID} .settings-input::-webkit-input-placeholder {
      font-family: "Beaufort for LOL", serif;
      color: #7d7d7d;
    }
    
    #${FLYOUT_ID} .settings-input::-moz-placeholder {
      font-family: "Beaufort for LOL", serif;
      color: #7d7d7d;
      opacity: 1;
    }
    
    #${FLYOUT_ID} .settings-input:-ms-input-placeholder {
      font-family: "Beaufort for LOL", serif;
      color: #7d7d7d;
    }
    
    #${FLYOUT_ID} .settings-input:focus {
      outline: none;
      border-color: #c8aa6e;
    }
    
    #${FLYOUT_ID} .settings-status {
      display: inline-block;
      margin-left: 8px;
      font-size: 16px;
    }
    
    #${FLYOUT_ID} .settings-button {
      width: 100%;
      padding: 10px;
      background: #0a1428;
      border: 1px solid #c8aa6e;
      border-radius: 4px;
      color: #c8aa6e;
      font-size: 14px;
      font-weight: bold;
      cursor: pointer;
      margin-top: 8px;
      transition: background 0.2s;
    }
    
    #${FLYOUT_ID} .settings-button:hover {
      background: #1a2332;
    }
    
    #${FLYOUT_ID} .settings-links {
      display: flex;
      justify-content: space-between;
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid #3c3c41;
      width: 100%;
    }
    
    #${FLYOUT_ID} form {
      width: 100%;
      display: flex;
      flex-direction: column;
      align-items: center;
    }
    
    #${FLYOUT_ID} .settings-link {
      color: #c8aa6e;
      text-decoration: none;
      font-size: 14px;
      transition: color 0.2s;
    }
    
    #${FLYOUT_ID} .settings-link:hover {
      color: #f0e6d2;
    }
    
    /* Box on the first line of its label, so boxes side by side stay aligned
       when a label wraps (other languages) */
    #${FLYOUT_ID} .settings-checkbox-wrapper {
      display: flex;
      align-items: flex-start;
      margin-top: 8px;
    }
    /* Long labels (other languages) wrap instead of being cut */
    #${FLYOUT_ID} .settings-checkbox-wrapper span {
      min-width: 0;
      padding-top: 1px;
      line-height: 1.2;
      overflow-wrap: anywhere;
    }
    #${FLYOUT_ID} .settings-checkbox-wrapper input {
      flex-shrink: 0;
      margin-top: 0;
    }

    /* Delete button in the manage-mods list rows */
    #${FLYOUT_ID} .mod-delete-button,
    .mod-delete-button {
      flex: 0 0 auto;
      background: transparent;
      border: 1px solid rgba(255, 107, 107, 0.5);
      border-radius: 3px;
      color: #ff6b6b;
      font-family: "Beaufort for LOL", serif;
      font-size: 12px;
      padding: 6px 14px;
      cursor: pointer;
      transition: background 0.2s, border-color 0.2s, color 0.2s;
    }
    .mod-delete-button:hover:not(:disabled) {
      background: rgba(255, 107, 107, 0.15);
      border-color: #ff6b6b;
      color: #ff8f8f;
    }
    .mod-delete-button:disabled {
      opacity: 0.5;
      cursor: default;
    }

    /* Save button in the rename-mod dialog */
    .mod-save-button {
      flex: 0 0 auto;
      background: transparent;
      border: 1px solid rgba(94, 184, 108, 0.5);
      border-radius: 3px;
      color: #5eb86c;
      font-family: "Beaufort for LOL", serif;
      font-size: 12px;
      padding: 6px 14px;
      cursor: pointer;
      transition: background 0.2s, border-color 0.2s, color 0.2s;
    }
    .mod-save-button:hover:not(:disabled) {
      background: rgba(94, 184, 108, 0.15);
      border-color: #5eb86c;
      color: #8fd89a;
    }

    /* Rename button in the manage-mods list rows */
    .mod-rename-button {
      flex: 0 0 auto;
      background: transparent;
      border: 1px solid rgba(200, 170, 110, 0.5);
      border-radius: 3px;
      color: #c8aa6e;
      font-family: "Beaufort for LOL", serif;
      font-size: 12px;
      padding: 6px 14px;
      cursor: pointer;
      transition: background 0.2s, border-color 0.2s, color 0.2s;
    }
    .mod-rename-button:hover:not(:disabled) {
      background: rgba(200, 170, 110, 0.15);
      border-color: #c8aa6e;
      color: #f0e6d2;
    }
    .mod-rename-button:disabled {
      opacity: 0.5;
      cursor: default;
    }
    #manage-custom-mods-dropdown > * {
      background: transparent !important;
      background-color: transparent !important;
    }
    #manage-custom-mods-dropdown:focus,
    #manage-custom-mods-dropdown:active,
    #manage-custom-mods-dropdown:focus-visible,
    #manage-custom-mods-dropdown:focus-within,
    #manage-custom-mods-dropdown:focus *,
    #manage-custom-mods-dropdown:active * {
      filter: none !important;
      -webkit-filter: none !important;
      transform: none !important;
      -webkit-transform: none !important;
      box-shadow: none !important;
      text-shadow: none !important;
      outline: none !important;
      border-color: transparent !important;
    }
    #manage-custom-mods-dropdown .framed-dropdown-type {
      text-align: left !important;
    }
    #manage-custom-mods-dropdown[class*="active"] .placeholder-option,
    #manage-custom-mods-dropdown.active .placeholder-option {
      display: none !important;
    }
    #manage-custom-mods-dropdown .placeholder-option {
      display: block !important;
    }
    #manage-custom-mods-dropdown lol-uikit-dropdown-option::after,
    #manage-custom-mods-dropdown lol-uikit-dropdown-option::before,
    #manage-custom-mods-dropdown .framed-dropdown-type::after,
    #manage-custom-mods-dropdown .framed-dropdown-type::before,
    #manage-custom-mods-dropdown lol-uikit-dropdown-option [class*="check"],
    #manage-custom-mods-dropdown lol-uikit-dropdown-option [class*="icon"],
    #manage-custom-mods-dropdown lol-uikit-dropdown-option [class*="selected"] {
      display: none !important;
      visibility: hidden !important;
      opacity: 0 !important;
    }
    #manage-custom-mods-dropdown .ui-dropdown {
      color: #CDBE91 !important;
      font-size: 12px !important;
      font-weight: normal !important;
      line-height: 16px !important;
      letter-spacing: 0.025em !important;
      -webkit-font-smoothing: subpixel-antialiased !important;
    }
    #manage-custom-mods-dropdown::part(content),
    #manage-custom-mods-dropdown .ui-dropdown-current-content,
    #manage-custom-mods-dropdown .ui-dropdown-current-content.shadow {
      color: #CDBE91 !important;
    }


    /* Add Custom Mods Dialog Styles */
    #add-custom-mods-dialog,
    #champion-selection-dialog,
    #skin-selection-dialog {
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      z-index: 10001;
      background: rgba(0, 0, 0, 0.5);
      display: flex;
      align-items: center;
      justify-content: center;
    }

    #add-custom-mods-dialog .backdrop,
    #champion-selection-dialog .backdrop,
    #skin-selection-dialog .backdrop {
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      z-index: 10001;
      background: rgba(0, 0, 0, 0.5);
      pointer-events: all;
    }

    
    #add-custom-mods-flyout,
    #champion-selection-flyout,
    #skin-selection-flyout {
      min-width: 0 !important;
      width: min(700px, calc(100vw - 24px)) !important;
      max-width: calc(100vw - 24px) !important;
      max-height: calc(100vh - 24px) !important;
      background: transparent !important;
      background-color: transparent !important;
      background-image: none !important;
      border-radius: 0 !important;
      padding: 0 !important;
      color: #cdbe91;
      font-family: "Beaufort for LOL", serif;
      display: flex !important;
      flex-direction: column !important;
      align-items: center !important;
      box-shadow: none !important;
      border: none !important;
      margin: 0 !important;
      overflow: visible !important;
      overflow-x: hidden !important;
      overflow-y: hidden !important;
    }

    #skin-selection-flyout {
      height: min(640px, calc(100vh - 24px)) !important;
    }

    #champion-selection-flyout::-webkit-scrollbar,
    #skin-selection-flyout::-webkit-scrollbar,
    #champion-selection-dialog::-webkit-scrollbar,
    #skin-selection-dialog::-webkit-scrollbar {
      display: none !important;
      width: 0 !important;
      height: 0 !important;
    }
    
    #champion-selection-flyout *::-webkit-scrollbar,
    #skin-selection-flyout *::-webkit-scrollbar {
      display: none !important;
      width: 0 !important;
      height: 0 !important;
    }
    
    #add-custom-mods-flyout lc-flyout-content,
    #add-custom-mods-flyout .lc-flyout-content,
    #champion-selection-flyout lc-flyout-content,
    #champion-selection-flyout .lc-flyout-content,
    #skin-selection-flyout lc-flyout-content,
    #skin-selection-flyout .lc-flyout-content {
      overflow-x: hidden !important;
    }
    
    #add-custom-mods-flyout lc-flyout-content,
    #add-custom-mods-flyout .lc-flyout-content,
    #champion-selection-flyout lc-flyout-content,
    #champion-selection-flyout .lc-flyout-content,
    #skin-selection-flyout lc-flyout-content,
    #skin-selection-flyout .lc-flyout-content {
      background: #010a13 !important;
      background-color: #010a13 !important;
      background-image: none !important;
      border-radius: 0 !important;
      padding: 20px !important;
      width: 100% !important;
      max-height: calc(100vh - 24px) !important;
      box-sizing: border-box !important;
      border: 1px solid #c8aa6e !important;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5) !important;
      margin: 0 !important;
      overflow-x: hidden !important;
      overflow-y: auto;
    }
    
    #champion-selection-dialog,
    #skin-selection-dialog {
      overflow-x: hidden !important;
      overflow-y: hidden !important;
    }
    
    #champion-selection-flyout::-webkit-scrollbar,
    #skin-selection-flyout::-webkit-scrollbar,
    #champion-selection-flyout::-webkit-scrollbar:horizontal,
    #skin-selection-flyout::-webkit-scrollbar:horizontal,
    #champion-selection-dialog::-webkit-scrollbar,
    #skin-selection-dialog::-webkit-scrollbar {
      display: none !important;
      width: 0 !important;
      height: 0 !important;
    }
    
    #add-custom-mods-flyout::before,
    #add-custom-mods-flyout::after {
      display: none !important;
      content: none !important;
    }

    #add-custom-mods-flyout *::before,
    #add-custom-mods-flyout *::after {
      display: none !important;
      content: none !important;
      background: none !important;
      background-image: none !important;
    }
    
    #add-custom-mods-flyout .settings-title,
    #champion-selection-flyout .settings-title,
    #skin-selection-flyout .settings-title {
      font-size: 18px;
      font-weight: bold !important;
      margin-bottom: 12px;
      color: #c8aa6e;
      text-align: center;
      width: 100%;
      position: relative;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    
    .dialog-header {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 100%;
      margin-bottom: 16px;
      position: relative;
      min-height: 32px;
      flex: 0 0 auto;
      box-sizing: border-box;
      padding-inline: 36px;
    }

    .back-button {
      position: absolute;
      left: 0;
      background: transparent;
      border: none;
      color: #a09b8c;
      width: 32px;
      height: 32px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 0;
      transition: color 0.2s ease;
      flex-shrink: 0;
    }
    .back-button svg {
      width: 20px;
      height: 20px;
      fill: none;
      stroke: currentColor;
      stroke-width: 2;
      stroke-linecap: round;
      stroke-linejoin: round;
    }
    .back-button:hover {
      color: #c8aa6e;
    }
    .back-button:active {
      color: #f0e6d2;
    }
    
    .dialog-title-wrapper {
      flex: 1;
      min-width: 0;
      overflow-wrap: anywhere;
      text-align: center;
      font-size: 18px;
      font-weight: bold;
      color: #c8aa6e;
      font-family: "Beaufort for LOL", serif;
    }
    
    #champion-selection-flyout .champion-search-input,
    #champion-selection-flyout lol-uikit-flat-input.champion-search-input {
      width: 100%;
      margin-bottom: 12px;
    }
    
    #champion-selection-flyout .champion-search-input input,
    #champion-selection-flyout lol-uikit-flat-input.champion-search-input input {
      width: 100%;
      box-sizing: border-box;
    }
    
    #champions-grid-wrapper,
    #skins-list {
      scrollbar-width: none;
    }
    #champions-grid-wrapper::-webkit-scrollbar,
    #skins-list::-webkit-scrollbar {
      display: none;
      width: 0;
      height: 0;
    }

    #champions-grid-wrapper {
      max-height: 45vh;
      margin-top: 12px;
    }
    
    #champions-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(90px, 1fr));
      gap: 8px;
      padding-right: 8px;
    }

    .champion-card {
      display: flex;
      flex-direction: column;
      align-items: center;
      cursor: pointer;
      padding: 6px;
      border: 1px solid transparent;
      border-radius: 4px;
      transition: border-color 0.2s, background 0.2s;
      background: transparent;
    }
    .champion-card:hover {
      border-color: #c8aa6e;
      background: rgba(200, 170, 110, 0.08);
    }
    .champion-card img {
      width: 60px;
      height: 60px;
      border-radius: 50%;
      border: 2px solid #5b5a56;
      object-fit: cover;
      transition: border-color 0.2s;
    }
    .champion-card:hover img {
      border-color: #c8aa6e;
    }
    .champion-card .champion-name {
      margin-top: 6px;
      font-size: 11px;
      color: #a09b8c;
      text-align: center;
      font-family: "Beaufort for LOL", serif;
      line-height: 1.2;
      max-width: 80px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .champion-card:hover .champion-name {
      color: #cdbe91;
    }

    #skins-list {
      flex: 1 1 auto;
      min-height: 120px !important;
      max-height: none;
    }

    #skins-list .skins-list-container {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(min(150px, 100%), 1fr));
      gap: 10px;
      padding-right: 8px;
    }

    .skin-card {
      position: relative;
      height: 280px;
      cursor: pointer;
      border-radius: 4px;
      perspective: 1000px;
      background: transparent;
    }
    .skin-card-inner {
      position: relative;
      width: 100%;
      height: 100%;
      transition: transform 0.45s cubic-bezier(0.2, 0.75, 0.25, 1);
      transform-style: preserve-3d;
    }
    .skin-card.is-flipped .skin-card-inner {
      transform: rotateY(180deg);
    }
    .skin-card-face {
      position: absolute;
      inset: 0;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      border: 1px solid #5b5a56;
      border-radius: 4px;
      background: #1e2328;
      backface-visibility: hidden;
      -webkit-backface-visibility: hidden;
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    .skin-card-front {
      z-index: 2;
    }
    .skin-target {
      position: relative;
      display: flex;
      flex-direction: column;
      width: 100%;
      height: 100%;
      min-height: 0;
      padding: 0;
      border: 0;
      background: #101923;
      color: inherit;
      cursor: pointer;
    }
    .skin-target .skin-placeholder {
      position: absolute;
      width: 64px;
      height: 80px;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      fill: none;
      stroke: #c8aa6e;
      stroke-width: 2;
      opacity: .4;
      pointer-events: none;
    }
    .skin-target img, .skin-target .skin-name { position: relative; }
    .skin-target .skin-name { margin-top: auto; background: #1e2328; width: 100%; box-sizing: border-box; }
    .skin-card .skin-target:focus-visible {
      outline: 2px solid #f0e6d2;
      outline-offset: -3px;
    }
    .skin-card-back {
      z-index: 1;
      pointer-events: none;
    }
    .skin-card-face[inert] { visibility: hidden; }
    .skin-card.is-flipped .skin-card-front {
      z-index: 1;
      pointer-events: none;
    }
    .skin-card.is-flipped .skin-card-back {
      z-index: 2;
      pointer-events: auto;
    }
    .skin-card-front:hover,
    .skin-card-back:hover {
      border-color: #c8aa6e;
      box-shadow: 0 0 8px rgba(200, 170, 110, 0.3);
    }
    .skin-card.selected .skin-card-front,
    .skin-card.selected .skin-card-back {
      border-color: #c8aa6e;
      box-shadow: 0 0 10px rgba(200, 170, 110, 0.55);
      background: #2b2a20;
    }
    .skin-card-back {
      transform: rotateY(180deg);
      padding: 8px;
      box-sizing: border-box;
    }
    .skin-card-front img {
      width: 100%;
      flex: 1 1 auto;
      min-height: 0;
      object-fit: cover;
      display: block;
      background: #0a0a0d;
    }
    .skin-card .skin-name {
      padding: 8px;
      font-size: 12px;
      color: #a09b8c;
      text-align: center;
      font-family: "Beaufort for LOL", serif;
      line-height: 1.3;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .skin-card-front:hover .skin-name {
      color: #cdbe91;
    }
    .skin-chroma-button {
      position: absolute;
      top: 7px;
      right: 7px;
      z-index: 2;
      padding: 4px 7px;
      border: 1px solid rgba(200, 170, 110, 0.8);
      border-radius: 3px;
      background: #0a0a0d;
      color: #c8aa6e;
      cursor: pointer;
      font-family: "Beaufort for LOL", serif;
      font-size: 10px;
      font-weight: bold;
      transition: background 0.2s, color 0.2s, transform 0.2s;
    }
    .skin-chroma-button:hover {
      background: #463714;
      color: #f0e6d2;
      transform: translateY(-1px);
    }
    .skin-card-back-header {
      display: flex;
      align-items: center;
      gap: 5px;
      flex: 0 0 auto;
      min-height: 26px;
      color: #cdbe91;
      font-family: "Beaufort for LOL", serif;
      font-size: 11px;
      font-weight: bold;
    }
    .skin-card-back-header > span {
      min-width: 0;
      overflow-wrap: anywhere;
      background: #1e2328;
    }
    .skin-card.selected .skin-card-back-header > span { background: #2b2a20; }
    .skin-card-back-close {
      position: relative;
      z-index: 1;
      flex: 0 0 auto;
      min-width: 34px;
      padding: 3px 7px;
      border: 1px solid #5b5a56;
      border-radius: 2px;
      background: #121820;
      color: #a09b8c;
      cursor: pointer;
      font-size: 12px;
      line-height: 16px;
    }
    .skin-card-back-close:hover {
      border-color: #c8aa6e;
      color: #f0e6d2;
    }
    .skin-card-back-options {
      display: flex;
      flex: 1 1 auto;
      flex-direction: column;
      gap: 6px;
      min-height: 0;
      margin-top: 6px;
      overflow-y: auto;
      padding-right: 2px;
    }
    .skin-option {
      display: flex;
      align-items: center;
      gap: 7px;
      flex: 0 0 auto;
      min-height: 55px;
      padding: 4px;
      border: 1px solid #4a4a48;
      border-radius: 3px;
      background: #151b21;
      color: #a09b8c;
      cursor: pointer;
      text-align: left;
      transition: border-color 0.2s, background 0.2s;
    }
    .skin-option:hover {
      border-color: #c8aa6e;
      background: #252b2d;
    }
    .skin-option.selected {
      border-color: #c8aa6e;
      background: #463714;
      color: #f0e6d2;
    }
    .skin-option img {
      width: 38px;
      height: 52px;
      flex: 0 0 38px;
      object-fit: cover;
      background: #0a0a0d;
    }
    .skin-option-name {
      overflow: hidden;
      font-family: "Beaufort for LOL", serif;
      font-size: 10px;
      line-height: 1.2;
      text-overflow: ellipsis;
    }
    #skin-selection-actions {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 12px;
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid #463714;
      flex: 0 0 auto;
    }
    #skin-selection-count {
      flex: 1;
      color: #a09b8c;
      font-family: "Beaufort for LOL", serif;
      font-size: 13px;
    }
    #skin-selection-confirm {
      max-width: 100%;
      white-space: normal;
      padding: 9px 18px;
      border: 1px solid #c8aa6e;
      border-radius: 3px;
      background: #1e2328;
      color: #c8aa6e;
      cursor: pointer;
      font-family: "Beaufort for LOL", serif;
      font-weight: bold;
    }
    #skin-selection-confirm:hover:not(:disabled) {
      background: #463714;
      color: #f0e6d2;
    }
    #skin-selection-confirm:disabled {
      opacity: 0.45;
      cursor: default;
    }
    .okdev-client-button {
      box-sizing: border-box;
      min-height: 36px;
      padding: 8px 14px;
      border: 1px solid #695625;
      border-radius: 4px;
      background: #111d2a;
      color: #e0d1ad;
      font: 600 13px/1.3 "Segoe UI", sans-serif;
      cursor: pointer;
    }
    .okdev-client-button:hover:not(:disabled) { background: #253141; border-color: #c8aa6e; }
    .okdev-client-button:disabled { opacity: .55; cursor: wait; }
    .okdev-management-feedback { color: #ffb5ba; background: #010a13; font: 13px/1.5 "Segoe UI", sans-serif; overflow-wrap: anywhere; margin: 10px 0; }
    .okdev-management-feedback .okdev-client-button { margin-top: 8px; }
    .okdev-client-button:focus-visible,
    #${FLYOUT_ID} select:focus-visible,
    [data-okdev-dialog] button:focus-visible,
    [data-okdev-dialog] input:focus-visible {
      outline: 2px solid #e0bd76;
      outline-offset: 3px;
    }
    #${FLYOUT_ID} .okdev-settings-header {
      display: grid !important;
      grid-template-columns: minmax(0, 1fr) auto 32px;
      gap: 10px !important;
      align-items: center !important;
      width: 100%;
      padding-bottom: 16px;
      margin-bottom: 16px !important;
      border-bottom: 1px solid #3a3429;
      position: sticky !important;
      top: -20px;
      padding-top: 12px;
      background: #010a13;
      z-index: 3;
    }
    #${FLYOUT_ID} .okdev-settings-header .settings-title {
      text-align: start;
      white-space: nowrap;
      font: 700 22px/1.2 "Beaufort for LOL", "Segoe UI", sans-serif;
    }
    #${FLYOUT_ID} #okdev-version-badge {
      display: block;
      position: static !important;
      margin: 4px 0 0 !important;
      color: #b5b7bb !important;
      font: 12px/1.3 "Segoe UI", sans-serif !important;
    }
    #${FLYOUT_ID} .okdev-panel-close { min-height: 32px; width: 32px; padding: 0; font-size: 24px; }
    #${FLYOUT_ID} .okdev-language-select,
    #${FLYOUT_ID} .okdev-category-select {
      min-width: 0;
      min-height: 38px;
      padding: 8px 7px;
      border: 1px solid #695625;
      border-radius: 4px;
      background: #111d2a;
      color: #e0d1ad;
      font: 13px/1.3 "Segoe UI", sans-serif;
      color-scheme: dark;
    }
    #${FLYOUT_ID} .okdev-language-select { max-width: 135px; width: 100%; }
    #${FLYOUT_ID} .okdev-category-select { flex: 1; width: 50%; }
    #${FLYOUT_ID} .lol-settings-slider { width: 100% !important; direction: ltr; }
    #${FLYOUT_ID} .settings-value { direction: ltr; unicode-bidi: isolate; }
    #${FLYOUT_ID} .lol-settings-slider input[type="range"] { margin: 0; inset: 0; }
    #${FLYOUT_ID} .lol-settings-slider:focus-within { outline: 2px solid #e0bd76; outline-offset: 4px; border-radius: 4px; }
    #${FLYOUT_ID} .lol-uikit-slider-wrapper { pointer-events: none; }
    #${FLYOUT_ID} .lol-uikit-slider-button {
      background: #c8aa6e !important;
      border: 7px solid #010a13;
      box-sizing: border-box;
      border-radius: 50%;
    }
    #${FLYOUT_ID} .settings-checkbox { accent-color: #c8aa6e; flex-shrink: 0; }
    #${FLYOUT_ID} .settings-checkbox { color-scheme: dark; }
    #${FLYOUT_ID} .settings-status { display: inline-flex; flex-shrink: 0; color: #b8b6b1; }
    #${FLYOUT_ID} .settings-status[data-state="valid"] { color: #81e4cd; }
    #${FLYOUT_ID} .settings-status[data-state="invalid"] { color: #ffb5ba; }
    #${FLYOUT_ID} .okdev-tools-row { width:100%; display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:12px; }
    #${FLYOUT_ID} .okdev-tools-row button { margin:0 !important; min-width:0; }
    #${FLYOUT_ID} #pengu-ui-button { grid-column:1 / -1; }
    #${FLYOUT_ID} .settings-checkbox-wrapper { cursor: pointer; color: #ddd4bf; line-height: 1.4; }
    #${FLYOUT_ID} .settings-section { margin-bottom: 18px; }
    #${FLYOUT_ID} .settings-label { line-height: 1.45; margin-bottom: 4px; color: #ddd4bf; }
    #${FLYOUT_ID} .settings-input { background: #111d2a; color: #edf2fa; font: 13px/1.4 "Segoe UI", sans-serif; }
    #${FLYOUT_ID} #save-button { background: #c8aa6e; color: #151c26; width: 100%; margin-top: 16px !important; }
    #${FLYOUT_ID} .settings-links { gap: 10px; flex-wrap: wrap; }
    #${FLYOUT_ID} .settings-link { font-size: 12px; }
    #${FLYOUT_ID} .okdev-save-status { width: 100%; margin: 10px 0 0; color: #b7d9c9; font: 12px/1.5 "Segoe UI", sans-serif; overflow-wrap: anywhere; }
    #${FLYOUT_ID} .okdev-save-status[data-error="true"] { color: #ffb5ba; }
    #champion-selection-flyout, #skin-selection-flyout,
    #champion-mods-manage-dialog > .flyout, #category-mods-manage-dialog > .flyout,
    #rename-mod-dialog > .flyout, #delete-mod-confirm-dialog > .flyout {
      max-width: calc(100vw - 24px) !important;
      max-height: calc(100vh - 24px) !important;
    }
    #champion-selection-flyout .lc-flyout-content, #skin-selection-flyout .lc-flyout-content {
      width: 100% !important;
      max-width: 100%;
      min-height: 0;
    }
    #rename-mod-dialog > .flyout, #delete-mod-confirm-dialog > .flyout {
      overflow-y: auto;
      overflow-wrap: anywhere;
    }
    @media (prefers-reduced-motion: reduce) {
      #${FLYOUT_ID}, #okdev-global-tooltip, .okdev-warning-glow { animation: none !important; transition: none !important; }
    }
  `;
  }

  function log(level, message, data = null) {
    const consoleMethod =
      level === "error"
        ? console.error
        : level === "warn"
          ? console.warn
          : console.log;
    consoleMethod(`${LOG_PREFIX} ${message}`, data || "");
  }

  function handleSettingsData(payload) {
    currentSettings = {
      threshold: payload.threshold || 0.5,
      monitorAutoResumeTimeout: payload.monitorAutoResumeTimeout || 60,
      autostart: payload.autostart || false,
      hideEmptyCategories: payload.hideEmptyCategories || false,
      gamePath: payload.gamePath || "",
      gamePathValid: payload.gamePathValid || false,
      version: payload.version || "",
    };
    // Update version badge if the panel is already open
    const badge = document.getElementById("okdev-version-badge");
    if (badge && payload.version) {
      badge.textContent = `v${payload.version}`;
    }
    if (settingsPanel?.dataset.dirty !== "true") updateSettingsForm();
    // Badge count should reflect what's actually in diagnostics (and not change while dragging sliders).
    const localCount = Array.isArray(diagnosticsState.errors) ? diagnosticsState.errors.length : 0;
    if (localCount > 0) {
      updateErrorBadges(true, localCount);
    } else {
      updateErrorBadges(!!payload.hasErrors, payload.errorsCount || 0);
    }
    // If backend reports errors but we don't have the list yet, fetch it once so we can
    // show per-category guidance and clear it after Save (not while dragging).
    if (payload.hasErrors && (!Array.isArray(diagnosticsState.errors) || diagnosticsState.errors.length === 0)) {
      requestDiagnostics();
    }
    log("info", "Settings data received", currentSettings);
  }

  let diagnosticsDialog = null;
  let diagnosticsState = { errors: [], path: "", settingsSnapshot: null, baseSkinStats: null };
  let errorBadgeState = { hasErrors: false, count: 0 };
  let _badgeObserverStarted = false;
  let _pendingSave = null;
  let _saveTimeout = null;
  let _saveSequence = 0;
  let _diagnosticsPollId = null;
  let _flyoutRepositionTimer = null;

  function _clamp(n, min, max) {
    return Math.max(min, Math.min(max, n));
  }

  function _diagnosticsCategory(e) {
    if (e?.code === 'LOW_DISK_SPACE') return 'disk_space';
    const raw = String(e?.text || e?.msg || "").trim();
    const code = String(e?.code || "").trim();

    if (code === "BASE_SKIN_FORCE_SLOW" || code === "BASE_SKIN_VERIFY_FAILED") return "injection_threshold";
    if (code === "AUTO_RESUME_TRIGGERED" || code === "MONITOR_AUTO_RESUME_TIMEOUT") return "monitor_timeout";

    if (/Injection\s*Threshold/i.test(raw)) return "injection_threshold";
    if (/Auto-Resume Timeout/i.test(raw) || /Monitor Auto-Resume Timeout/i.test(raw)) return "monitor_timeout";

    return "other";
  }

  function _getRecommendedForCategory(category, errors) {
    const snap = diagnosticsState?.settingsSnapshot || null;
    const snapThreshold =
      typeof snap?.threshold === "number" && Number.isFinite(snap.threshold) ? snap.threshold : null;
    const snapTimeout =
      typeof snap?.monitorAutoResumeTimeout === "number" && Number.isFinite(snap.monitorAutoResumeTimeout)
        ? snap.monitorAutoResumeTimeout
        : null;

    if (category === "injection_threshold") {
      // Prefer explicit recommendation if present.
      const recs = (errors || [])
        .map((e) => e?.recommendedThresholdS)
        .filter((v) => typeof v === "number" && Number.isFinite(v));
      if (recs.length) return _clamp(Math.max(...recs), 0.3, 2.0);
      // Otherwise: stable heuristic based on the settings at the time diagnostics were fetched.
      if (typeof snapThreshold === "number") return _clamp(snapThreshold + 0.25, 0.3, 2.0);
      return null;
    }

    if (category === "monitor_timeout") {
      // Prefer explicit recommendation if present (support multiple field names defensively).
      const recs = (errors || [])
        .map((e) => e?.recommendedMonitorTimeoutS ?? e?.recommendedTimeoutS ?? e?.recommendedAutoResumeTimeoutS)
        .filter((v) => typeof v === "number" && Number.isFinite(v));
      if (recs.length) return _clamp(Math.max(...recs), 20, 180);
      if (typeof snapTimeout === "number") return _clamp(Math.max(snapTimeout + 30, 90), 20, 180);
      return null;
    }

    return null;
  }

  function getEffectiveDiagnosticsErrors() {
    const errors = Array.isArray(diagnosticsState.errors) ? diagnosticsState.errors : [];
    if (errors.length === 0) return [];

    // Group by category so we can drop the whole category once resolved.
    const byCat = new Map();
    for (const e of errors) {
      const cat = _diagnosticsCategory(e);
      if (!byCat.has(cat)) byCat.set(cat, []);
      byCat.get(cat).push(e);
    }

    const curThreshold = typeof currentSettings?.threshold === "number" ? currentSettings.threshold : null;
    const curTimeout =
      typeof currentSettings?.monitorAutoResumeTimeout === "number" ? currentSettings.monitorAutoResumeTimeout : null;

    const resolved = new Set();
    for (const [cat, list] of byCat.entries()) {
      const rec = _getRecommendedForCategory(cat, list);
      if (rec == null) continue;

      if (cat === "injection_threshold" && typeof curThreshold === "number" && curThreshold >= (rec - 1e-6)) {
        resolved.add(cat);
      } else if (cat === "monitor_timeout" && typeof curTimeout === "number" && curTimeout >= (rec - 1e-6)) {
        resolved.add(cat);
      }
    }

    if (resolved.size === 0) return errors;
    return errors.filter((e) => !resolved.has(_diagnosticsCategory(e)));
  }

  function getResolvedDiagnosticsCategories() {
    const all = Array.isArray(diagnosticsState?.errors) ? diagnosticsState.errors : [];
    if (all.length === 0) return [];
    const allCats = new Set(all.map(_diagnosticsCategory));
    const remainingCats = new Set(getEffectiveDiagnosticsErrors().map(_diagnosticsCategory));

    const resolved = [];
    for (const cat of allCats) {
      if (cat === "other") continue;
      if (!remainingCats.has(cat)) resolved.push(cat);
    }
    return resolved;
  }

  function handleDiagnosticsData(payload) {
    // Snapshot the settings at the time we fetched diagnostics so "recommended" targets stay stable
    // while the user is dragging sliders.
    const snapshot =
      currentSettings && typeof currentSettings === "object"
        ? {
            threshold: currentSettings.threshold,
            monitorAutoResumeTimeout: currentSettings.monitorAutoResumeTimeout,
          }
        : null;
    diagnosticsState = {
      errors: Array.isArray(payload.errors) ? payload.errors : [],
      path: payload.path || "",
      settingsSnapshot: snapshot,
      baseSkinStats: payload.baseSkinStats || null,
    };
    updateErrorBadges(diagnosticsState.errors.length > 0, diagnosticsState.errors.length);
    renderDiagnosticsDialog();
    renderThresholdBenchmark();
  }

  function getResolvedCategoriesForSavedValues(values) {
    // Only consider a category "fixed" if:
    // - the saved value meets/exceeds the recommended target, AND
    // - the user actually increased it compared to the snapshot from when diagnostics were fetched.
    const eps = 1e-6;
    const all = Array.isArray(diagnosticsState?.errors) ? diagnosticsState.errors : [];
    if (!all.length || !values) return [];

    const snap = diagnosticsState?.settingsSnapshot || null;
    const snapThreshold = typeof snap?.threshold === "number" ? snap.threshold : null;
    const snapTimeout = typeof snap?.monitorAutoResumeTimeout === "number" ? snap.monitorAutoResumeTimeout : null;

    const byCat = new Map();
    for (const e of all) {
      const cat = _diagnosticsCategory(e);
      if (!byCat.has(cat)) byCat.set(cat, []);
      byCat.get(cat).push(e);
    }

    const resolved = [];
    for (const [cat, list] of byCat.entries()) {
      if (cat === "other") continue;
      const rec = _getRecommendedForCategory(cat, list);
      if (rec == null) continue;

      if (cat === "injection_threshold") {
        const saved = typeof values.threshold === "number" ? values.threshold : null;
        const increased = typeof snapThreshold === "number" ? saved != null && saved > (snapThreshold + eps) : true;
        if (saved != null && saved >= (rec - eps) && increased) resolved.push(cat);
      } else if (cat === "monitor_timeout") {
        const saved = typeof values.monitorAutoResumeTimeout === "number" ? values.monitorAutoResumeTimeout : null;
        const increased = typeof snapTimeout === "number" ? saved != null && saved > (snapTimeout + eps) : true;
        if (saved != null && saved >= (rec - eps) && increased) resolved.push(cat);
      }
    }

    return resolved;
  }

  function updateErrorBadges(hasErrors, count) {
    errorBadgeState = { hasErrors: !!hasErrors, count: Number(count) || 0 };
    applyErrorBadges();
  }

  // Reconnect screen: let the player stop OKDEV's injection when a mod crashes the game
  let _reconnectObserverStarted = false;
  // The client detaches the reconnect screen while hidden, so querySelector can't reach it
  const _stopInjectionButtons = new Set();
  function addStopInjectionButton() {
    const container = document.querySelector(".reconnect-button-container");
    if (!container || container.querySelector(".okdev-stop-injection")) return;

    const button = document.createElement("lol-uikit-flat-button");
    button.className = "okdev-stop-injection";
    button.setAttribute("margin-right", "10px");
    resetStopInjectionButton(button);
    _stopInjectionButtons.add(button);
    button.addEventListener("click", () => {
      if (!bridge || button.hasAttribute("disabled")) return;
      bridge.send({ type: "stop-injection" });
      button.setAttribute("disabled", "true");
      labelStopInjectionButton(button);
    });
    container.appendChild(button);
  }

  function labelStopInjectionButton(button) {
    button.title = t("Stop OKDEV's injection, then reconnect without mods (use this if a mod crashes your game)");
    button.textContent = button.hasAttribute("disabled") ? t("Mods disabled") : t("Disable OKDEV mods");
  }

  function resetStopInjectionButton(button) {
    button.removeAttribute("disabled");
    labelStopInjectionButton(button);
  }

  // Menus on screen follow a language change
  window.addEventListener("okdev-i18n-changed", () => {
    _stopInjectionButtons.forEach(labelStopInjectionButton);
    const navItem = document.querySelector("lol-uikit-navigation-item.menu_item_Golden.OKDEV");
    if (settingsPanel && document.getElementById(PANEL_ID) && navItem) {
      createSettingsFlyout(navItem);
    }
    if (diagnosticsDialog) {
      // Closes the open one, then opens it again
      openDiagnosticsDialog();
      openDiagnosticsDialog();
    }
  });

  // The client reuses the reconnect screen, so re-enable the button for each new game
  function handleReconnectPhaseChange(payload) {
    // Keep it disabled only while the same game is running or reconnecting
    if (["InProgress", "Reconnect", "GameStart"].includes(payload?.phase)) return;
    _stopInjectionButtons.forEach(resetStopInjectionButton);
  }

  function startReconnectObserver() {
    if (_reconnectObserverStarted) return;
    _reconnectObserverStarted = true;
    addStopInjectionButton();
    new MutationObserver(addStopInjectionButton).observe(document.body, { childList: true, subtree: true });
  }

  function startBadgeObserver() {
    if (_badgeObserverStarted) return;
    _badgeObserverStarted = true;

    // Re-apply badges when the Golden OKDEV nav item is injected by OKDEV-UI (or recreated by Ember).
    const tryApply = () => {
      try {
        applyErrorBadges();
      } catch (e) {}
    };

    try {
      const obs = new MutationObserver(() => {
        // Only bother if we actually have errors to show (keeps it cheap)
        if (!errorBadgeState.hasErrors) return;
        tryApply();
      });
      obs.observe(document.body, { childList: true, subtree: true });

      // Also retry a few times after startup (covers cases where body observer misses early churn)
      let attempts = 0;
      const id = setInterval(() => {
        attempts += 1;
        tryApply();
        if (attempts >= 20) clearInterval(id); // ~10s max
      }, 500);
    } catch (e) {
      // Fallback: periodic best-effort if MutationObserver fails
      let attempts = 0;
      const id = setInterval(() => {
        attempts += 1;
        tryApply();
        if (attempts >= 20) clearInterval(id);
      }, 500);
    }
  }

  function applyErrorBadges() {
    // Sidebar "Golden OKDEV" nav icon badge
    const navItem = document.querySelector(
      "lol-uikit-navigation-item.menu_item_Golden.OKDEV"
    );
    if (navItem) {
      const host =
        navItem.querySelector(".menu-item-icon-wrapper") ||
        navItem.querySelector(".menu-item-icon") ||
        navItem;

      host.style.position = host.style.position || "relative";
      // Use warning image overlay (assets/red-warning.png) on the top-right of the OKDEV icon.
      let badge = host.querySelector("#okdev-errors-badge");
      if (errorBadgeState.hasErrors) {
        if (!badge) {
          badge = document.createElement("div");
          badge.id = "okdev-errors-badge";
          badge.classList.add("okdev-warning-glow");
          // Position + size for the warning overlay
          badge.style.position = "absolute";
          badge.style.top = "-10px";
          badge.style.right = "-10px";
          badge.style.width = "14px";
          badge.style.height = "14px";
          badge.style.backgroundImage = `url(http://127.0.0.1:${window.__okdevBridge ? window.__okdevBridge.port : 50000}/asset/red-warning.png)`;
          badge.style.backgroundSize = "contain";
          badge.style.backgroundRepeat = "no-repeat";
          badge.style.backgroundPosition = "center";
          badge.style.pointerEvents = "none";
          host.appendChild(badge);
        }
        // Keep text empty; this overlay is purely visual.
      } else if (badge) {
        badge.remove();
      }
    }

    // Troubleshooting button warning overlay (only when settings flyout is open)
    const tb = document.getElementById("troubleshoot-button");
    if (tb) {
      tb.style.position = tb.style.position || "relative";
      let warn = tb.querySelector("#okdev-troubleshoot-warning");
      if (errorBadgeState.hasErrors) {
        if (!warn) {
          warn = document.createElement("div");
          warn.id = "okdev-troubleshoot-warning";
          warn.classList.add("okdev-warning-glow");

          warn.style.position = "absolute";
          warn.style.top = "-15px";
          warn.style.right = "-9px";
          warn.style.width = "14px";
          warn.style.height = "14px";
          warn.style.backgroundImage = `url(http://127.0.0.1:${window.__okdevBridge ? window.__okdevBridge.port : 50000}/asset/red-warning.png)`;
          warn.style.backgroundSize = "contain";
          warn.style.backgroundRepeat = "no-repeat";
          warn.style.backgroundPosition = "center";
          warn.style.pointerEvents = "none";

          tb.appendChild(warn);
        }
      } else if (warn) {
        warn.remove();
      }
    }
  }

  function handlePathValidationResult(payload) {
    const pathInput = document.getElementById("game-path-input");
    const pathStatus = document.getElementById("path-status");

    if (!pathInput || !pathStatus) {
      return;
    }

    // Only update if this validation is for the current path value
    const currentPath = pathInput.value.trim();
    if (payload.gamePath === currentPath) {
      const isValid = payload.valid === true;
      showPathStatus(isValid ? 'valid' : 'invalid');

      // Update current settings if this is the saved path
      if (currentPath === currentSettings.gamePath) {
        currentSettings.gamePathValid = isValid;
      }
    }
  }

  function handleSettingsSaved(payload) {
    if (!_pendingSave || (payload.requestId && payload.requestId !== _pendingSave.requestId)) return;
    clearTimeout(_saveTimeout);
    _saveTimeout = null;
    const savedValues = _pendingSave;
    _pendingSave = null;
    const saveButton = document.getElementById("save-button");
    if (saveButton) { saveButton.disabled = false; saveButton.textContent = t("Save"); }
    if (!payload.success) {
      showSettingsFeedback(payload.error ? tAny(payload.error) : t("Error saving settings"), true);
      return;
    }
    if (settingsPanel === savedValues.panel && (settingsPanel._revision || 0) === savedValues.revision) {
      delete settingsPanel.dataset.dirty;
    }
    showSettingsFeedback(t("Saved!"));
    if (savedValues) {
      const categories = getResolvedCategoriesForSavedValues(savedValues);
      if (categories.length && bridge) bridge.send({type:"diagnostics-clear-category", categories});
    }
    requestSettings();
    requestDiagnostics();
  }

  // Language of OKDEV's menus: a code badge in the corner of Settings, applied as soon as it is picked
  function createLanguagePicker() {
    const i18n = window.OKDEVI18n;
    const picker = document.createElement("select");
    picker.className = "okdev-language-select";
    picker.setAttribute("aria-label", t("Language:"));
    for (const [value, name] of [["auto", t("Auto (client language)")], ...Object.entries(i18n.languages || {})]) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = name;
      picker.appendChild(option);
    }
    picker.value = i18n.setting || "auto";
    picker.addEventListener("change", () => {
      if (bridge) bridge.send({type: "language-save", language: picker.value});
    });
    return picker;
  }

  function createSettingsFlyout(navItem) {
    // Remove existing panel if any
    const existingPanel = document.getElementById(PANEL_ID);
    const draft = existingPanel?.dataset.dirty === 'true' ? {
      revision: existingPanel._revision || 0,
      values: [...existingPanel.querySelectorAll('input[id]')].map(input => ({id:input.id, value:input.value, checked:input.checked})),
    } : null;
    if (existingPanel) {
      existingPanel.dispose?.();
      existingPanel.remove();
    }

    // Create panel container (fixed positioning for viewport-relative coordinates)
    const panel = document.createElement("div");
    panel.id = PANEL_ID;
    const cleanups = [];
    const timers = new Set();
    let disposed = false;
    const schedule = (callback, delay) => {
      const timer = setTimeout(() => {
        timers.delete(timer);
        if (!disposed && panel.isConnected) callback();
      }, delay);
      timers.add(timer);
      return timer;
    };
    panel.dispose = () => {
      if (disposed) return;
      disposed = true;
      timers.forEach(clearTimeout);
      cleanups.forEach(cleanup => cleanup());
      clearTimeout(pathValidationTimeout);
      pathValidationTimeout = null;
      hideGlobalTooltip();
    };
    panel.opener = navItem;
    const markDirty = () => { panel.dataset.dirty = "true"; panel._revision = (panel._revision || 0) + 1; };
    panel.addEventListener("input", markDirty);
    panel.addEventListener("change", e => {
      if (e.target.matches('input')) markDirty();
    });
    panel.style.position = "fixed";
    panel.style.top = "0";
    panel.style.left = "0";
    panel.style.width = "100%";
    panel.style.height = "100%";
    panel.style.zIndex = "10000";
    panel.style.pointerEvents = "none";
    document.body.appendChild(panel);

    // Create backdrop for click-outside-to-close
    const backdrop = document.createElement("div");
    backdrop.style.position = "fixed";
    backdrop.style.top = "0";
    backdrop.style.left = "0";
    backdrop.style.width = "100%";
    backdrop.style.height = "100%";
    backdrop.style.zIndex = "9999";
    backdrop.style.background = "transparent";
    backdrop.style.pointerEvents = "all";
    backdrop.addEventListener("click", (e) => {
      // Only close if clicking directly on backdrop, not on flyout
      if (e.target === backdrop) {
        closeSettingsPanel();
      }
    });
    panel.appendChild(backdrop);

    // Get the actual icon element position (not the parent container)
    const iconElement =
      navItem.querySelector(".menu-item-icon") ||
      navItem.querySelector(".menu-item-icon-wrapper") ||
      navItem;
    const iconRect = iconElement.getBoundingClientRect();

    // Create flyout frame
    let flyoutFrame;
    try {
      flyoutFrame = document.createElement("lol-uikit-flyout-frame");
      flyoutFrame.id = FLYOUT_ID;
      flyoutFrame.className = "flyout";
      flyoutFrame.setAttribute("orientation", "bottom");
      flyoutFrame.setAttribute("animated", "true");
      flyoutFrame.setAttribute("show", "true");
    } catch (e) {
      log("debug", "Could not create custom element, using div", e);
      flyoutFrame = document.createElement("div");
      flyoutFrame.id = FLYOUT_ID;
      flyoutFrame.className = "flyout";
    }

    // Use absolute positioning within the fixed panel container
    flyoutFrame.style.position = "absolute";
    flyoutFrame.style.overflow = "visible";
    // Position below the icon, centered horizontally on the icon
    flyoutFrame.style.top = `${iconRect.bottom + 45}px`;
    flyoutFrame.style.left = `${iconRect.left + iconRect.width / 2}px`;
    flyoutFrame.style.transform = "translateX(-50%)"; // Center the panel on the icon
    flyoutFrame.style.zIndex = "10001";
    flyoutFrame.style.pointerEvents = "all";
    flyoutFrame.style.setProperty("background", "transparent", "important");
    flyoutFrame.style.setProperty(
      "background-color",
      "transparent",
      "important"
    );
    flyoutFrame.style.setProperty("background-image", "none", "important");
    flyoutFrame.style.setProperty("border", "none", "important");
    flyoutFrame.style.setProperty("box-shadow", "none", "important");
    flyoutFrame.style.setProperty("margin", "0", "important");
    flyoutFrame.style.setProperty("padding", "0", "important");
    flyoutFrame.style.setProperty("overflow", "visible", "important");

    // Force remove any default classes that might add background
    if (flyoutFrame.classList) {
      flyoutFrame.classList.forEach((cls) => {
        if (cls.includes("background") || cls.includes("bg-")) {
          flyoutFrame.classList.remove(cls);
        }
      });
    }

    // Prevent click from closing
    flyoutFrame.addEventListener("click", (e) => {
      e.stopPropagation();
    });

    // Create flyout content
    let flyoutContent;
    try {
      flyoutContent = document.createElement("lc-flyout-content");
    } catch (e) {
      log("debug", "Could not create lc-flyout-content, using div", e);
      flyoutContent = document.createElement("div");
      flyoutContent.className = "lc-flyout-content";
    }

    // Create settings form
    const form = document.createElement("div");
    form.style.width = "100%";
    form.style.display = "flex";
    form.style.flexDirection = "column";
    form.style.alignItems = "center";

    function getOrCreateGlobalTooltip() {
      let el = document.getElementById("okdev-global-tooltip");
      if (el) return el;

      el = document.createElement("div");
      el.id = "okdev-global-tooltip";
      el.setAttribute("role", "tooltip");
      el.setAttribute("data-show", "false");
      document.body.appendChild(el);
      return el;
    }

    function hideGlobalTooltip() {
      const el = document.getElementById("okdev-global-tooltip");
      if (!el) return;
      el.setAttribute("data-show", "false");
    }

    function showGlobalTooltipFor(anchorEl, text) {
      const tooltip = getOrCreateGlobalTooltip();
      tooltip._anchor = anchorEl;
      tooltip.textContent = text;
      tooltip.setAttribute("data-show", "true");

      // Measure after setting text
      const margin = 10;
      const rect = anchorEl.getBoundingClientRect();
      const tRect = tooltip.getBoundingClientRect();

      // Prefer above, fallback below if not enough room
      const preferredTop = rect.top - tRect.height - margin;
      const belowTop = rect.bottom + margin;
      const useTop = preferredTop >= 8;
      const top = useTop ? preferredTop : belowTop;
      tooltip.setAttribute("data-placement", useTop ? "top" : "bottom");

      // Center horizontally on icon, clamp to viewport
      let left = rect.left + rect.width / 2 - tRect.width / 2;
      const maxLeft = window.innerWidth - tRect.width - 8;
      left = Math.max(8, Math.min(maxLeft, left));

      tooltip.style.left = `${Math.round(left)}px`;
      tooltip.style.top = `${Math.round(top)}px`;

      // Nudge the arrow towards the anchor if clamped
      const anchorCenterX = rect.left + rect.width / 2;
      const arrowX = Math.max(12, Math.min(tRect.width - 12, anchorCenterX - left));
      tooltip.style.setProperty("--okdev-tooltip-arrow-x", `${Math.round(arrowX)}px`);
    }

    function createTooltipButton(tooltipText, ariaLabel) {
      const wrapper = document.createElement("span");
      wrapper.className = "okdev-tooltip-wrapper";

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "okdev-tooltip-icon";
      btn.setAttribute("aria-label", ariaLabel || t("Info"));

      // prevent accidental focus/drag interactions with nearby controls
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
      });

      const show = () => showGlobalTooltipFor(btn, tooltipText);
      const hide = () => hideGlobalTooltip();

      btn.addEventListener("mouseenter", show);
      btn.addEventListener("mouseleave", hide);
      btn.addEventListener("focus", show);
      btn.addEventListener("blur", hide);

      // Keep tooltip in correct position while resizing/scrolling
      const reposition = () => {
        const tt = document.getElementById("okdev-global-tooltip");
        if (!tt || tt.getAttribute("data-show") !== "true" || tt._anchor !== btn) return;
        showGlobalTooltipFor(btn, tooltipText);
      };
      window.addEventListener("resize", reposition);
      window.addEventListener("scroll", reposition, true);
      cleanups.push(() => {
        window.removeEventListener("resize", reposition);
        window.removeEventListener("scroll", reposition, true);
      });

      wrapper.appendChild(btn);
      return wrapper;
    }

    // Title + version badge inline
    const titleRow = document.createElement("div");
    titleRow.className = "okdev-settings-header";
    titleRow.style.cssText = "display:flex;align-items:baseline;justify-content:center;gap:8px;margin-bottom:4px";

    const title = document.createElement("div");
    title.className = "settings-title";
    title.textContent = t("Settings");
    title.style.marginBottom = "0";
    titleRow.appendChild(title);

    const versionBadge = document.createElement("span");
    versionBadge.id = "okdev-version-badge";
    versionBadge.style.cssText = [
      "font-size: 11px",
      "color: #a09b8c",
      "font-family: Beaufort for LOL, serif",
      "letter-spacing: 0.06em",
    ].join(";");
    versionBadge.textContent = currentSettings.version ? `v${currentSettings.version}` : "";
    titleRow.appendChild(versionBadge);

    if (window.OKDEVI18n) {
      // The title alone is centered on the panel: the version hangs to its right
      // and the language picker sits in the corner
      titleRow.style.position = "relative";
      titleRow.style.alignSelf = "stretch";
      title.style.width = "auto";
      title.style.position = "relative";
      versionBadge.style.position = "absolute";
      versionBadge.style.left = "100%";
      versionBadge.style.bottom = "3px";
      versionBadge.style.marginLeft = "8px";
      versionBadge.style.fontWeight = "normal";
      versionBadge.style.whiteSpace = "nowrap";
      title.appendChild(versionBadge);
      titleRow.appendChild(createLanguagePicker());
    }

    form.appendChild(titleRow);

    // Injection threshold section
    const thresholdSection = document.createElement("div");
    thresholdSection.className = "settings-section";

    const thresholdLabel = document.createElement("label");
    thresholdLabel.className = "settings-label";
    const thresholdLabelText = document.createElement("span");
    thresholdLabelText.textContent = t("Injection Threshold (seconds):");
    thresholdLabel.appendChild(
      createTooltipButton(
        t("Injection threshold is the time window during which the app considers your last hovered skin as the one to inject.\n\nFor example, if your injection threshold is set to 1 second, whichever skin you were hovering 1 second before champ select ends will be the one injected.\n\nIf your PC or connection is on the slower side, you may need to fine-tune this value."),
        t("Injection threshold info")
      )
    );
    thresholdLabel.appendChild(thresholdLabelText);
    thresholdSection.appendChild(thresholdLabel);

    const thresholdValue = document.createElement("span");
    thresholdValue.className = "settings-value";
    thresholdValue.id = "threshold-value";
    thresholdValue.textContent = "0.50 s";
    thresholdLabel.appendChild(thresholdValue);

    // Create slider container with League of Legends style
    const thresholdSliderContainer = document.createElement("div");
    thresholdSliderContainer.className = "lol-settings-slider-component";
    thresholdSliderContainer.style.display = "flex";
    thresholdSliderContainer.style.alignItems = "center";
    thresholdSliderContainer.style.width = "100%";
    thresholdSliderContainer.style.marginTop = "10px";

    const thresholdSliderWrapper = document.createElement("div");
    thresholdSliderWrapper.className = "lol-settings-slider";
    thresholdSliderWrapper.style.width = "100%";
    thresholdSliderWrapper.style.height = "30px";
    thresholdSliderWrapper.style.position = "relative";

    const thresholdSlider = document.createElement("input");
    thresholdSlider.type = "range";
    thresholdSlider.dir = "ltr";
    thresholdSlider.id = "threshold-slider";
    thresholdSlider.setAttribute("aria-label", t("Injection Threshold (seconds):"));
    // Minimum Injection Threshold: 300ms (0.30s)
    thresholdSlider.min = "30";
    thresholdSlider.max = "200";
    thresholdSlider.value = "50";
    thresholdSlider.style.width = "100%";
    thresholdSlider.style.height = "100%";
    thresholdSlider.style.opacity = "0";
    thresholdSlider.style.cursor = "pointer";
    thresholdSlider.style.position = "absolute";
    thresholdSlider.style.zIndex = "2";

    const thresholdSliderUI = document.createElement("div");
    thresholdSliderUI.className = "lol-uikit-slider-wrapper horizontal";
    thresholdSliderUI.style.position = "relative";
    thresholdSliderUI.style.height = "30px";
    thresholdSliderUI.style.width = "100%";

    const thresholdSliderBase = document.createElement("div");
    thresholdSliderBase.className = "lol-uikit-slider-base";
    thresholdSliderBase.style.height = "30px";
    thresholdSliderBase.style.width = "100%";
    thresholdSliderBase.style.position = "absolute";

    const thresholdTrack = document.createElement("div");
    thresholdTrack.className = "lol-uikit-slider-base-track";
    thresholdTrack.style.position = "absolute";
    thresholdTrack.style.top = "14px";
    thresholdTrack.style.left = "0";
    thresholdTrack.style.width = "calc(100% - 2.5px)";
    thresholdTrack.style.height = "2px";
    thresholdTrack.style.background = "#1e2328";

    const thresholdMin = 30;
    const thresholdMax = 200;

    const thresholdFill = document.createElement("div");
    thresholdFill.className = "lol-uikit-slider-fill";
    thresholdFill.style.width = "0px";
    thresholdFill.style.height = "2px";
    thresholdFill.style.background = "linear-gradient(to left, #695625, #463714)";
    thresholdFill.style.position = "absolute";
    thresholdFill.style.top = "13px";
    thresholdFill.style.border = "thin solid #010a13";
    thresholdFill.style.transition = "width 0.1s ease-out, background 0.2s ease";

    const thresholdButton = document.createElement("div");
    thresholdButton.className = "lol-uikit-slider-button";
    thresholdButton.style.left = "0px";
    thresholdButton.style.width = "30px";
    thresholdButton.style.height = "30px";
    thresholdButton.style.position = "absolute";
    thresholdButton.style.top = "0px";
    thresholdButton.style.cursor = "pointer";
    thresholdButton.style.transition = "left 0.1s ease-out, background-position 0.2s ease";

    thresholdSliderBase.appendChild(thresholdTrack);
    thresholdSliderBase.appendChild(thresholdFill);
    thresholdSliderBase.appendChild(thresholdButton);
    thresholdSliderUI.appendChild(thresholdSliderBase);
    thresholdSliderWrapper.appendChild(thresholdSlider);
    thresholdSliderWrapper.appendChild(thresholdSliderUI);
    thresholdSliderContainer.appendChild(thresholdSliderWrapper);
    thresholdSection.appendChild(thresholdSliderContainer);

    // Benchmark info placeholder (populated when diagnostics data arrives)
    const benchmarkInfo = document.createElement("div");
    benchmarkInfo.id = "okdev-threshold-benchmark";
    benchmarkInfo.style.marginTop = "6px";
    benchmarkInfo.style.fontSize = "11px";
    benchmarkInfo.style.fontFamily = "'Beaufort for LOL', serif";
    benchmarkInfo.style.color = "#b8b1a3";
    thresholdSection.appendChild(benchmarkInfo);

    form.appendChild(thresholdSection);

    // Monitor auto-resume timeout section
    const timeoutSection = document.createElement("div");
    timeoutSection.className = "settings-section";

    const timeoutLabel = document.createElement("label");
    timeoutLabel.className = "settings-label";
    const timeoutLabelText = document.createElement("span");
    timeoutLabelText.textContent = t("Monitor Auto-Resume Timeout (seconds):");
    timeoutLabel.appendChild(
      createTooltipButton(
        t("Auto-resume is a safety feature.\n\nIf the injection process takes longer than the value you set, the app will automatically cancel the injection and let the game start normally.\n\nThis prevents the injection from looping and blocking the game from launching.\n\nIf you use a lot of custom mods, you may need to adjust this value."),
        t("Auto-resume info")
      )
    );
    timeoutLabel.appendChild(timeoutLabelText);
    timeoutSection.appendChild(timeoutLabel);

    const timeoutValue = document.createElement("span");
    timeoutValue.className = "settings-value";
    timeoutValue.id = "timeout-value";
    timeoutValue.textContent = "60 s";
    timeoutLabel.appendChild(timeoutValue);

    // Create slider container with League of Legends style
    const timeoutSliderContainer = document.createElement("div");
    timeoutSliderContainer.className = "lol-settings-slider-component";
    timeoutSliderContainer.style.display = "flex";
    timeoutSliderContainer.style.alignItems = "center";
    timeoutSliderContainer.style.width = "100%";
    timeoutSliderContainer.style.marginTop = "10px";

    const timeoutSliderWrapper = document.createElement("div");
    timeoutSliderWrapper.className = "lol-settings-slider";
    timeoutSliderWrapper.style.width = "100%";
    timeoutSliderWrapper.style.height = "30px";
    timeoutSliderWrapper.style.position = "relative";

    const timeoutSlider = document.createElement("input");
    timeoutSlider.type = "range";
    timeoutSlider.dir = "ltr";
    timeoutSlider.id = "timeout-slider";
    timeoutSlider.setAttribute("aria-label", t("Monitor Auto-Resume Timeout (seconds):"));
    // Minimum Auto-Resume Timeout: 20s
    timeoutSlider.min = "20";
    timeoutSlider.max = "180";
    timeoutSlider.value = "60";
    timeoutSlider.style.width = "100%";
    timeoutSlider.style.height = "100%";
    timeoutSlider.style.opacity = "0";
    timeoutSlider.style.cursor = "pointer";
    timeoutSlider.style.position = "absolute";
    timeoutSlider.style.zIndex = "2";

    const timeoutSliderUI = document.createElement("div");
    timeoutSliderUI.className = "lol-uikit-slider-wrapper horizontal";
    timeoutSliderUI.style.position = "relative";
    timeoutSliderUI.style.height = "30px";
    timeoutSliderUI.style.width = "100%";

    const timeoutSliderBase = document.createElement("div");
    timeoutSliderBase.className = "lol-uikit-slider-base";
    timeoutSliderBase.style.height = "30px";
    timeoutSliderBase.style.width = "100%";
    timeoutSliderBase.style.position = "absolute";

    const timeoutTrack = document.createElement("div");
    timeoutTrack.className = "lol-uikit-slider-base-track";
    timeoutTrack.style.position = "absolute";
    timeoutTrack.style.top = "14px";
    timeoutTrack.style.left = "0";
    timeoutTrack.style.width = "calc(100% - 2.5px)";
    timeoutTrack.style.height = "2px";
    timeoutTrack.style.background = "#1e2328";

    const timeoutFill = document.createElement("div");
    timeoutFill.className = "lol-uikit-slider-fill";
    timeoutFill.style.width = "0px"; // Initial position for min value
    timeoutFill.style.height = "2px";
    timeoutFill.style.background = "linear-gradient(to left, #695625, #463714)";
    timeoutFill.style.position = "absolute";
    timeoutFill.style.top = "13px";
    timeoutFill.style.border = "thin solid #010a13";
    timeoutFill.style.transition = "width 0.1s ease-out, background 0.2s ease";

    const timeoutButton = document.createElement("div");
    timeoutButton.className = "lol-uikit-slider-button";
    timeoutButton.style.left = "0px"; // Initial position
    timeoutButton.style.width = "30px";
    timeoutButton.style.height = "30px";
    timeoutButton.style.position = "absolute";
    timeoutButton.style.top = "0px";
    timeoutButton.style.cursor = "pointer";
    timeoutButton.style.transition = "left 0.1s ease-out, background-position 0.2s ease";

    timeoutSliderBase.appendChild(timeoutTrack);
    timeoutSliderBase.appendChild(timeoutFill);
    timeoutSliderBase.appendChild(timeoutButton);
    timeoutSliderUI.appendChild(timeoutSliderBase);
    timeoutSliderWrapper.appendChild(timeoutSlider);
    timeoutSliderWrapper.appendChild(timeoutSliderUI);
    timeoutSliderContainer.appendChild(timeoutSliderWrapper);
    timeoutSection.appendChild(timeoutSliderContainer);
    form.appendChild(timeoutSection);

    // Auto-start and hide-empty-categories checkboxes share one row
    const checkboxRow = document.createElement("div");
    checkboxRow.className = "settings-section";
    checkboxRow.style.display = "flex";
    checkboxRow.style.gap = "12px";

    const autostartSection = document.createElement("div");
    autostartSection.style.flex = "1";
    autostartSection.style.minWidth = "0";

    const autostartWrapper = document.createElement("label");
    autostartWrapper.className = "settings-checkbox-wrapper";

    const autostartCheckbox = document.createElement("input");
    autostartCheckbox.type = "checkbox";
    autostartCheckbox.className = "settings-checkbox";
    autostartCheckbox.id = "autostart-checkbox";
    autostartWrapper.appendChild(autostartCheckbox);

    const autostartText = document.createElement("span");
    autostartText.textContent = t("Start with Windows");
    autostartWrapper.appendChild(autostartText);
    autostartSection.appendChild(autostartWrapper);
    checkboxRow.appendChild(autostartSection);

    const customWheelSection = document.createElement("div");
    customWheelSection.style.flex = "1";
    customWheelSection.style.minWidth = "0";

    const hideEmptyCategoriesWrapper = document.createElement("label");
    hideEmptyCategoriesWrapper.className = "settings-checkbox-wrapper";

    const hideEmptyCategoriesCheckbox = document.createElement("input");
    hideEmptyCategoriesCheckbox.type = "checkbox";
    hideEmptyCategoriesCheckbox.className = "settings-checkbox";
    hideEmptyCategoriesCheckbox.id = "hide-empty-categories-checkbox";
    hideEmptyCategoriesWrapper.appendChild(hideEmptyCategoriesCheckbox);

    const hideEmptyCategoriesText = document.createElement("span");
    hideEmptyCategoriesText.textContent = t("Hide empty categories");
    hideEmptyCategoriesWrapper.title = t("Hide empty categories in the custom mods wheel");
    hideEmptyCategoriesWrapper.appendChild(hideEmptyCategoriesText);
    customWheelSection.appendChild(hideEmptyCategoriesWrapper);
    checkboxRow.appendChild(customWheelSection);
    form.appendChild(checkboxRow);

    // Game path section
    const pathSection = document.createElement("div");
    pathSection.className = "settings-section";

    const pathLabel = document.createElement("label");
    pathLabel.className = "settings-label";
    pathLabel.htmlFor = "game-path-input";
    pathLabel.textContent = t("League of Legends Game Path:");
    pathSection.appendChild(pathLabel);

    const pathInputWrapper = document.createElement("div");
    pathInputWrapper.style.display = "flex";
    pathInputWrapper.style.alignItems = "center";

    const pathInput = document.createElement("input");
    pathInput.type = "text";
    pathInput.dir = "ltr";
    pathInput.className = "settings-input";
    pathInput.id = "game-path-input";
    pathInput.placeholder = "C:\\Riot Games\\League of Legends\\Game";
    pathInput.addEventListener("input", () => {
      updatePathStatus();
    });
    pathInputWrapper.appendChild(pathInput);

    const pathStatus = document.createElement("span");
    pathStatus.className = "settings-status";
    pathStatus.id = "path-status";
    pathStatus.setAttribute('role', 'status');
    pathStatus.textContent = "";
    pathInputWrapper.appendChild(pathStatus);
    pathSection.appendChild(pathInputWrapper);
    form.appendChild(pathSection);

    // Add / Manage custom mods dropdowns share one row, half width each
    const customModsRow = document.createElement("div");
    customModsRow.style.display = "flex";
    customModsRow.style.gap = "8px";
    customModsRow.style.marginTop = "8px";
    customModsRow.style.width = "100%";

    // Add custom mods dropdown
    // Native selects keep keyboard behavior and avoid shadow-DOM polling.
    const categories = [
      { id: "skins", name: "Skins" }, { id: "maps", name: "Maps" },
      { id: "fonts", name: "Fonts" }, { id: "announcers", name: "Announcers" },
      { id: "ui", name: "UI" }, { id: "voiceover", name: "Voiceover" },
      { id: "loading_screen", name: "Loading Screen" }, { id: "vfx", name: "VFX" },
      { id: "sfx", name: "SFX" }, { id: "others", name: "Others" },
    ];
    for (const [id, title, action] of [
      ["add-custom-mods-dropdown", "Add custom mods", handleCategorySelection],
      ["manage-custom-mods-dropdown", "Manage custom mods", handleManageCategorySelection],
    ]) {
      const select = document.createElement("select");
      select.id = id;
      select.className = "okdev-category-select";
      select.setAttribute("aria-label", t(title));
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = t(title);
      select.appendChild(placeholder);
      for (const category of categories) {
        const option = document.createElement("option");
        option.value = category.id;
        option.textContent = t(category.name);
        select.appendChild(option);
      }
      select.addEventListener("change", () => {
        const category = select.value;
        select.value = "";
        if (category) action(category);
      });
      customModsRow.appendChild(select);
    }
    form.appendChild(customModsRow);

    // Open logs folder button
    const logsButton = createActionButton();
    logsButton.id = "logs-folder-button";
    logsButton.textContent = t("Open Logs Folder");
    logsButton.style.marginTop = "8px";
    logsButton.style.width = "100%";
    logsButton.addEventListener("click", () => {
      openLogsFolder();
    });
    const toolsRow = document.createElement('div');
    toolsRow.className = 'okdev-tools-row';
    toolsRow.appendChild(logsButton);

    // Troubleshooting button (opens a small dialog with compact errors)
    const troubleshootButton = createActionButton();
    troubleshootButton.id = "troubleshoot-button";
    troubleshootButton.textContent = t("Troubleshooting");
    troubleshootButton.style.marginTop = "8px";
    troubleshootButton.style.width = "100%";
    troubleshootButton.addEventListener("click", () => {
      openDiagnosticsDialog();
    });
    toolsRow.appendChild(troubleshootButton);


    // Open Pengu Loader UI button
    const penguUIButton = createActionButton();
    penguUIButton.id = "pengu-ui-button";
    penguUIButton.textContent = t("Open Pengu Loader UI");
    penguUIButton.style.marginTop = "8px";
    penguUIButton.style.width = "100%";
    penguUIButton.addEventListener("click", () => {
      openPenguLoaderUI();
    });
    toolsRow.appendChild(penguUIButton);
    form.appendChild(toolsRow);

    // Save button (moved to last position)
    const saveButton = createActionButton();
    saveButton.id = "save-button";
    saveButton.textContent = t(_pendingSave ? "Saving..." : "Save");
    saveButton.disabled = !!_pendingSave;
    saveButton.style.marginTop = "8px";
    // At least its usual size, wider when the text is longer (other languages)
    saveButton.style.minWidth = "21%";
    saveButton.style.maxWidth = "100%";
    saveButton.addEventListener("click", () => {
      saveSettings();
    });
    form.appendChild(saveButton);
    const feedback = document.createElement("p");
    feedback.id = "okdev-settings-feedback";
    feedback.className = "okdev-save-status";
    feedback.setAttribute("role", "status");
    feedback.setAttribute("aria-live", "polite");
    form.appendChild(feedback);

    // Links section
    const linksSection = document.createElement("div");
    linksSection.className = "settings-links";

    const supportLink = document.createElement("a");
    supportLink.className = "settings-link";
    supportLink.href = SUPPORT_URL;
    supportLink.target = "_blank";
    supportLink.rel = "noopener noreferrer";
    supportLink.textContent = t("Support");
    linksSection.appendChild(supportLink);

    const githubLink = document.createElement("a");
    githubLink.className = "settings-link";
    githubLink.href = GITHUB_URL;
    githubLink.target = "_blank";
    githubLink.rel = "noopener noreferrer";
    githubLink.textContent = "GitHub";
    linksSection.appendChild(githubLink);

    form.appendChild(linksSection);

    flyoutContent.appendChild(form);
    flyoutFrame.appendChild(flyoutContent);
    panel.appendChild(flyoutFrame);

    // Setup slider interactions after form is added to DOM
    schedule(() => {
      setupSliderInteractions("threshold", thresholdSlider, thresholdButton, thresholdFill, thresholdValue, thresholdMin, thresholdMax, (value) => {
        return parseFloat(value) / 100;
      }, (value) => {
        return `${value.toFixed(2)} s`;
      });

      // Use the slider element's min/max so UI stays correct when limits change
      setupSliderInteractions(
        "timeout",
        timeoutSlider,
        timeoutButton,
        timeoutFill,
        timeoutValue,
        parseInt(timeoutSlider.min || "20", 10),
        parseInt(timeoutSlider.max || "180", 10),
        (value) => {
          return parseInt(value);
      }, (value) => {
        return `${value} s`;
      });
    }, 100);

    settingsPanel = panel;
    if (draft) {
      panel.dataset.dirty = 'true';
      panel._revision = draft.revision;
      for (const saved of draft.values) {
        const input = panel.querySelector('#' + saved.id);
        if (input) { input.value = saved.value; input.checked = saved.checked; }
      }
      if (_pendingSave?.panel === existingPanel) _pendingSave.panel = panel;
    }

    const reposition = () => {
      if (disposed || !panel.isConnected) return;
      const icon = navItem.querySelector(".menu-item-icon") || navItem;
      const rect = icon.getBoundingClientRect();
      const width = Math.min(420, window.innerWidth - 24);
      const top = Math.max(12, Math.min(rect.bottom + 18, window.innerHeight - 250));
      const left = Math.max(12, Math.min(rect.left + rect.width / 2 - width / 2, window.innerWidth - width - 12));
      flyoutFrame.style.width = `${width}px`;
      flyoutFrame.style.top = `${top}px`;
      flyoutFrame.style.left = `${left}px`;
      flyoutFrame.style.transform = "none";
      flyoutContent.style.maxHeight = `${Math.max(120, window.innerHeight - top - 12)}px`;
    };
    window.addEventListener("resize", reposition);
    cleanups.push(() => window.removeEventListener("resize", reposition));
    reposition();
    schedule(reposition, 0);
    prepareOwnedDialog(flyoutFrame, "Settings", closeSettingsPanel);
    flyoutFrame.setAttribute("role", "dialog");
    flyoutFrame.setAttribute("aria-modal", "true");
    flyoutFrame.setAttribute("aria-label", t("Settings"));
    flyoutFrame.tabIndex = -1;
    const closeButton = createActionButton();
    closeButton.className += " okdev-panel-close";
    closeButton.textContent = "×";
    closeButton.setAttribute("aria-label", t("Close"));
    closeButton.addEventListener("click", closeSettingsPanel);
    titleRow.appendChild(closeButton);
    schedule(() => closeButton.focus(), 0);

    // Request current settings and benchmark data
    requestSettings();
    requestDiagnostics();
  }

  function updateRangeVisual(slider, button, fill, valueDisplay, valueConverter, displayFormatter) {
    const min = Number(slider.min), max = Number(slider.max);
    const value = Math.max(min, Math.min(max, Number(slider.value)));
    const fraction = max > min ? (value - min) / (max - min) : 0;
    const position = `calc(${fraction * 100}% - ${fraction * 30}px)`;
    button.style.left = position;
    fill.style.width = position;
    const text = displayFormatter(valueConverter(value));
    valueDisplay.textContent = text;
    slider.setAttribute('aria-valuetext', text);
  }

  function setupSliderInteractions(sliderId, slider, button, fill, valueDisplay, min, max, valueConverter, displayFormatter) {
    if (!slider || !button || !fill || !valueDisplay) return;
    const update = () => updateRangeVisual(slider, button, fill, valueDisplay, valueConverter, displayFormatter);
    slider.addEventListener('input', update);
    update();
  }

  function updateSettingsForm() {
    const thresholdSlider = document.getElementById("threshold-slider");
    const thresholdValue = document.getElementById("threshold-value");
    const thresholdButton = thresholdSlider?.closest('.lol-settings-slider')?.querySelector('.lol-uikit-slider-button');
    const thresholdFill = thresholdSlider?.closest('.lol-settings-slider')?.querySelector('.lol-uikit-slider-fill');
    const timeoutSlider = document.getElementById("timeout-slider");
    const timeoutValue = document.getElementById("timeout-value");
    const timeoutButton = timeoutSlider?.closest('.lol-settings-slider')?.querySelector('.lol-uikit-slider-button');
    const timeoutFill = timeoutSlider?.closest('.lol-settings-slider')?.querySelector('.lol-uikit-slider-fill');
    const autostartCheckbox = document.getElementById("autostart-checkbox");
    const hideEmptyCategoriesCheckbox = document.getElementById("hide-empty-categories-checkbox");
    const pathInput = document.getElementById("game-path-input");

    if (thresholdSlider && thresholdValue && thresholdButton && thresholdFill) {
      const sliderValue = Math.round(currentSettings.threshold * 100);
      thresholdSlider.value = sliderValue;
      thresholdValue.textContent = `${currentSettings.threshold.toFixed(2)} s`;
      updateRangeVisual(thresholdSlider, thresholdButton, thresholdFill, thresholdValue,
        value => value / 100, value => `${value.toFixed(2)} s`);
    }

    if (timeoutSlider && timeoutValue && timeoutButton && timeoutFill) {
      timeoutSlider.value = currentSettings.monitorAutoResumeTimeout;
      timeoutValue.textContent = `${currentSettings.monitorAutoResumeTimeout} s`;
      updateRangeVisual(timeoutSlider, timeoutButton, timeoutFill, timeoutValue,
        value => value, value => `${value} s`);
    }

    if (autostartCheckbox) {
      autostartCheckbox.checked = currentSettings.autostart;
    }

    if (hideEmptyCategoriesCheckbox) {
      hideEmptyCategoriesCheckbox.checked = currentSettings.hideEmptyCategories;
    }

    if (pathInput) {
      pathInput.value = currentSettings.gamePath || "";
      // Update status based on validation result from settings data
      const pathStatus = document.getElementById("path-status");
      if (pathStatus) {
        const path = pathInput.value.trim();
        if (path.length === 0) {
          showPathStatus('');
        } else if (currentSettings.gamePathValid) {
          showPathStatus('valid');
        } else {
          // Request validation for the loaded path
          requestPathValidation(path);
        }
      }
    }

    // Update version badge
    const versionBadge = document.getElementById("okdev-version-badge");
    if (versionBadge && currentSettings.version) {
      versionBadge.textContent = `v${currentSettings.version}`;
    }
  }

  function updatePathStatus() {
    const pathInput = document.getElementById("game-path-input");
    const pathStatus = document.getElementById("path-status");

    if (!pathInput || !pathStatus) {
      return;
    }

    const path = pathInput.value.trim();
    clearTimeout(pathValidationTimeout);
    pathValidationTimeout = null;
    if (path.length === 0) {
      showPathStatus('');
      return;
    }

    // Show loading indicator while validating
    showPathStatus('pending');

    // Clear any existing timeout
    if (pathValidationTimeout) {
      clearTimeout(pathValidationTimeout);
    }

    // Debounce validation request (wait 500ms after user stops typing)
    pathValidationTimeout = setTimeout(() => {
      requestPathValidation(path);
    }, 500);
  }

  function requestPathValidation(path) {
    if (!path || !path.trim()) {
      return;
    }

    if (bridge) bridge.send({
      type: "path-validate",
      gamePath: path.trim(),
    });
  }

  function requestSettings() {
    if (bridge) bridge.send({
      type: "settings-request",
    });
  }

  function saveSettings() {
    if (_pendingSave) return;
    if (!bridge || !bridge.ready) {
      showSettingsFeedback(t("Connection lost. Reopen OKDEV and try again."), true);
      return;
    }
    const thresholdSlider = document.getElementById("threshold-slider");
    const timeoutSlider = document.getElementById("timeout-slider");
    const autostartCheckbox = document.getElementById("autostart-checkbox");
    const hideEmptyCategoriesCheckbox = document.getElementById("hide-empty-categories-checkbox");
    const pathInput = document.getElementById("game-path-input");

    const threshold = thresholdSlider
      ? parseFloat(thresholdSlider.value) / 100
      : 0.5;
    const monitorAutoResumeTimeout = timeoutSlider
      ? parseInt(timeoutSlider.value)
      : 60;
    const autostart = autostartCheckbox ? autostartCheckbox.checked : false;
    const hideEmptyCategories = hideEmptyCategoriesCheckbox ? hideEmptyCategoriesCheckbox.checked : false;
    const gamePath = pathInput ? pathInput.value.trim() : "";

    // Clamp threshold between 0.30 and 2.0
    const clampedThreshold = Math.max(0.3, Math.min(2.0, threshold));
    // Clamp timeout between 20 and 180
    const clampedTimeout = Math.max(20, Math.min(180, monitorAutoResumeTimeout));

    // Track what we're trying to save; we only clear warnings after the save succeeds.
    const requestId = `settings-${Date.now()}-${++_saveSequence}`;
    _pendingSave = { threshold: clampedThreshold, monitorAutoResumeTimeout: clampedTimeout,
      requestId, panel: settingsPanel, revision: settingsPanel?._revision || 0 };
    const saveButton = document.getElementById("save-button");
    if (saveButton) { saveButton.disabled = true; saveButton.textContent = t("Saving..."); }
    showSettingsFeedback("");
    clearTimeout(_saveTimeout);
    _saveTimeout = setTimeout(() => {
      _pendingSave = null;
      const button = document.getElementById("save-button");
      if (button) { button.disabled = false; button.textContent = t("Save"); }
      showSettingsFeedback(t("No response received. Check the connection before saving again."), true);
    }, 15000);

    try { bridge.send({
      type: "settings-save",
      requestId,
      threshold: clampedThreshold,
      monitorAutoResumeTimeout: clampedTimeout,
      autostart: autostart,
      hideEmptyCategories: hideEmptyCategories,
      gamePath: gamePath,
    }); } catch (error) {
      handleSettingsSaved({requestId, success:false, error:String(error)});
      return;
    }

    log("info", "Settings save requested", {
      threshold: clampedThreshold,
      monitorAutoResumeTimeout: clampedTimeout,
      autostart,
      hideEmptyCategories,
      gamePath,
    });
  }

  function openAddCustomModsDialog() {
    createCategorySelectionDialog();
    log("info", "Add custom mods dialog opened");
  }

  function createCategorySelectionDialog() {
    // Remove existing dialog if any
    const existingDialog = document.getElementById("add-custom-mods-dialog");
    if (existingDialog) {
      removeOwnedDialog(existingDialog);
    }

    // Create dialog container
    const dialog = document.createElement("div");
    dialog.id = "add-custom-mods-dialog";
    prepareOwnedDialog(dialog, "Add Custom Mods", closeCategoryDialog);
    dialog.style.position = "fixed";
    dialog.style.top = "0";
    dialog.style.left = "0";
    dialog.style.width = "100%";
    dialog.style.height = "100%";
    dialog.style.zIndex = "10001";
    dialog.style.pointerEvents = "none";
    document.body.appendChild(dialog);

    // Create backdrop
    const backdrop = document.createElement("div");
    backdrop.className = "backdrop";
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) {
        closeCategoryDialog();
      }
    });
    dialog.appendChild(backdrop);

    // Create flyout frame
    let flyoutFrame;
    try {
      flyoutFrame = document.createElement("lol-uikit-flyout-frame");
      flyoutFrame.id = "add-custom-mods-flyout";
      flyoutFrame.className = "flyout";
      flyoutFrame.setAttribute("orientation", "center");
      flyoutFrame.setAttribute("animated", "true");
      flyoutFrame.setAttribute("show", "true");
    } catch (e) {
      log("debug", "Could not create custom element, using div", e);
      flyoutFrame = document.createElement("div");
      flyoutFrame.id = "add-custom-mods-flyout";
      flyoutFrame.className = "flyout";
    }

    flyoutFrame.style.position = "absolute";
    flyoutFrame.style.top = "50%";
    flyoutFrame.style.left = "50%";
    flyoutFrame.style.transform = "translate(-50%, -50%)";
    flyoutFrame.style.zIndex = "10002";
    flyoutFrame.style.pointerEvents = "all";

    // Create flyout content
    let flyoutContent;
    try {
      flyoutContent = document.createElement("lc-flyout-content");
    } catch (e) {
      log("debug", "Could not create lc-flyout-content, using div", e);
      flyoutContent = document.createElement("div");
      flyoutContent.className = "lc-flyout-content";
    }

    // Title
    const title = document.createElement("div");
    title.className = "settings-title";
    title.textContent = t("Add Custom Mods");
    flyoutContent.appendChild(title);

    // Category buttons container
    const categoriesContainer = document.createElement("div");
    categoriesContainer.style.display = "flex";
    categoriesContainer.style.flexDirection = "column";
    categoriesContainer.style.gap = "10px";

    const categories = [
      { id: "skins", name: "Skins" },
      { id: "maps", name: "Maps" },
      { id: "fonts", name: "Fonts" },
      { id: "announcers", name: "Announcers" },
      { id: "ui", name: "UI" },
      { id: "voiceover", name: "Voiceover" },
      { id: "loading_screen", name: "Loading Screen" },
      { id: "vfx", name: "VFX" },
      { id: "sfx", name: "SFX" },
      { id: "others", name: "Others" },
    ];

    categories.forEach((category) => {
      const categoryButton = createActionButton();
      categoryButton.textContent = t(category.name);
      categoryButton.style.width = "100%";
      categoryButton.style.padding = "12px";
      categoryButton.addEventListener("click", () => {
        handleCategorySelection(category.id);
      });
      categoriesContainer.appendChild(categoryButton);
    });

    flyoutContent.appendChild(categoriesContainer);
    flyoutFrame.appendChild(flyoutContent);
    dialog.appendChild(flyoutFrame);

    // Prevent click from closing
    flyoutFrame.addEventListener("click", (e) => {
      e.stopPropagation();
    });
  }

  function closeCategoryDialog() {
    const dialog = document.getElementById("add-custom-mods-dialog");
    if (dialog) {
      removeOwnedDialog(dialog);
    }
  }

  function handleCategorySelection(category) {
    closeCategoryDialog();

    if (category === "skins") {
      // Open champion selection for skins
      openChampionSelection();
    } else {
      // Let the backend open the native mod-file picker for other categories.
      if (bridge) bridge.send({
        type: "add-custom-mods-category-selected",
        category: category,
      });
      log("info", `Category selected: ${category}`);
    }
  }

  function openChampionSelection(mode) {
    window.__okdevChampionSelectionMode = mode === "manage" ? "manage" : "add";

    // Remove existing dialog if any
    const existingDialog = document.getElementById("champion-selection-dialog");
    if (existingDialog) {
      removeOwnedDialog(existingDialog);
    }

    // Dialog is the backdrop itself — no extra wrapper
    const dialog = document.createElement("div");
    dialog.id = "champion-selection-dialog";
    prepareOwnedDialog(dialog, "Select Champion", closeChampionSelection);
    dialog.addEventListener("click", (e) => {
      if (e.target === dialog) {
        closeChampionSelection();
      }
    });
    document.body.appendChild(dialog);

    // Create flyout frame
    const flyoutFrame = document.createElement("div");
    flyoutFrame.id = "champion-selection-flyout";
    flyoutFrame.className = "flyout";
    flyoutFrame.style.maxHeight = "75vh";
    flyoutFrame.style.width = "700px";
    flyoutFrame.style.overflowY = "hidden";
    flyoutFrame.style.overflowX = "hidden";
    flyoutFrame.addEventListener("click", (e) => e.stopPropagation());

    // Create flyout content
    const flyoutContent = document.createElement("div");
    flyoutContent.className = "lc-flyout-content";

    // Header with back button and title
    const header = document.createElement("div");
    header.className = "dialog-header";

    // Back button
    const backButton = document.createElement("button");
    backButton.className = "back-button";
    backButton.innerHTML = '<svg viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"></polyline></svg>';
    backButton.setAttribute("aria-label", t("Go back"));
    backButton.addEventListener("click", () => {
      closeChampionSelection();
    });
    header.appendChild(backButton);

    // Title text
    const titleWrapper = document.createElement("div");
    titleWrapper.className = "dialog-title-wrapper";
    titleWrapper.textContent = window.__okdevChampionSelectionMode === "manage"
      ? t("Manage Mods - Select Champion")
      : t("Select Champion");
    header.appendChild(titleWrapper);

    flyoutContent.appendChild(header);

    // Search input using League UI component
    const searchContainer = document.createElement("div");
    searchContainer.className = "settings-section";

    let flatInput;
    try {
      flatInput = document.createElement("lol-uikit-flat-input");
    } catch (e) {
      flatInput = document.createElement("div");
      flatInput.className = "lol-uikit-flat-input";
    }
    flatInput.className = "champion-search-input";
    flyoutContent.style.width = "700px";

    const searchInput = document.createElement("input");
    searchInput.type = "search";
    searchInput.name = "champion_search";
    searchInput.id = "champion-search-input";
    searchInput.placeholder = t("Search champions...");
    searchInput.setAttribute("aria-label", t("Search champions..."));
    searchInput.autocomplete = "off";
    searchInput.autocorrect = "off";
    searchInput.autocapitalize = "off";
    searchInput.spellcheck = "false";

    flatInput.appendChild(searchInput);
    searchContainer.appendChild(flatInput);
    flyoutContent.appendChild(searchContainer);

    // Loading indicator
    const loadingIndicator = document.createElement("div");
    loadingIndicator.id = "champion-loading";
    loadingIndicator.textContent = t("Loading champions...");
    loadingIndicator.style.color = "#cdbe91";
    loadingIndicator.style.textAlign = "center";
    loadingIndicator.style.padding = "20px";
    loadingIndicator.style.fontFamily = '"Beaufort for LOL", serif';
    flyoutContent.appendChild(loadingIndicator);

    // Champions grid wrapper
    const championsGridWrapper = document.createElement("div");
    championsGridWrapper.id = "champions-grid-wrapper";
    championsGridWrapper.style.overflowY = "auto";
    championsGridWrapper.style.overflowX = "hidden";
    championsGridWrapper.style.maxHeight = "45vh";
    championsGridWrapper.style.marginTop = "12px";

    // Champions grid container
    const championsGrid = document.createElement("div");
    championsGrid.id = "champions-grid";
    championsGridWrapper.appendChild(championsGrid);
    flyoutContent.appendChild(championsGridWrapper);

    flyoutFrame.appendChild(flyoutContent);
    dialog.appendChild(flyoutFrame);

    // Request champions list
    if (bridge) bridge.send({
      type: "add-custom-mods-champion-selected",
      action: "list",
      withModsOnly: window.__okdevChampionSelectionMode === "manage",
    });

    // Search functionality
    searchInput.addEventListener("input", (e) => {
      const searchTerm = e.target.value.toLowerCase().trim();
      const allChampions = window.__okdevAllChampions || [];
      const filtered = allChampions.filter((champ) =>
        champ.name.toLowerCase().includes(searchTerm)
      );
      renderChampionsGrid(filtered);
    });

    // Store render function for bridge response
    window.__okdevChampionRenderer = renderChampionsGrid;
  }

  function closeChampionSelection() {
    const dialog = document.getElementById("champion-selection-dialog");
    if (dialog) {
      removeOwnedDialog(dialog);
    }
    delete window.__okdevChampionRenderer;
    delete window.__okdevAllChampions;
  }

  function renderChampionsGrid(champions) {
    const championsGrid = document.getElementById("champions-grid");
    if (!championsGrid) return;

    championsGrid.innerHTML = "";

    if (champions.length === 0) {
      championsGrid.innerHTML = `<div style="grid-column: 1 / -1; color: #cdbe91; text-align: center; padding: 20px; font-family: 'Beaufort for LOL', serif;">${escapeHtml(t("No champions found matching your search."))}</div>`;
      return;
    }

    champions.forEach((champion) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "champion-card";

      const img = document.createElement("img");
      img.src = `/lol-game-data/assets/v1/champion-icons/${champion.id}.png`;
      img.alt = champion.name;
      img.loading = "lazy";
      img.onerror = function () { this.style.display = "none"; };
      card.appendChild(img);

      const name = document.createElement("div");
      name.className = "champion-name";
      name.textContent = champion.name;
      card.appendChild(name);

      card.addEventListener("click", () => handleChampionSelection(champion.id));
      championsGrid.appendChild(card);
    });
  }

  function handleChampionSelection(championId) {
    const mode = window.__okdevChampionSelectionMode === "manage" ? "manage" : "add";
    closeChampionSelection();
    if (mode === "manage") {
      openChampionModsList(championId);
      log("info", "Champion selected for mod management: champion=" + championId);
    } else {
      openSkinSelection(championId);
      log("info", "Champion selected for custom mods: champion=" + championId);
    }
  }

  function openSkinSelection(championId) {
    // Remove existing dialog if any
    const existingDialog = document.getElementById("skin-selection-dialog");
    if (existingDialog) {
      removeOwnedDialog(existingDialog);
    }

    // Dialog is the backdrop itself
    const dialog = document.createElement("div");
    dialog.id = "skin-selection-dialog";
    prepareOwnedDialog(dialog, "Select Skins & Chromas", closeSkinSelection);
    dialog.addEventListener("click", (e) => {
      if (e.target === dialog) {
        closeSkinSelection();
      }
    });
    document.body.appendChild(dialog);

    // Create flyout frame
    const flyoutFrame = document.createElement("div");
    flyoutFrame.id = "skin-selection-flyout";
    flyoutFrame.className = "flyout";
    flyoutFrame.style.maxHeight = "75vh";
    flyoutFrame.style.height = "75vh";
    flyoutFrame.style.width = "700px";
    flyoutFrame.style.boxSizing = "border-box";
    flyoutFrame.style.overflowY = "hidden";
    flyoutFrame.style.overflowX = "hidden";
    flyoutFrame.addEventListener("click", (e) => e.stopPropagation());

    // Create flyout content
    const flyoutContent = document.createElement("div");
    flyoutContent.className = "lc-flyout-content";
    flyoutContent.style.display = "flex";
    flyoutContent.style.flexDirection = "column";
    flyoutContent.style.height = "100%";
    flyoutContent.style.boxSizing = "border-box";

    // Header with back button and title
    const header = document.createElement("div");
    header.className = "dialog-header";
    header.id = "skin-selection-header";

    // Back button
    const backButton = document.createElement("button");
    backButton.className = "back-button";
    backButton.innerHTML = '<svg viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"></polyline></svg>';
    backButton.setAttribute("aria-label", t("Go back"));
    backButton.addEventListener("click", (e) => {
      e.stopPropagation();
      closeSkinSelection();
      openChampionSelection();
    });
    header.appendChild(backButton);

    // Title text
    const titleWrapper = document.createElement("div");
    titleWrapper.className = "dialog-title-wrapper";
    titleWrapper.textContent = t("Select Skins & Chromas");
    header.appendChild(titleWrapper);

    flyoutContent.appendChild(header);

    // Loading indicator
    const loadingIndicator = document.createElement("div");
    loadingIndicator.id = "skin-loading";
    loadingIndicator.textContent = t("Loading skins...");
    loadingIndicator.style.color = "#cdbe91";
    loadingIndicator.style.textAlign = "center";
    loadingIndicator.style.padding = "20px";
    loadingIndicator.style.fontFamily = '"Beaufort for LOL", serif';
    flyoutContent.appendChild(loadingIndicator);

    // Skins list container
    const skinsList = document.createElement("div");
    skinsList.style.overflowY = "auto";
    skinsList.style.overflowX = "hidden";
    skinsList.id = "skins-list";
    skinsList.style.flex = "1 1 auto";
    skinsList.style.minHeight = "0";
    skinsList.style.maxHeight = "none";

    // Create inner container for flex layout
    const skinsListContainer = document.createElement("div");
    skinsListContainer.className = "skins-list-container";
    skinsList.appendChild(skinsListContainer);

    flyoutContent.appendChild(skinsList);

    const selectionActions = document.createElement("div");
    selectionActions.id = "skin-selection-actions";
    selectionActions.style.flex = "0 0 auto";

    const selectionCount = document.createElement("span");
    selectionCount.id = "skin-selection-count";
    selectionCount.textContent = t("{count} targets selected", { count: 0 });
    selectionActions.appendChild(selectionCount);

    const confirmButton = document.createElement("button");
    confirmButton.id = "skin-selection-confirm";
    confirmButton.type = "button";
    confirmButton.textContent = t("Confirm & Select Mod");
    confirmButton.disabled = true;
    confirmButton.addEventListener("click", (e) => {
      e.stopPropagation();
      confirmSkinSelection(championId);
    });
    selectionActions.appendChild(confirmButton);
    flyoutContent.appendChild(selectionActions);

    flyoutFrame.appendChild(flyoutContent);
    dialog.appendChild(flyoutFrame);

    window.__okdevSelectedSkinIds = new Set();

    // Establish ownership before sending; a host may respond immediately.
    window.__okdevSelectedChampionId = championId;
    // Request skins for champion
    if (bridge) bridge.send({
      type: "add-custom-mods-skin-selected",
      action: "list",
      championId: championId,
    });

  }

  function closeSkinSelection() {
    const dialog = document.getElementById("skin-selection-dialog");
    if (dialog) {
      removeOwnedDialog(dialog);
    }
    delete window.__okdevSelectedChampionId;
  }

  function updateSkinSelectionUI() {
    const selectedSkinIds = window.__okdevSelectedSkinIds || new Set();
    document.querySelectorAll("#skins-list [data-target-skin-id]").forEach((option) => {
      const skinId = Number(option.dataset.targetSkinId);
      const selected = selectedSkinIds.has(skinId);
      if (option.classList.contains("skin-option")) {
        option.classList.toggle("selected", selected);
      } else {
        option.classList.toggle("target-selected", selected);
      }
      option.setAttribute("aria-pressed", selected ? "true" : "false");
    });

    document.querySelectorAll("#skins-list .skin-card").forEach((card) => {
      const selected = Array.from(card.querySelectorAll("[data-target-skin-id]")).some(
        (option) => selectedSkinIds.has(Number(option.dataset.targetSkinId))
      );
      card.classList.toggle("selected", selected);
    });

    const selectionCount = document.getElementById("skin-selection-count");
    if (selectionCount) {
      const count = selectedSkinIds.size;
      selectionCount.textContent = count === 1 ? t("{count} target selected", { count }) : t("{count} targets selected", { count });
    }

    const confirmButton = document.getElementById("skin-selection-confirm");
    if (confirmButton) {
      confirmButton.disabled = selectedSkinIds.size === 0;
    }
  }

  function handleSkinSelection(championId, skinId) {
    const selectedSkinIds = window.__okdevSelectedSkinIds || new Set();
    const numericSkinId = Number(skinId);
    if (!Number.isFinite(numericSkinId) || numericSkinId <= 0) return;

    if (selectedSkinIds.has(numericSkinId)) {
      selectedSkinIds.delete(numericSkinId);
    } else {
      selectedSkinIds.add(numericSkinId);
    }
    window.__okdevSelectedSkinIds = selectedSkinIds;
    updateSkinSelectionUI();
    log("info", `Skin selection toggled: champion=${championId}, skin=${numericSkinId}`);
  }

  function confirmSkinSelection(championId) {
    const selectedSkinIds = Array.from(window.__okdevSelectedSkinIds || []);
    if (selectedSkinIds.length === 0) return;

    closeSkinSelection();
    if (bridge) bridge.send({
      type: "add-custom-mods-skin-selected",
      action: "create",
      championId: championId,
      skinIds: selectedSkinIds,
    });
    log("info", `Skin selection confirmed: champion=${championId}, skins=${selectedSkinIds.join(",")}`);
  }

  // ==================== Manage Custom Mods (delete) ====================

  const MANAGE_MOD_CATEGORIES = [
    { id: "skins", name: "Skins" },
    { id: "maps", name: "Maps" },
    { id: "fonts", name: "Fonts" },
    { id: "announcers", name: "Announcers" },
    { id: "ui", name: "UI" },
    { id: "voiceover", name: "Voiceover" },
    { id: "loading_screen", name: "Loading Screen" },
    { id: "vfx", name: "VFX" },
    { id: "sfx", name: "SFX" },
    { id: "others", name: "Others" },
  ];

  function handleManageCategorySelection(category) {
    if (category === "skins") {
      openChampionSelection("manage");
    } else {
      openCategoryModsList(category);
    }
  }

  function createModsListDialog(id, titleText, onBack, onDismiss) {
    const existingDialog = document.getElementById(id);
    if (existingDialog) {
      removeOwnedDialog(existingDialog);
    }

    const dismiss = () => {
      removeOwnedDialog(dialog);
      if (onDismiss) onDismiss();
    };

    const dialog = document.createElement("div");
    dialog.id = id;
    prepareOwnedDialog(dialog, titleText, dismiss);
    dialog.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;z-index:10001;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;";
    dialog.addEventListener("click", (e) => {
      if (e.target === dialog) {
        dismiss();
      }
    });
    document.body.appendChild(dialog);

    const flyoutFrame = document.createElement("div");
    flyoutFrame.className = "flyout";
    flyoutFrame.style.maxHeight = "75vh";
    flyoutFrame.style.width = "700px";
    flyoutFrame.style.boxSizing = "border-box";
    flyoutFrame.style.overflowY = "hidden";
    flyoutFrame.style.overflowX = "hidden";
    flyoutFrame.style.position = "relative";
    flyoutFrame.style.zIndex = "10002";
    flyoutFrame.addEventListener("click", (e) => e.stopPropagation());

    const flyoutContent = document.createElement("div");
    flyoutContent.className = "lc-flyout-content";
    flyoutContent.style.cssText = "display:flex;flex-direction:column;box-sizing:border-box;background:#010a13;border:1px solid #c8aa6e;padding:20px;width:100%;box-shadow:0 4px 12px rgba(0,0,0,0.5);color:#cdbe91;font-family:'Beaufort for LOL',serif;";

    const header = document.createElement("div");
    header.className = "dialog-header";

    const backButton = document.createElement("button");
    backButton.className = "back-button";
    backButton.innerHTML = '<svg viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"></polyline></svg>';
    backButton.setAttribute("aria-label", t("Go back"));
    backButton.addEventListener("click", (e) => {
      e.stopPropagation();
      dismiss();
      if (onBack) onBack();
    });
    header.appendChild(backButton);

    const titleWrapper = document.createElement("div");
    titleWrapper.className = "dialog-title-wrapper";
    titleWrapper.textContent = titleText;
    header.appendChild(titleWrapper);
    flyoutContent.appendChild(header);

    const feedback = document.createElement('div');
    feedback.className = 'okdev-management-feedback';
    feedback.setAttribute('role', 'alert');
    feedback.hidden = true;
    flyoutContent.appendChild(feedback);

    const listContainer = document.createElement("div");
    listContainer.id = `${id}-list`;
    listContainer.style.overflowY = "auto";
    listContainer.style.overflowX = "hidden";
    listContainer.style.maxHeight = "60vh";
    listContainer.style.marginTop = "12px";
    listContainer.innerHTML = `<div style="color: #cdbe91; text-align: center; padding: 20px; font-family: 'Beaufort for LOL', serif;">${escapeHtml(t("Loading mods..."))}</div>`;
    flyoutContent.appendChild(listContainer);

    flyoutFrame.appendChild(flyoutContent);
    dialog.appendChild(flyoutFrame);
    return { dialog, listContainer };
  }

  function renderModRow(listContainer, mod, onDelete, onRename) {
    const row = document.createElement("div");
    row.className = "mod-manage-row";
    row.style.display = "flex";
    row.style.alignItems = "center";
    row.style.justifyContent = "space-between";
    row.style.gap = "10px";
    row.style.padding = "10px";
    row.style.borderBottom = "1px solid rgba(205, 190, 145, 0.2)";

    const infoWrapper = document.createElement("div");
    infoWrapper.style.display = "flex";
    infoWrapper.style.alignItems = "center";
    infoWrapper.style.gap = "10px";
    infoWrapper.style.minWidth = "0";

    if (mod.thumbnailUrl) {
      const thumb = document.createElement("img");
      thumb.src = mod.thumbnailUrl;
      thumb.alt = mod.name;
      thumb.style.width = "44px";
      thumb.style.height = "44px";
      thumb.style.flex = "0 0 44px";
      thumb.style.objectFit = "cover";
      thumb.style.borderRadius = "50%";
      thumb.style.border = "2px solid #5b5a56";
      thumb.onerror = function () { this.style.display = "none"; };
      infoWrapper.appendChild(thumb);
    }

    const displayLabel = mod.displayName || mod.name;
    const nameEl = document.createElement("div");
    nameEl.textContent = displayLabel;
    nameEl.style.color = "#cdbe91";
    nameEl.style.fontFamily = '"Beaufort for LOL", serif';
    nameEl.style.overflow = "hidden";
    nameEl.style.textOverflow = "ellipsis";
    nameEl.style.whiteSpace = "nowrap";
    infoWrapper.appendChild(nameEl);

    row.appendChild(infoWrapper);

    const actions = document.createElement("div");
    actions.style.display = "flex";
    actions.style.alignItems = "center";
    actions.style.gap = "8px";
    actions.style.flex = "0 0 auto";

    if (onRename) {
      const renameButton = document.createElement("button");
      renameButton.type = "button";
      renameButton.className = "mod-rename-button";
      renameButton.textContent = t("Rename");
      renameButton.addEventListener("click", (e) => {
        e.stopPropagation();
        promptRenameMod(displayLabel, (newName) => onRename(renameButton, row, newName));
      });
      actions.appendChild(renameButton);
    }

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "mod-delete-button";
    deleteButton.textContent = t("Delete");
    deleteButton.addEventListener("click", (e) => {
      e.stopPropagation();
      confirmDeleteMod(displayLabel, () => onDelete(deleteButton, row));
    });
    actions.appendChild(deleteButton);

    row.appendChild(actions);
    listContainer.appendChild(row);
  }

  function promptRenameMod(currentName, onConfirm) {
    const existing = document.getElementById("rename-mod-dialog");
    if (existing) removeOwnedDialog(existing);

    const dlg = document.createElement("div");
    dlg.id = "rename-mod-dialog";
    prepareOwnedDialog(dlg, "Rename mod");
    dlg.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;z-index:10004;";

    const backdrop = document.createElement("div");
    backdrop.className = "backdrop";
    backdrop.addEventListener("click", () => dlg.remove());
    dlg.appendChild(backdrop);

    const box = document.createElement("div");
    box.className = "flyout";
    box.style.cssText = "position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:380px;padding:20px;background:#010a13;border:1px solid #c8aa6e;box-sizing:border-box;";
    box.addEventListener("click", (e) => e.stopPropagation());

    const label = document.createElement("div");
    label.textContent = t("Rename mod");
    label.style.cssText = "color:#c8aa6e;font-family:'Beaufort for LOL',serif;font-size:16px;font-weight:bold;margin-bottom:12px;text-align:center;";
    box.appendChild(label);

    const input = document.createElement("input");
    input.type = "text";
    input.value = currentName || "";
    input.setAttribute("aria-label", t("Rename mod"));
    input.maxLength = 100;
    input.style.cssText = "width:100%;padding:8px;background:#1e2328;border:1px solid #5c5b56;color:#cdbe91;font-size:14px;font-family:'Beaufort for LOL',serif;box-sizing:border-box;outline:none;";
    box.appendChild(input);

    const actionsRow = document.createElement("div");
    actionsRow.style.cssText = "display:flex;justify-content:flex-end;gap:10px;margin-top:16px;";

    const saveButton = document.createElement("button");
    saveButton.type = "button";
    saveButton.className = "mod-save-button";
    saveButton.textContent = t("Save");
    const submit = () => {
      const value = input.value.trim();
      if (!value) return;
      removeOwnedDialog(dlg);
      onConfirm(value);
    };
    saveButton.addEventListener("click", submit);
    actionsRow.appendChild(saveButton);

    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.className = "mod-rename-button";
    cancelButton.textContent = t("Cancel");
    cancelButton.addEventListener("click", () => dlg.remove());
    actionsRow.appendChild(cancelButton);

    box.appendChild(actionsRow);
    dlg.appendChild(box);
    document.body.appendChild(dlg);

    input.focus();
    input.select();
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); submit(); }
      else if (e.key === "Escape") { e.preventDefault(); removeOwnedDialog(dlg); }
    });
  }

  function confirmDeleteMod(modName, onConfirm) {
    const existing = document.getElementById("delete-mod-confirm-dialog");
    if (existing) removeOwnedDialog(existing);

    const confirmDialog = document.createElement("div");
    confirmDialog.id = "delete-mod-confirm-dialog";
    prepareOwnedDialog(confirmDialog, "Delete");
    confirmDialog.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;z-index:10004;";

    const backdrop = document.createElement("div");
    backdrop.className = "backdrop";
    backdrop.style.cssText = "position:absolute;inset:0;background:rgba(0,0,0,0.55);";
    backdrop.addEventListener("click", () => confirmDialog.remove());
    confirmDialog.appendChild(backdrop);

    const box = document.createElement("div");
    box.className = "flyout";
    box.style.cssText = "position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:360px;padding:20px;background:#010a13;border:1px solid #c8aa6e;box-sizing:border-box;box-shadow:0 4px 12px rgba(0,0,0,0.5);";
    box.addEventListener("click", (e) => e.stopPropagation());

    const message = document.createElement("div");
    message.style.backgroundColor = "#010a13";
    message.style.color = "#cdbe91";
    message.style.fontFamily = '"Beaufort for LOL", serif';
    message.style.marginBottom = "16px";
    message.textContent = t('Delete mod "{name}"? This cannot be undone.', { name: modName });
    box.appendChild(message);

    const actions = document.createElement("div");
    actions.style.display = "flex";
    actions.style.justifyContent = "flex-end";
    actions.style.gap = "10px";

    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.className = "mod-rename-button";
    cancelButton.textContent = t("Cancel");
    cancelButton.addEventListener("click", () => confirmDialog.remove());
    actions.appendChild(cancelButton);

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "mod-delete-button";
    deleteButton.textContent = t("Delete");
    deleteButton.addEventListener("click", () => {
      removeOwnedDialog(confirmDialog);
      onConfirm();
    });
    actions.appendChild(deleteButton);

    box.appendChild(actions);
    confirmDialog.appendChild(box);
    document.body.appendChild(confirmDialog);
  }

  function openChampionModsList(championId) {
    createModsListDialog(
      "champion-mods-manage-dialog",
      t("Manage Mods - Loading..."),
      () => openChampionSelection("manage"),
      () => { delete window.__okdevManageChampionId; }
    );
    window.__okdevManageChampionId = championId;

    sendManagedRequest(document.getElementById("champion-mods-manage-dialog"), {
      type: "request-manage-champion-mods",
      championId: championId,
    });
  }

  function closeChampionModsList() {
    const dialog = document.getElementById("champion-mods-manage-dialog");
    if (dialog) removeOwnedDialog(dialog);
    delete window.__okdevManageChampionId;
  }

  function handleManageSkinModsResponse(payload) {
    if (Number(payload.championId) !== Number(window.__okdevManageChampionId)) return;

    const dialog = document.getElementById("champion-mods-manage-dialog");
    const listContainer = document.getElementById("champion-mods-manage-dialog-list");
    if (!dialog || !listContainer) return;

    const titleWrapper = dialog.querySelector(".dialog-title-wrapper");
    if (titleWrapper) {
      titleWrapper.textContent = payload.championName
        ? t("Manage Mods - {name}", { name: payload.championName })
        : t("Manage Mods");
    }

    const owner = document.getElementById("champion-mods-manage-dialog");
    finishManagedRequest(owner);
    listContainer.innerHTML = "";
    if (payload.error) { showManagedFailure(owner, payload.error); return; }
    const mods = payload.mods || [];
    if (mods.length === 0) {
      listContainer.innerHTML = `<div style="color: #cdbe91; text-align: center; padding: 20px; font-family: 'Beaufort for LOL', serif;">${escapeHtml(t("No custom mods installed for this champion."))}</div>`;
      return;
    }

    // De-duplicate by path: the same folder can appear once per target skin.
    const seen = new Set();
    mods.forEach((mod) => {
      const dedupeKey = mod.relativePath || mod.modName;
      if (seen.has(dedupeKey)) return;
      seen.add(dedupeKey);
      renderModRow(
        listContainer,
        { name: mod.modName, displayName: mod.displayName, thumbnailUrl: mod.thumbnailUrl },
        (deleteButton, row) => {
          sendManagedRequest(listContainer.closest('[data-okdev-dialog]'), {
            type: "delete-champion-mod",
            championId: window.__okdevManageChampionId,
            modName: mod.modName,
            relativePath: mod.relativePath,
          });
        },
        (renameButton, row, newName) => {
          sendManagedRequest(listContainer.closest('[data-okdev-dialog]'), {
            type: "rename-champion-mod",
            championId: window.__okdevManageChampionId,
            modName: mod.modName,
            relativePath: mod.relativePath,
            newName: newName,
          });
        }
      );
    });
  }

  function handleChampionModDeleted(payload) {
    if (!payload.success) {
      log("error", "Failed to delete champion mod: " + (payload.error || "unknown error"));
    } else {
      log("info", `Champion mod deleted: champion=${payload.championId}, mod=${payload.modName}`);
    }
    if (
      document.getElementById("champion-mods-manage-dialog") &&
      Number(payload.championId) === Number(window.__okdevManageChampionId)
    ) {
      openChampionModsList(payload.championId);
      if (!payload.success) showManagedFailure(document.getElementById("champion-mods-manage-dialog"), payload.error || t("Operation failed"));
    }
  }

  function handleChampionModRenamed(payload) {
    if (!payload.success) {
      log("error", "Failed to rename champion mod: " + (payload.error || "unknown error"));
    } else {
      log("info", `Champion mod renamed: champion=${payload.championId}, mod=${payload.modName} -> ${payload.displayName}`);
    }
    if (
      document.getElementById("champion-mods-manage-dialog") &&
      Number(payload.championId) === Number(window.__okdevManageChampionId)
    ) {
      openChampionModsList(payload.championId);
      if (!payload.success) showManagedFailure(document.getElementById("champion-mods-manage-dialog"), payload.error || t("Operation failed"));
    }
  }

  function openCategoryModsList(category) {
    const categoryMeta = MANAGE_MOD_CATEGORIES.find((c) => c.id === category);
    createModsListDialog(
      "category-mods-manage-dialog",
      t("Manage Mods - {name}", { name: categoryMeta ? t(categoryMeta.name) : category }),
      null,
      () => { delete window.__okdevManageCategory; }
    );
    window.__okdevManageCategory = category;

    sendManagedRequest(document.getElementById("category-mods-manage-dialog"), {
      type: "request-manage-category-mods",
      category: category,
    });
  }

  function handleManageCategoryModsResponse(payload) {
    if (payload.category !== window.__okdevManageCategory) return;

    const listContainer = document.getElementById("category-mods-manage-dialog-list");
    if (!listContainer) return;

    const owner = document.getElementById("category-mods-manage-dialog");
    finishManagedRequest(owner);
    listContainer.innerHTML = "";
    if (payload.error) { showManagedFailure(owner, payload.error); return; }
    const mods = payload.mods || [];
    if (mods.length === 0) {
      listContainer.innerHTML = `<div style="color: #cdbe91; text-align: center; padding: 20px; font-family: 'Beaufort for LOL', serif;">${escapeHtml(t("No custom mods installed in this category."))}</div>`;
      return;
    }

    mods.forEach((mod) => {
      renderModRow(
        listContainer,
        { name: mod.name, displayName: mod.displayName },
        (deleteButton) => {
          sendManagedRequest(listContainer.closest('[data-okdev-dialog]'), {
            type: "delete-category-mod",
            category: window.__okdevManageCategory,
            modName: mod.name,
          });
        },
        (renameButton, row, newName) => {
          sendManagedRequest(listContainer.closest('[data-okdev-dialog]'), {
            type: "rename-category-mod",
            category: window.__okdevManageCategory,
            modName: mod.name,
            newName: newName,
          });
        }
      );
    });
  }

  function handleCategoryModDeleted(payload) {
    if (!payload.success) {
      log("error", "Failed to delete category mod: " + (payload.error || "unknown error"));
    } else {
      log("info", `Category mod deleted: category=${payload.category}, mod=${payload.modName}`);
    }
    if (
      document.getElementById("category-mods-manage-dialog") &&
      payload.category === window.__okdevManageCategory
    ) {
      openCategoryModsList(payload.category);
      if (!payload.success) showManagedFailure(document.getElementById("category-mods-manage-dialog"), payload.error || t("Operation failed"));
    }
  }

  function handleCategoryModRenamed(payload) {
    if (!payload.success) {
      log("error", "Failed to rename category mod: " + (payload.error || "unknown error"));
    } else {
      log("info", `Category mod renamed: category=${payload.category}, mod=${payload.modName} -> ${payload.displayName}`);
    }
    if (
      document.getElementById("category-mods-manage-dialog") &&
      payload.category === window.__okdevManageCategory
    ) {
      openCategoryModsList(payload.category);
      if (!payload.success) showManagedFailure(document.getElementById("category-mods-manage-dialog"), payload.error || t("Operation failed"));
    }
  }

  function handleChampionsListResponse(payload) {
    const loadingIndicator = document.getElementById("champion-loading");
    if (loadingIndicator) {
      loadingIndicator.style.display = "none";
    }

    const championsGrid = document.getElementById("champions-grid");
    if (!championsGrid) return;

    if (payload.error) {
      championsGrid.innerHTML = `<div style="grid-column: 1 / -1; color: #ff6b6b; text-align: center; padding: 20px; font-family: 'Beaufort for LOL', serif;">${escapeHtml(tAny(payload.error))}</div>`;
      return;
    }

    const champions = payload.champions || [];
    if (champions.length === 0) {
      const emptyText = window.__okdevChampionSelectionMode === "manage"
        ? t("No champions have custom skins yet.")
        : t("No champions found. Please ensure League of Legends client is running.");
      championsGrid.innerHTML = `<div style="grid-column: 1 / -1; color: #cdbe91; text-align: center; padding: 20px; font-family: 'Beaufort for LOL', serif;">${escapeHtml(emptyText)}</div>`;
      return;
    }

    // Store champions for search functionality
    window.__okdevAllChampions = champions;

    // Render champions
    if (window.__okdevChampionRenderer) {
      window.__okdevChampionRenderer(champions);
    } else {
      // Fallback: render directly
      renderChampionsGrid(champions);
    }
  }

  function handleChampionSkinsResponse(payload) {
    // A response for a previous selection must never replace this champion's
    // targets, including when the old request finished after Back was used.
    if (Number(payload.championId) !== Number(window.__okdevSelectedChampionId)) return;
    const loadingIndicator = document.getElementById("skin-loading");
    if (loadingIndicator) {
      loadingIndicator.style.display = "none";
    }

    const skinsList = document.getElementById("skins-list");
    if (!skinsList) return;

    if (payload.error) {
      let skinsListContainer = skinsList.querySelector(".skins-list-container");
      if (!skinsListContainer) {
        skinsListContainer = document.createElement("div");
        skinsListContainer.className = "skins-list-container";
        skinsList.innerHTML = "";
        skinsList.appendChild(skinsListContainer);
      } else {
        skinsListContainer.innerHTML = "";
      }
      skinsListContainer.innerHTML = `<div style="color: #ff6b6b; text-align: center; padding: 20px; font-family: 'Beaufort for LOL', serif;">${escapeHtml(tAny(payload.error))}</div>`;
      return;
    }

    const skins = payload.skins || [];
    const championId = payload.championId;

    // Update title with champion name if available
    const header = document.getElementById("skin-selection-header");
    if (header && payload.championName) {
      const titleWrapper = header.querySelector(".dialog-title-wrapper");
      if (titleWrapper) {
        titleWrapper.textContent = t("Select Skins & Chromas - {name}", { name: payload.championName });
      }
    }

    // Get or create the container inside the scrollable
    let skinsListContainer = skinsList.querySelector(".skins-list-container");
    if (!skinsListContainer) {
      skinsListContainer = document.createElement("div");
      skinsListContainer.className = "skins-list-container";
      skinsList.innerHTML = "";
      skinsList.appendChild(skinsListContainer);
    } else {
      skinsListContainer.innerHTML = "";
    }

    if (skins.length === 0) {
      skinsListContainer.innerHTML = `<div style="color: #cdbe91; text-align: center; padding: 20px; font-family: 'Beaufort for LOL', serif;">${escapeHtml(t("No skins found for this champion."))}</div>`;
      return;
    }

    const baseSkins = skins.filter((skin) => !skin.isChroma);
    const chromasByBaseSkin = new Map();
    skins.filter((skin) => skin.isChroma).forEach((chroma) => {
      const baseSkinId = Number(chroma.baseSkinId);
      if (!Number.isFinite(baseSkinId)) return;
      if (!chromasByBaseSkin.has(baseSkinId)) {
        chromasByBaseSkin.set(baseSkinId, []);
      }
      chromasByBaseSkin.get(baseSkinId).push(chroma);
    });

    const getSkinId = (skin) => Number(skin.skinId || skin.id);
    const getTilePath = (skin) => {
      const skinId = getSkinId(skin);
      return skin.tilePath || `/lol-game-data/assets/v1/champion-tiles/${skinId}.jpg`;
    };

    baseSkins.forEach((skin) => {
      const baseSkinId = getSkinId(skin);
      const chromas = chromasByBaseSkin.get(baseSkinId) || [];
      const card = document.createElement("div");
      card.className = "skin-card";
      card.dataset.baseSkinId = String(baseSkinId);

      const inner = document.createElement("div");
      inner.className = "skin-card-inner";

      const front = document.createElement("div");
      front.className = "skin-card-face skin-card-front";
      const targetButton = document.createElement("button");
      targetButton.type = "button";
      targetButton.className = "skin-target";
      targetButton.dataset.targetSkinId = String(baseSkinId);
      targetButton.setAttribute("aria-pressed", "false");
      targetButton.setAttribute("aria-label", skin.name || t("Skin {id}", { id: baseSkinId }));
      const placeholder = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      placeholder.classList.add('skin-placeholder');
      placeholder.setAttribute('viewBox', '0 0 100 120');
      placeholder.setAttribute('aria-hidden', 'true');
      placeholder.innerHTML = '<path d="M50 5 90 26 83 82 50 113 17 82 10 26Z M50 18 77 33 72 76 50 96 28 76 23 33Z M33 46 50 60 67 46 59 75 50 82 41 75Z"/>';
      targetButton.appendChild(placeholder);

      const img = document.createElement("img");
      img.src = getTilePath(skin);
      img.alt = skin.name || t("Skin {id}", { id: baseSkinId });
      img.loading = "lazy";
      img.onerror = function () { this.style.display = "none"; };
      targetButton.appendChild(img);

      const nameEl = document.createElement("span");
      nameEl.className = "skin-name";
      nameEl.textContent = skin.name || t("Skin {id}", { id: baseSkinId });
      targetButton.appendChild(nameEl);
      front.appendChild(targetButton);

      targetButton.addEventListener("click", () => handleSkinSelection(championId, baseSkinId));

      if (chromas.length > 0) {
        const chromaButton = document.createElement("button");
        chromaButton.type = "button";
        chromaButton.className = "skin-chroma-button";
        chromaButton.textContent = t("Chromas {count}", { count: chromas.length });
        chromaButton.setAttribute("aria-label", t("Show {count} chromas", { count: chromas.length }));
        chromaButton.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          card.classList.add("is-flipped");
          front.inert = true;
          front.setAttribute("aria-hidden", "true");
          const back = card.querySelector('.skin-card-back');
          back.inert = false;
          back.removeAttribute('aria-hidden');
          back.querySelector('button')?.focus();
        });
        front.appendChild(chromaButton);
      }
      inner.appendChild(front);

      if (chromas.length > 0) {
        const back = document.createElement("div");
        back.className = "skin-card-face skin-card-back";
        back.inert = true;
        back.setAttribute('aria-hidden', 'true');

        const backHeader = document.createElement("div");
        backHeader.className = "skin-card-back-header";

        const backButton = document.createElement("button");
        backButton.type = "button";
        backButton.className = "skin-card-back-close";
        backButton.textContent = "\u2039";
        backButton.setAttribute("aria-label", t("Back to skin"));
        backButton.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          card.classList.remove("is-flipped");
          back.inert = true;
          back.setAttribute('aria-hidden', 'true');
          front.inert = false;
          front.removeAttribute('aria-hidden');
          front.querySelector('.skin-chroma-button')?.focus();
        });
        backHeader.appendChild(backButton);

        const backTitle = document.createElement("span");
        backTitle.textContent = t("{name} - Chromas", { name: skin.name || t("Skin") });
        backHeader.appendChild(backTitle);
        back.appendChild(backHeader);

        const options = document.createElement("div");
        options.className = "skin-card-back-options";
        [skin, ...chromas].forEach((optionSkin, optionIndex) => {
          const optionId = getSkinId(optionSkin);
          const option = document.createElement("button");
          option.type = "button";
          option.className = "skin-option";
          option.dataset.targetSkinId = String(optionId);
          option.setAttribute("aria-pressed", "false");

          const optionImg = document.createElement("img");
          optionImg.src = getTilePath(optionSkin);
          optionImg.alt = optionSkin.name || t("Skin {id}", { id: optionId });
          optionImg.loading = "lazy";
          optionImg.onerror = function () { this.style.display = "none"; };
          option.appendChild(optionImg);

          const optionName = document.createElement("span");
          optionName.className = "skin-option-name";
          optionName.textContent = optionIndex === 0
            ? t("Base skin")
            : (optionSkin.name || t("Chroma {id}", { id: optionId }));
          option.appendChild(optionName);

          option.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            handleSkinSelection(championId, optionId);
          });
          options.appendChild(option);
        });
        back.appendChild(options);
        inner.appendChild(back);
      }

      card.appendChild(inner);
      skinsListContainer.appendChild(card);
    });
    updateSkinSelectionUI();
  }

  function handleFolderOpenedResponse(payload) {
    if (payload.cancelled) {
      log("info", "Mod import cancelled");
    } else if (payload.error) {
      log("error", `Failed to import mod: ${escapeHtml(payload.error)}`);
      showSettingsFeedback(tAny(payload.error), true);
    } else {
      log("info", `Imported mod: ${payload.modName || payload.path || "success"}`);
      showSettingsFeedback(t("Mod imported: {name}", {name: payload.modName || t("Custom mod")}));
    }
  }

  function openLogsFolder() {
    if (bridge) bridge.send({
      type: "open-logs-folder",
    });
    log("info", "Open logs folder requested");
  }

  function requestDiagnostics() {
    if (bridge) bridge.send({ type: "diagnostics-request" });
  }

  function openDiagnosticsDialog() {
    // If already open, close it
    const existing = document.getElementById("okdev-diagnostics-dialog");
    if (existing) {
      removeOwnedDialog(existing);
      diagnosticsDialog = null;
      return;
    }

    const dialog = document.createElement("div");
    dialog.id = "okdev-diagnostics-dialog";
    prepareOwnedDialog(dialog, "Troubleshooting");
    dialog.style.position = "fixed";
    dialog.style.top = "0";
    dialog.style.left = "0";
    dialog.style.width = "100%";
    dialog.style.height = "100%";
    dialog.style.zIndex = "10002";
    dialog.style.pointerEvents = "none";
    document.body.appendChild(dialog);

    const backdrop = document.createElement("div");
    backdrop.style.position = "absolute";
    backdrop.style.top = "0";
    backdrop.style.left = "0";
    backdrop.style.width = "100%";
    backdrop.style.height = "100%";
    backdrop.style.background = "rgba(0, 0, 0, 0.6)";
    backdrop.style.pointerEvents = "auto";
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) {
        removeOwnedDialog(dialog);
        diagnosticsDialog = null;
      }
    });
    dialog.appendChild(backdrop);

    const panel = document.createElement("div");
    panel.style.position = "absolute";
    panel.style.left = "50%";
    panel.style.top = "50%";
    panel.style.transform = "translate(-50%, -50%)";
    panel.style.width = "520px";
    panel.style.maxWidth = "calc(100vw - 24px)";
    panel.style.maxHeight = "calc(100vh - 24px)";
    panel.style.boxSizing = "border-box";
    panel.style.display = "flex";
    panel.style.flexDirection = "column";
    panel.style.background = "#0b0f14";
    panel.style.border = "1px solid #463714";
    panel.style.boxShadow = "0 10px 30px rgba(0,0,0,0.6)";
    panel.style.padding = "14px";
    panel.style.pointerEvents = "auto";
    panel.style.position = "absolute";

    const title = document.createElement("div");
    title.textContent = t("Troubleshooting");
    title.style.color = "#cdbe91";
    title.style.fontFamily = "'Beaufort for LOL', serif";
    title.style.fontSize = "16px";
    title.style.marginBottom = "10px";
    panel.appendChild(title);

    // Top-right close button
    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.setAttribute("aria-label", t("Close"));
    closeBtn.textContent = "×";
    closeBtn.style.position = "absolute";
    closeBtn.style.top = "6px";
    closeBtn.style.right = "8px";
    closeBtn.style.width = "26px";
    closeBtn.style.height = "26px";
    closeBtn.style.lineHeight = "24px";
    closeBtn.style.padding = "0";
    closeBtn.style.border = "none";
    closeBtn.style.background = "#0b0f14";
    closeBtn.style.color = "#cdbe91";
    closeBtn.style.cursor = "pointer";
    closeBtn.style.borderRadius = "4px";
    closeBtn.style.fontFamily = "'Beaufort for LOL', serif";
    closeBtn.style.fontSize = "18px";
    closeBtn.addEventListener("click", () => {
      removeOwnedDialog(dialog);
      diagnosticsDialog = null;
    });
    panel.appendChild(closeBtn);

    const body = document.createElement("div");
    body.id = "okdev-diagnostics-body";
    body.style.color = "#cdbe91";
    body.style.fontFamily = "'Beaufort for LOL', serif";
    body.style.fontSize = "12px";
    body.style.whiteSpace = "normal";
    body.style.border = "1px solid #010a13";
    body.style.background = "#070a0e";
    body.style.padding = "10px";
    body.style.maxHeight = "220px";
    body.style.minHeight = "0";
    body.style.overflowWrap = "anywhere";
    body.style.overflow = "auto";
    body.style.lineHeight = "1.35";
    body.textContent = t("Loading…");
    panel.appendChild(body);

    const foot = document.createElement("div");
    foot.id = "okdev-diagnostics-foot";
    foot.style.marginTop = "8px";
    foot.style.color = "#b8b1a3";
    foot.style.overflowWrap = "anywhere";
    foot.style.maxHeight = "25vh";
    foot.style.overflowY = "auto";
    foot.style.fontFamily = "'Beaufort for LOL', serif";
    foot.style.fontSize = "11px";
    panel.appendChild(foot);

    backdrop.appendChild(panel);
    diagnosticsDialog = dialog;

    requestDiagnostics();
    renderDiagnosticsDialog();
  }

  function renderDiagnosticsDialog() {
    if (!diagnosticsDialog) return;
    const body = document.getElementById("okdev-diagnostics-body");
    const foot = document.getElementById("okdev-diagnostics-foot");
    if (!body || !foot) return;

    const errors = Array.isArray(diagnosticsState.errors) ? diagnosticsState.errors : [];
    if (errors.length === 0) {
      body.innerHTML = `
        <div style="opacity:0.85; margin-bottom:8px;">${escapeHtml(t("No recent errors."))}</div>
        <div style="opacity:0.75;">${escapeHtml(t("If something feels off, open the logs folder and share the latest log in a discord ticket."))}</div>
      `.trim();
    } else {
      const clamp = (n, min, max) => Math.max(min, Math.min(max, n));
      const fmtS = (n, digits = 2) => (typeof n === "number" && Number.isFinite(n) ? `${n.toFixed(digits)} s` : "");
      const curThreshold = typeof currentSettings?.threshold === "number" ? currentSettings.threshold : null;
      const curMonitorTimeout =
        typeof currentSettings?.monitorAutoResumeTimeout === "number"
          ? currentSettings.monitorAutoResumeTimeout
          : null;

      const escapeHtml = (value) =>
        String(value ?? "")
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;")
          .replace(/'/g, "&#39;");

      const describe = (e) => {
        const raw = String(e?.text || "").trim();
        const code = String(e?.code || "").trim();

        const isInjectionThreshold =
          code === "BASE_SKIN_FORCE_SLOW" ||
          code === "BASE_SKIN_VERIFY_FAILED" ||
          /Injection\s*Threshold/i.test(raw);
        const isMonitorTimeout =
          code === "AUTO_RESUME_TRIGGERED" ||
          code === "MONITOR_AUTO_RESUME_TIMEOUT" ||
          /Auto-Resume Timeout/i.test(raw) ||
          /Monitor Auto-Resume Timeout/i.test(raw);

        if (isInjectionThreshold) {
          const thresholdAtMax =
            typeof curThreshold === "number" && Number.isFinite(curThreshold) && curThreshold >= (2.0 - 1e-6);
          const stats = diagnosticsState.baseSkinStats;
          const hasTrackerData = stats && typeof stats.p90_ms === "number" && stats.confirmed_count > 0;
          const recMs = hasTrackerData ? stats.recommended_threshold_ms : (e.recommendedThresholdMs || null);
          const recS = typeof recMs === "number" ? (recMs / 1000).toFixed(2) : null;

          let fixText;
          if (thresholdAtMax) {
            fixText = t("Fix: you're already at the maximum Injection Threshold. This usually means the injection is extremely slow. Try lighter mods, close heavy apps, move League/mods to an SSD, and consider adding antivirus exclusions for the League and OKDEV folders. Then retry.");
          } else if (hasTrackerData) {
            fixText = t('Fix: based on {games} game(s), base skin confirmation takes up to {ms}ms (p90). Recommended threshold: {seconds}s. Use the "Apply recommended" button below, or increase "Injection Threshold" manually.', { games: stats.confirmed_count, ms: stats.p90_ms, seconds: recS });
          } else {
            fixText = t('Fix: increase "Injection Threshold (seconds)" and click Save. If the warning is still there, increase it again and Save again. Once the warning is gone, retry your skin selection.');
          }

          return {
            title:
              code === "BASE_SKIN_VERIFY_FAILED"
                ? t("Base skin verification failed (selected skin may not apply)")
                : t("Base skin forcing took too long (skin may not appear)"),
            details: [
              code === "BASE_SKIN_VERIFY_FAILED"
                ? t("What it means: the client didn't confirm the base skin change in time.")
                : t("What it means: forcing the base skin took too long, so the selected skin may not show."),
              fixText,
            ],
          };
        }

        if (isMonitorTimeout) {
          const timeoutAtMax =
            typeof curMonitorTimeout === "number" &&
            Number.isFinite(curMonitorTimeout) &&
            curMonitorTimeout >= (180 - 1e-6);
          return {
            title: t("Injection exceeded the timeout (process was stopped)"),
            details: [
              t("What it means: injection took longer than the allowed time, so OKDEV stopped the process."),
              timeoutAtMax
                ? t("Fix: you're already at the maximum Monitor Auto-Resume Timeout. This usually means the injection is extremely slow. Try lighter mods, close heavy apps, move League/mods to an SSD, and consider adding antivirus exclusions for the League and OKDEV folders. Then retry.")
                : t('Fix: increase "Monitor Auto-Resume Timeout (seconds)" and click Save. If the warning is still there, increase it again and Save again. Once the warning is gone, try again.'),
            ],
          };
        }

        const isLowDiskSpace =
          code === 'LOW_DISK_SPACE' || /Low Disk Space/i.test(raw) || /not enough disk space/i.test(raw);
        if (isLowDiskSpace) {
          return {
            title: t('Not enough disk space for injection'),
            details: [
              t('What it means: OKDEV could not create the overlay for the selected skin.'),
              t('Fix: free up space on the drive containing OKDEV injection files, then retry. Map mods can require several GB.'),
            ],
          };
        }

        if (code === 'LTK_PATCHER_EOL') {
          return {
            title: t('LTK patcher is outdated (end of life reached)'),
            details: [
              t('What it means: your ltk_patcher_dll.dll no longer supports the current game build, so skins cannot be injected.'),
              t("Fix: update LTK Manager, copy its new ltk_patcher_host.exe and ltk_patcher_dll.dll into OKDEV's tools folder, then restart OKDEV."),
            ],
          };
        }

        if (code === 'LTK_PATCHER_MISSING') {
          return {
            title: t('LTK patcher files are missing'),
            details: [
              t('What it means: OKDEV needs ltk_patcher_host.exe and ltk_patcher_dll.dll to inject skins.'),
              t("Fix: copy both files from your LTK Manager install into OKDEV's tools folder, then restart OKDEV."),
            ],
          };
        }

        if (code === 'LTK_PATCHER_FAILED') {
          const detail = String(e?.detail || '').trim();
          return {
            title: t('LTK patcher failed during injection'),
            details: [
              detail ? t('What happened: {detail}', { detail }) : t('What happened: the LTK patcher reported an error.'),
              t('Fix: make sure your LTK patcher files are up to date, then retry. Full output is in okdev_runoverlay_*.log in the OKDEV logs folder.'),
            ],
          };
        }

        // Fallback: show raw error text as-is.
        return {
          title: raw ? tAny(raw) : t("(unknown error)"),
          details: [],
        };
      };

      const headerHtml = `
        <div style="display:flex; flex-direction:column; gap:4px; margin-bottom:10px;">
          <div style="font-weight:700;">${escapeHtml(t("Errors (most recent first)"))}</div>
          <div style="opacity:0.75;">${escapeHtml(t("Tip: after changing a setting, click {save}, then retry.")).replace("{save}", `<span style="font-weight:700;">${escapeHtml(t("Save"))}</span>`)}</div>
        </div>
      `.trim();

      const itemsHtml = errors
        .map((e, idx) => {
          const ts = String(e?.ts || "").trim();
          const desc = describe(e);
          const title = escapeHtml(desc.title);
          const tsHtml = ts ? `<span style="opacity:0.75;">${escapeHtml(ts)}</span>` : "";

          const detailsHtml = (desc.details || [])
            .map((d) => `<li style="margin:2px 0;">${escapeHtml(d)}</li>`)
            .join("");

          return `
            <div style="border:1px solid rgba(70,55,20,0.55); background: rgba(1,10,19,0.35); padding:8px; margin-bottom:8px;">
              <div style="display:flex; gap:8px; align-items:baseline; margin-bottom:6px;">
                <span style="font-weight:800; color:#c89b3c;">${idx + 1}.</span>
                ${tsHtml}
                <span style="font-weight:700; flex:1;">${title}</span>
                <button class="okdev-diagnostics-delete" data-key="${escapeHtml(e?.key || e?.text || "")}" aria-label="${escapeHtml(t("Delete this error"))}" title="${escapeHtml(t("Delete this error"))}" style="
                  border:none; background:none; color:#cdbe91; cursor:pointer; padding:4px; width:24px; height:24px; flex:0 0 24px;
                "><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg></button>
              </div>
              ${
                detailsHtml
                  ? `<ul style="margin:0; padding-left:18px;">${detailsHtml}</ul>`
                  : `<div style="opacity:0.8;">${escapeHtml(tAny(String(e?.text || "").trim()) || t("No additional details."))}</div>`
              }
            </div>
          `.trim();
        })
        .join("");

      body.innerHTML = `${headerHtml}${itemsHtml}`;
      body.querySelectorAll(".okdev-diagnostics-delete").forEach((btn) => {
        btn.addEventListener("click", () => deleteDiagnostics([btn.dataset.key]));
      });
    }

    foot.innerHTML = "";
    if (errors.length > 0) {
      const clearAll = document.createElement("button");
      clearAll.textContent = t("Clear all");
      clearAll.style.cssText = `
        padding:2px 10px; border:1px solid #463714; background:#1e2328;
        color:#cdbe91; cursor:pointer; font-family:'Beaufort for LOL',serif; font-size:12px;
      `;
      clearAll.addEventListener("click", () => {
        if (bridge) bridge.send({ type: "diagnostics-clear" });
      });
      foot.appendChild(clearAll);
    }
  }

  function deleteDiagnostics(keys) {
    const wanted = keys.filter(Boolean);
    if (!bridge || wanted.length === 0) return;
    bridge.send({ type: "diagnostics-delete", keys: wanted });
  }

  function renderThresholdBenchmark() {
    const el = document.getElementById("okdev-threshold-benchmark");
    if (!el) return;

    const stats = diagnosticsState.baseSkinStats;
    const hasStats = stats && typeof stats.confirmed_count === "number" && stats.confirmed_count > 0;

    if (!hasStats) {
      el.innerHTML = "";
      return;
    }

    const recMs = stats.recommended_threshold_ms;
    const recS = typeof recMs === "number" ? (recMs / 1000).toFixed(2) : null;
    const curThresholdVal = typeof currentSettings?.threshold === "number" ? currentSettings.threshold : null;
    const needsIncrease = recS !== null && curThresholdVal !== null && curThresholdVal < parseFloat(recS) - 0.001;
    const games = stats.confirmed_count;
    const label = games > 1 ? t("{count} games", { count: games }) : t("{count} game", { count: games });

    let html;
    if (needsIncrease) {
      const recommended = `<span style="color:#c89b3c; font-weight:700;">${recS}s</span>`;
      html = `<span style="color:#c8aa6e;">${escapeHtml(t("Based on {games}, we recommend {value}", { games: label })).replace("{value}", recommended)}</span>`;
      html += ` <button id="okdev-apply-recommended-btn" style="
        margin-left:4px; padding:1px 8px; border:1px solid #463714; background:#1e2328;
        color:#cdbe91; cursor:pointer; font-family:'Beaufort for LOL',serif; font-size:11px;
        vertical-align:middle;
      ">${escapeHtml(t("Apply"))}</button>`;
    } else {
      html = `<span style="color:#5b9a32;">${escapeHtml(t("Your threshold looks good (based on {games})", { games: label }))}</span>`;
    }

    el.innerHTML = html;

    const applyBtn = document.getElementById("okdev-apply-recommended-btn");
    if (applyBtn) {
      applyBtn.addEventListener("click", () => {
        if (bridge) {
          bridge.send({ type: "diagnostics-apply-recommended" });
          applyBtn.textContent = t("Applied!");
          applyBtn.disabled = true;
          applyBtn.style.opacity = "0.6";
          setTimeout(() => {
            if (bridge) bridge.send({ type: "settings-request" });
            requestDiagnostics();
          }, 500);
        }
      });
    }
  }

  function openPenguLoaderUI() {
    if (bridge) bridge.send({
      type: "open-pengu-loader-ui",
    });
    log("info", "Open Pengu Loader UI requested");
  }

  function closeSettingsPanel() {
    if (!settingsPanel) return;
    const closingPanel = settingsPanel;
    settingsPanel = null;
    closingPanel.dispose?.();
    closingPanel.querySelector('[data-okdev-dialog]')?.removeAttribute('data-okdev-dialog');
    document.querySelectorAll('[data-okdev-dialog]').forEach(removeOwnedDialog);
    delete window.__okdevManageChampionId;
    delete window.__okdevManageCategory;
    delete window.__okdevChampionRenderer;
    delete window.__okdevAllChampions;
    if (closingPanel.opener?.isConnected) closingPanel.opener.focus();

    // Disable selected nav item
    const navItem = document.querySelector(".menu_item_Golden");
    if (navItem) {
      navItem.removeAttribute("active")
    }

    // Restore last active item
    const lastActiveNavItem = document.querySelector(".main-nav-bar > * > lol-uikit-navigation-item[okdevLastActive]");
    if (lastActiveNavItem) {
      lastActiveNavItem.removeAttribute("okdevLastActive")
      lastActiveNavItem.setAttribute("active", true);
    }

    // Cancel any pending reposition timer to avoid a "one-frame" flicker after closing.
    try {
      if (_flyoutRepositionTimer) {
        clearTimeout(_flyoutRepositionTimer);
        _flyoutRepositionTimer = null;
      }
    } catch (e) {}

    // If troubleshooting dialog is open, close it too (it is a separate fixed overlay).
    try {
      const diag = document.getElementById("okdev-diagnostics-dialog");
      if (diag) diag.remove();
      diagnosticsDialog = null;
    } catch (e) {}

    const cleanup = () => {
      try {
        closingPanel.remove();
      } catch (e) {}
    };

    // Prefer the built-in flyout animation when available.
    let flyout = null;
    try {
      flyout = document.getElementById(FLYOUT_ID);
    } catch (e) {
      flyout = null;
    }

    if (flyout) {
      // Disable interactions immediately while closing.
      try {
        flyout.style.pointerEvents = "none";
      } catch (e) {}

      // Smooth close (avoid scale/pop + avoid one-frame re-appearance).
      try {
        const baseTransform = flyout.style.transform || "translateX(-50%)";
        flyout.style.willChange = "opacity, transform";
        flyout.style.transition =
          "opacity 180ms cubic-bezier(0.22, 1, 0.36, 1), transform 180ms cubic-bezier(0.22, 1, 0.36, 1)";

        // Apply end-state on next frame so the transition reliably runs.
        requestAnimationFrame(() => {
          try {
            flyout.style.opacity = "0";
            flyout.style.transform = `${baseTransform} translateY(-6px)`;
          } catch (e) {}
        });

        // Cleanup after the transition.
        setTimeout(cleanup, 220);
        return;
      } catch (e) {
        // If something goes wrong, fall back to immediate cleanup.
        cleanup();
        return;
      }
    }

    cleanup();
  }

  // Listen for open settings event from OKDEV-UI
  window.addEventListener("okdev-open-settings", (e) => {
    const navItem =
      e.detail?.navItem ||
      document.querySelector(
        "lol-uikit-navigation-item.menu_item_Golden.OKDEV"
      );
    if (navItem) {
      // Toggle: if panel is already open, close it
      if (settingsPanel && document.getElementById(PANEL_ID)) {
        closeSettingsPanel();
      } else {
        createSettingsFlyout(navItem);
      }
    } else {
      log(
        "warn",
        "Could not find Golden OKDEV nav item to position settings panel"
      );
    }
  });

  // Inject CSS
  function injectCSS() {
    // Remove existing CSS if it exists (to update with correct port)
    const existingStyle = document.getElementById("okdev-settings-panel-css");
    if (existingStyle) {
      existingStyle.remove();
    }

    const style = document.createElement("style");
    style.id = "okdev-settings-panel-css";
    style.textContent = getCSSRules();
    document.head.appendChild(style);
  }

  let _initializing = false;
  let _initialized = false;
  let _retryCount = 0;
  const MAX_RETRIES = 100; // Maximum number of retry attempts

  async function init() {
    // Prevent multiple concurrent initializations (but allow recursive retry)
    if (_initialized) {
      return;
    }
    // If already initializing, only proceed if this is a recursive retry call
    // (indicated by document being ready now when it wasn't before)
    if (_initializing) {
      // Allow recursive call to proceed only if document is now ready
      if (!document || !document.head) {
        // Check retry limit to prevent unbounded retries
        if (_retryCount >= MAX_RETRIES) {
          log("error", `Init failed: Maximum retry count (${MAX_RETRIES}) reached. Document still not ready.`);
          _initializing = false;
          _retryCount = 0; // Reset for next attempt
          return;
        }
        _retryCount++;
        // Still not ready, schedule another retry
        requestAnimationFrame(() => {
          init().catch(err => {
            log("error", "Init failed:", err);
            _initializing = false;
          });
        });
        return;
      }
      // Document is now ready, proceed with initialization
    } else {
      // First call - set flag BEFORE document check to prevent race condition
      _initializing = true;
      // Don't reset retry counter here - it should persist across retries
      // Only reset on successful initialization

      if (!document || !document.head) {
        // Check retry limit BEFORE incrementing to prevent unbounded retries
        if (_retryCount >= MAX_RETRIES) {
          log("error", `Init failed: Maximum retry count (${MAX_RETRIES}) reached. Document still not ready.`);
          _initializing = false;
          _retryCount = 0; // Reset for next attempt
          return;
        }
        _retryCount++;
        // Use synchronous wrapper to prevent multiple concurrent schedules
        requestAnimationFrame(() => {
          init().catch(err => {
            log("error", "Init failed:", err);
            _initializing = false;
          });
        });
        return;
      }
    }
    try {
      // Wait for the shared bridge to become available
      bridge = await waitForBridge();

      // Inject CSS after bridge is loaded (so it has the correct port number)
      injectCSS();

      // Subscribe to all message types
      bridge.subscribe("settings-data", handleSettingsData);
      bridge.subscribe("settings-saved", handleSettingsSaved);
      bridge.subscribe("diagnostics-data", handleDiagnosticsData);
      bridge.subscribe("diagnostics-cleared-category", () => requestDiagnostics());
      bridge.subscribe("diagnostics-cleared", () => requestDiagnostics());
      bridge.subscribe("phase-change", handleReconnectPhaseChange);
      bridge.subscribe("diagnostics-tracker-cleared", () => requestDiagnostics());
      bridge.subscribe("diagnostics-applied-recommended", () => requestDiagnostics());
      bridge.subscribe("path-validation-result", handlePathValidationResult);
      bridge.subscribe("champions-list-response", handleChampionsListResponse);
      bridge.subscribe("champion-skins-response", handleChampionSkinsResponse);
      bridge.subscribe("folder-opened-response", handleFolderOpenedResponse);
      bridge.subscribe("manage-champion-mods-response", handleManageSkinModsResponse);
      bridge.subscribe("manage-category-mods-response", handleManageCategoryModsResponse);
      bridge.subscribe("champion-mod-deleted", handleChampionModDeleted);
      bridge.subscribe("category-mod-deleted", handleCategoryModDeleted);
      bridge.subscribe("champion-mod-renamed", handleChampionModRenamed);
      bridge.subscribe("category-mod-renamed", handleCategoryModRenamed);

      // On every (re)connect, sync state
      bridge.onReady(() => {
        requestSettings();
        requestDiagnostics();
        startBadgeObserver();
        startReconnectObserver();

        // Poll diagnostics so warnings appear without opening the panel.
        if (!_diagnosticsPollId) {
          _diagnosticsPollId = setInterval(() => {
            try {
              if (!bridge || !bridge.ready) return;
              if (typeof document !== "undefined" && document.hidden) return;
              requestDiagnostics();
            } catch (e) {}
          }, 15000);
        }
      });

      log("info", "Settings panel plugin initialized");
      _initialized = true;
      _retryCount = 0; // Reset retry counter on success
    } catch (err) {
      log("error", "Init failed:", err);
      throw err; // Re-throw to propagate error to .catch() handlers
    } finally {
      _initializing = false;
    }
  }

  if (typeof document === "undefined") {
    log("warn", "document unavailable; aborting");
    return;
  }

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      () => {
        init().catch((err) => {
          log("error", "Init failed:", err);
        });
      },
      { once: true }
    );
  } else {
    init().catch((err) => {
      log("error", "Init failed:", err);
    });
  }
})();
