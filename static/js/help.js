// Help window: what changed in this version, with live checks of the setup,
// and a short guide. It opens on its own once after an upgrade; closing it
// tells the server, so it does not come back. The Help button reopens it.

import { escapeHtml, fetchJSON, on } from './core.js';
import { planBadge } from './account.js';

function showTab(modal, name) {
  modal.el.querySelectorAll('[data-help-tab]').forEach(btn => {
    btn.setAttribute('aria-pressed', String(btn.dataset.helpTab === name));
  });
  modal.el.querySelectorAll('[data-help-panel]').forEach(panel => {
    panel.hidden = panel.dataset.helpPanel !== name;
  });
}

async function checkAccount(modal) {
  const step = modal.el.querySelector('[data-help-account]');
  const line = step.querySelector('[data-help-account-status]');
  const dot = step.querySelector('.dot');
  const { ok, data } = await fetchJSON('/api/deezer/account');
  const connected = ok && data?.connected;
  dot.className = `dot ${connected ? 'dot--ok' : 'dot--miss'}`;
  line.classList.toggle('help-live--warn', !connected);
  if (connected) {
    line.innerHTML = `Connected as <b>${escapeHtml(data.name)}</b> ${planBadge(data)}`;
  } else {
    line.textContent = data?.error ? `Not connected: ${data.error}` : 'Not connected yet.';
  }
}

export function initHelp(modal) {
  const auto = modal.el.dataset.autoOpen === 'true';
  let markSeen = auto;

  function open(tab = 'new') {
    showTab(modal, tab);
    modal.open({
      closeHandler() {
        if (!markSeen) return;
        markSeen = false;
        fetchJSON('/api/whats-new/seen', { json: {} });
      },
    });
    checkAccount(modal);
  }

  on(modal.el, 'click', '[data-help-tab]', (_, btn) => showTab(modal, btn.dataset.helpTab));
  // The view switch happens behind the window: close it first.
  on(modal.el, 'click', '[data-help-settings]', () => modal.close());
  on(document, 'click', '[data-action="help"]', () => open());

  if (auto) open('new');
}
