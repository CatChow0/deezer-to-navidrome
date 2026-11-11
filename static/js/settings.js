// Settings view: its spaces (General, Accounts, Stats and sign-in, Users),
// the mappings editor, saving without leaving the page, the two-click
// confirmation on reset buttons, and the clears of your own profiles.

import { armed, escapeHtml, fetchJSON, on, toast } from './core.js';
import { setSubject, subject } from './subject.js';

const SPACES = ['general', 'accounts', 'stats', 'users'];

function initSpaces() {
  const tabs = document.querySelector('[data-settings-tabs]');
  if (!tabs) return;
  const show = name => {
    if (!tabs.querySelector(`[data-space-tab="${name}"]`)) name = tabs.querySelector('[data-space-tab]').dataset.spaceTab;
    tabs.querySelectorAll('[data-space-tab]').forEach(tab => tab.setAttribute('aria-pressed', String(tab.dataset.spaceTab === name)));
    document.querySelectorAll('[data-space]').forEach(part => { part.hidden = part.dataset.space !== name; });
  };
  on(tabs, 'click', '[data-space-tab]', (_, tab) => {
    show(tab.dataset.spaceTab);
    history.replaceState(history.state, '', `#settings/${tab.dataset.spaceTab}`);
  });
  const asked = location.hash.match(/^#settings\/(\w+)/)?.[1];
  show(SPACES.includes(asked) ? asked : '');
}

async function initSubject() {
  const select = document.querySelector('[data-subject]');
  if (!select) return;
  const { ok, data } = await fetchJSON('/api/users');
  if (!ok) return;
  select.innerHTML = data.users.filter(u => u.can.edit).map(u =>
    `<option value="${u.id === data.me ? '' : escapeHtml(u.id)}">${u.id === data.me ? 'You' : escapeHtml(u.username)}</option>`).join('');
  select.addEventListener('change', () => setSubject(select.value));
  document.addEventListener('d2n:subject', () => { select.value = subject(); });
}

function initProfileClears() {
  on(document, 'click', '[data-profile-clear]', async (_, button) => {
    if (!armed(button, 'Click again to confirm')) return;
    const { ok, data } = await fetchJSON(`/api/profiles/clear/${button.dataset.profileClear}`, { method: 'POST' });
    if (!ok) return toast(data?.error || 'That did not work', { tone: 'error' });
    toast(`${data.cleared} playlist${data.cleared === 1 ? '' : 's'} cleared`, { tone: 'ok' });
  });
}

export function initSettings() {
  initSpaces();
  initSubject();
  initProfileClears();
  const form = document.getElementById('settings-form');
  if (!form) return;

  const mappings = document.getElementById('mappings');
  const template = document.getElementById('mapping-template');
  const saveBar = form.querySelector('[data-save-bar]');
  const showSaveBar = () => {
    saveBar.hidden = false;
  };

  form.addEventListener('input', showSaveBar);
  form.addEventListener('change', showSaveBar);

  on(form, 'click', '[data-action="add-mapping"]', () => {
    mappings.appendChild(template.content.cloneNode(true));
    mappings.lastElementChild.querySelector('input')?.focus();
    showSaveBar();
  });

  on(form, 'click', '[data-action="remove-mapping"]', (_, btn) => {
    btn.closest('.mapping-row')?.remove();
    showSaveBar();
  });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    button.textContent = 'Saving…';

    try {
      const resp = await fetch(form.action, { method: 'POST', body: new FormData(form) });
      if (!resp.ok) {
        const data = await resp.json().catch(() => null);
        throw new Error(data?.error || `HTTP ${resp.status}`);
      }
      toast('Settings saved', { tone: 'ok' });
      saveBar.hidden = true;
    } catch (err) {
      toast(`Settings were not saved: ${err.message}`, { tone: 'error' });
    } finally {
      button.disabled = false;
      button.textContent = 'Save settings';
    }
  });

  // Reset buttons still submit normally: the page reloads on Settings with the
  // result, and the background carries over thanks to the session.
  document.querySelectorAll('[data-confirm-form]').forEach(resetForm => {
    resetForm.addEventListener('submit', event => {
      if (!armed(resetForm.querySelector('button'), resetForm.dataset.confirmForm)) event.preventDefault();
    });
  });
}
