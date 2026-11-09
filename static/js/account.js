// Settings: the Deezer accounts. Each Navidrome profile reads its releases and
// Deezer mixes with one of them (the default one unless it chose another); one
// account, marked "Use for download", fetches the files for everyone. ARLs are
// only ever sent, never read back.

import { armed, escapeHtml, fetchJSON, on, toast } from './core.js';

const HELP = `
  <details class="account-help">
    <summary>Where do I find the ARL?</summary>
    <p>Log in to deezer.com in your browser, open the developer tools, then Application (Storage in Firefox) → Cookies → https://www.deezer.com, and copy the value of <code>arl</code>. It stays on this server, encrypted.</p>
  </details>
`;

function countryName(code) {
  try {
    return new Intl.DisplayNames(['en'], { type: 'region' }).of(code) || code;
  } catch (_) {
    return code;
  }
}

// Deezer serves the catalogue of the account's subscription country: what can
// be downloaded, and in which version, depends on it.
function countryBadge(code) {
  if (!code) return '';
  return `<span class="chip chip--info" title="Deezer serves the catalogue of this account's country (${escapeHtml(code)})">${escapeHtml(countryName(code))}</span>`;
}

// The badge says what an account can do: Premium or Free, and its country.
export function planBadge(status) {
  const plan = status.premium ? '<span class="chip chip--ok">Premium account</span>' : '<span class="chip">Free account</span>';
  return `${plan} ${countryBadge(status.country)}`;
}

const FORMAT_LABEL = { FLAC: 'FLAC', MP3_320: 'MP3 320', MP3_128: 'MP3 128' };

function downloadsNote(state) {
  const downloads = state.downloads || {};
  if (!downloads.account) return '<p class="muted">Add a Deezer account to download what is missing.</p>';
  if (!downloads.connected) {
    return `<p class="dz-warn">The downloads use ${escapeHtml(downloads.label)}, which cannot sign in: ${escapeHtml(downloads.error || 'check its ARL')}.</p>`;
  }
  const format = FORMAT_LABEL[downloads.format] || downloads.format || 'the best quality it allows';
  const free = downloads.premium ? '' : ' A free account only downloads MP3 128: mark a premium one with <b>Use for download</b> for FLAC.';
  return `<p class="muted">The downloads use <b>${escapeHtml(downloads.label)}</b>, in ${escapeHtml(format)}, for every profile.${free}</p>`;
}

function accountRow(account, state) {
  const only = state.accounts.length === 1;
  // Until a first check, Deezer has not said what the account is: no plan badge.
  let status = account.checked_at ? planBadge(account) : '';
  if (account.error) status = `<span class="chip chip--miss" title="${escapeHtml(account.error)}">Cannot sign in</span>`;
  let who = account.checked_at ? '' : 'Not checked yet';
  if (account.name) who = `Deezer user ${escapeHtml(account.name)}`;
  const env = account.from_env
    ? `<p class="muted">Set by the ${escapeHtml(account.from_env)} environment variable: change the ARL there.</p>` : '';
  const error = account.error ? `<p class="dz-warn">${escapeHtml(account.error)}</p>` : '';
  return `
    <div class="nd-account" data-dz-id="${escapeHtml(account.id)}">
      <div class="nd-account-main">
        <strong>${escapeHtml(account.label)}</strong>
        ${who ? `<span class="muted">${who}</span>` : ''}
        <div class="chips">
          ${account.is_default ? '<span class="chip chip--ok">Default</span>' : ''}
          ${account.is_download ? '<span class="chip chip--partial" title="It fetches the files for every profile">Downloads</span>' : ''}
          ${status}
        </div>
        ${env}${error}
      </div>
      <div class="nd-account-actions">
        <button type="button" class="btn btn--ghost btn--sm" data-dz-check>Check</button>
        <button type="button" class="btn btn--ghost btn--sm" data-dz-edit>Edit</button>
        ${account.is_default ? '' : '<button type="button" class="btn btn--ghost btn--sm" data-dz-default>Make default</button>'}
        ${account.is_download ? '' : '<button type="button" class="btn btn--ghost btn--sm" data-dz-download>Use for download</button>'}
        ${only ? '' : '<button type="button" class="btn btn--danger btn--sm" data-dz-delete>Remove</button>'}
      </div>
    </div>`;
}

function formHtml(account) {
  const editing = Boolean(account);
  const fromEnv = Boolean(account?.from_env);
  return `
    <form class="nd-form" data-dz-form ${editing ? `data-dz-form-id="${escapeHtml(account.id)}"` : ''}>
      <h3>${editing ? `Edit ${escapeHtml(account.label)}` : 'New Deezer account'}</h3>
      <div class="nd-form-grid">
        <label class="form-field">
          <span>Name</span>
          <input type="text" name="label" maxlength="40" value="${escapeHtml(account?.label || '')}" placeholder="Shown in the lists, e.g. Alice" autocomplete="off">
        </label>
        ${fromEnv ? '' : `
        <label class="form-field">
          <span>ARL</span>
          <input type="password" name="arl" autocomplete="off" spellcheck="false" ${editing ? 'placeholder="Leave empty to keep the saved one"' : 'placeholder="Paste the arl cookie value" required'}>
          <small>Checked by signing in, then kept encrypted. Never shown again.</small>
        </label>`}
      </div>
      ${HELP}
      <div class="button-row">
        <button type="submit" class="btn btn--sm">${editing ? 'Save' : 'Add the account'}</button>
        <button type="button" class="btn btn--ghost btn--sm" data-dz-cancel>Cancel</button>
      </div>
    </form>`;
}

export async function initAccount() {
  const root = document.querySelector('[data-account]');
  if (!root) return;
  const cell = root.closest('section');
  let state = null;
  let editing = null; // null: no form, '': new account, 'dz2': that account

  function render() {
    const form = editing === null ? '' : formHtml(editing ? state.accounts.find(a => a.id === editing) : null);
    const list = state.accounts.length
      ? `<div class="nd-accounts">${state.accounts.map(a => accountRow(a, state)).join('')}</div>`
      : '<p class="muted">No Deezer account yet. Add one to download, and to follow the releases and mixes of your favorite artists.</p>';
    root.innerHTML = `${list}${form}<div class="nd-footer">${downloadsNote(state)}</div>`;
    root.querySelector('[data-dz-form] input[name="label"]')?.focus();
  }

  async function load() {
    const { ok, data } = await fetchJSON('/api/deezer/accounts');
    if (!ok) {
      root.innerHTML = `<p class="dz-warn">${escapeHtml(data?.error || 'Could not load the Deezer accounts.')}</p>`;
      return;
    }
    state = data;
    render();
  }

  async function send(url, options, message) {
    const { ok, data } = await fetchJSON(url, options);
    if (!ok) {
      toast(data?.error || 'That did not work', { tone: 'error' });
      return false;
    }
    await load();
    if (message) toast(message);
    return true;
  }

  cell.addEventListener('click', event => {
    if (event.target.closest('[data-dz-add]') && state) {
      editing = '';
      render();
    }
  });
  on(root, 'click', '[data-dz-cancel]', () => {
    editing = null;
    render();
  });
  on(root, 'click', '[data-dz-edit]', (_, button) => {
    editing = button.closest('[data-dz-id]').dataset.dzId;
    render();
  });
  on(root, 'submit', '[data-dz-form]', async (event, form) => {
    event.preventDefault();
    const id = form.dataset.dzFormId;
    const values = Object.fromEntries(new FormData(form));
    if (!values.arl) delete values.arl;
    const submit = form.querySelector('button[type="submit"]');
    submit.disabled = true;
    submit.textContent = 'Checking…';
    const done = await send(id ? `/api/deezer/accounts/${encodeURIComponent(id)}` : '/api/deezer/accounts',
      { method: id ? 'PATCH' : 'POST', json: values }, id ? 'Deezer account saved' : 'Deezer account added');
    if (done) {
      editing = null;
      render();
    } else {
      submit.disabled = false;
      submit.textContent = id ? 'Save' : 'Add the account';
    }
  });
  on(root, 'click', '[data-dz-check]', (_, button) => {
    button.disabled = true;
    const id = button.closest('[data-dz-id]').dataset.dzId;
    send(`/api/deezer/accounts/${encodeURIComponent(id)}/check`, { method: 'POST' }, 'Checked');
  });
  on(root, 'click', '[data-dz-default]', (_, button) => {
    const id = button.closest('[data-dz-id]').dataset.dzId;
    send(`/api/deezer/accounts/${encodeURIComponent(id)}/default`, { method: 'POST' }, 'Default Deezer account changed');
  });
  on(root, 'click', '[data-dz-download]', (_, button) => {
    const id = button.closest('[data-dz-id]').dataset.dzId;
    send(`/api/deezer/accounts/${encodeURIComponent(id)}/download`, { method: 'POST' }, 'The downloads now use this account');
  });
  on(root, 'click', '[data-dz-delete]', (_, button) => {
    const row = button.closest('[data-dz-id]');
    const account = state.accounts.find(a => a.id === row.dataset.dzId);
    if (!armed(button, `Click again to remove ${account.label}`)) return;
    send(`/api/deezer/accounts/${encodeURIComponent(account.id)}`, { method: 'DELETE' }, `${account.label} removed`);
  });

  load();
}
