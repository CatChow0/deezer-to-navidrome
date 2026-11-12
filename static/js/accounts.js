// Navidrome accounts: the picker at the top of the page (this browser's
// account) and the list in Settings. Passwords and API keys are only ever
// sent, never read back: the server says whether one is saved.

import { armed, escapeHtml, fetchJSON, on, toast } from './core.js';
import { runServerTask } from './activity.js';
import { scoped } from './subject.js';
import { showView } from './views.js';

const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;

function when(seconds) {
  if (!seconds) return '';
  return new Date(seconds * 1000).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

function testSummary(test) {
  if (!test) return '';
  if (!test.ok) return `<p class="nd-warn">${escapeHtml(test.error || 'The test failed.')}</p>`;
  const libraries = (test.libraries || []).map(l => l.name).filter(Boolean);
  const facts = [
    test.server_version ? `Navidrome ${escapeHtml(test.server_version)}` : '',
    test.admin === true ? 'admin' : test.admin === false ? 'not an admin' : '',
    libraries.length ? `sees ${escapeHtml(libraries.join(', '))}` : '',
    test.api_keys ? 'API keys accepted' : 'no API keys, so the password is used',
  ].filter(Boolean);
  const user = test.navidrome_user
    ? `<p class="muted">Found in Navidrome's database as <b>${escapeHtml(test.navidrome_user)}</b>: its plays and stars can be told apart.</p>`
    : '';
  const warning = test.warning ? `<p class="nd-warn">${escapeHtml(test.warning)}</p>` : '';
  return `<p class="nd-test-ok"><span class="dot dot--ok"></span>Connected: ${facts.join(' · ')}.</p>${user}${warning}`;
}

function statusChip(account) {
  if (!account.complete) return '<span class="chip chip--partial">Address or password missing</span>';
  const test = account.last_test;
  if (!test) return '<span class="chip">Not tested yet</span>';
  return test.ok
    ? `<span class="chip chip--ok" title="Tested ${escapeHtml(when(test.at))}">Connected</span>`
    : `<span class="chip chip--miss" title="${escapeHtml(test.error || '')}">Connection failed</span>`;
}

function ago(seconds) {
  const minutes = Math.round((Date.now() / 1000 - seconds) / 60);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)} h ago`;
  return when(seconds);
}

function syncLine(account) {
  const sync = account.sync;
  if (!sync) return '';
  if (sync.error) return `<p class="nd-warn">Last sync with Navidrome failed: ${escapeHtml(sync.error)}</p>`;
  const parts = [`Synced with Navidrome ${ago(sync.at)}`];
  if (sync.removed?.length) parts.push(`${plural(sync.removed.length, 'playlist')} removed, deleted in Navidrome (${sync.removed.map(escapeHtml).join(', ')})`);
  if (sync.renamed) parts.push(`${plural(sync.renamed, 'playlist')} renamed there`);
  if (sync.handmade) parts.push(`${sync.handmade} made by hand`);
  const warning = sync.warning ? `<p class="nd-warn">${escapeHtml(sync.warning)}</p>` : '';
  return `<p class="muted">${parts.join(' · ')}</p>${warning}`;
}

function deezerLabel(state, id) {
  const deezer = state.deezer?.accounts || [];
  if (!id) {
    const fallback = deezer.find(d => d.is_default);
    return fallback ? `${fallback.label} (default)` : '';
  }
  return deezer.find(d => d.id === id)?.label || '';
}

function accountRow(account, state) {
  const deezer = deezerLabel(state, account.deezer_account);
  const where = [account.username, account.url].filter(Boolean).map(escapeHtml).join(' · ') || 'No address or user yet';
  const mode = account.publish_mode === 'm3u8'
    ? '<span class="chip chip--info" title="Navidrome imports the .m3u8 files: they belong to its first admin">Playlists as .m3u8 files</span>'
    : '<span class="chip chip--info" title="Published as this Navidrome user">Playlists as this user</span>';
  const legacy = account.legacy && !account.complete
    ? '<p class="muted">Made from your install: it keeps working as before. Add its address and password to get ready for per-user playlists.</p>'
    : '';
  const only = state.accounts.length === 1;
  return `
    <div class="nd-account" data-nd-id="${escapeHtml(account.id)}">
      <div class="nd-account-main">
        <strong>${escapeHtml(account.label)}</strong>
        <span class="muted">${where}</span>
        <div class="chips">
          ${account.is_default ? '<span class="chip chip--ok">Default</span>' : ''}
          ${account.id === state.active ? '<span class="chip">This browser</span>' : ''}
          ${statusChip(account)}
          ${mode}
          ${deezer ? `<span class="chip" title="Its releases and Deezer mixes">Deezer: ${escapeHtml(deezer)}</span>` : ''}
        </div>
        ${legacy}
        ${syncLine(account)}
      </div>
      <div class="nd-account-actions">
        ${account.publish_mode === 'm3u8' && account.complete && account.last_test?.ok
          ? '<button type="button" class="btn btn--sm" data-nd-switch title="Its playlists become this user\'s own, through Navidrome\'s API">Publish as this user…</button>' : ''}
        ${account.complete ? '<button type="button" class="btn btn--ghost btn--sm" data-nd-test>Test</button>' : ''}
        <button type="button" class="btn btn--ghost btn--sm" data-nd-edit>Edit</button>
        ${account.is_default ? '' : '<button type="button" class="btn btn--ghost btn--sm" data-nd-default>Make default</button>'}
        ${only ? '' : '<button type="button" class="btn btn--danger btn--sm" data-nd-delete>Remove</button>'}
      </div>
      <div class="nd-account-test" data-nd-test-result></div>
    </div>`;
}

function deezerSelect(state, account) {
  const deezer = state.deezer?.accounts || [];
  if (!deezer.length) return '';
  const chosen = account?.deezer_account || '';
  const fallback = deezer.find(d => d.is_default);
  const options = [`<option value="" ${chosen ? '' : 'selected'}>Default${fallback ? ` (${escapeHtml(fallback.label)})` : ''}</option>`,
    ...deezer.map(d => `<option value="${escapeHtml(d.id)}" ${d.id === chosen ? 'selected' : ''}>${escapeHtml(d.label)}</option>`)];
  return `
        <label class="form-field">
          <span>Deezer account</span>
          <select name="deezer_account">${options.join('')}</select>
          <small>Its releases and Deezer mixes. The downloads always use the account marked for them.</small>
        </label>`;
}

function formHtml(account, state) {
  const editing = Boolean(account);
  const value = name => escapeHtml(account?.[name] || '');
  const apikey = account?.auth_type === 'apikey';
  return `
    <form class="nd-form" data-nd-form ${editing ? `data-nd-form-id="${escapeHtml(account.id)}"` : ''}>
      <h3>${editing ? `Edit ${escapeHtml(account.label)}` : 'New Navidrome account'}</h3>
      <div class="nd-form-grid">
        <label class="form-field">
          <span>Name</span>
          <input type="text" name="label" maxlength="40" value="${value('label')}" placeholder="Shown in the picker, e.g. Alice" autocomplete="off">
        </label>
        <label class="form-field">
          <span>Navidrome address</span>
          <input type="url" name="url" class="mono" value="${value('url')}" placeholder="http://navidrome:4533" autocomplete="off" spellcheck="false" ${editing ? '' : 'required'}>
          <small>The address this server reaches Navidrome at, like ND_LISTENBRAINZ_BASEURL the other way round.</small>
        </label>
        <label class="form-field">
          <span>Navidrome user name</span>
          <input type="text" name="username" value="${value('username')}" autocomplete="off" spellcheck="false" ${editing ? '' : 'required'}>
        </label>
        <label class="form-field">
          <span>Sign in with</span>
          <select name="auth_type">
            <option value="password" ${apikey ? '' : 'selected'}>Password</option>
            <option value="apikey" ${apikey ? 'selected' : ''}>API key (if your Navidrome accepts them)</option>
          </select>
        </label>
        <label class="form-field nd-form-secret">
          <span data-nd-secret-label>${apikey ? 'API key' : 'Password'}</span>
          <input type="password" name="secret" autocomplete="new-password" spellcheck="false" ${editing ? '' : 'required'}
                 placeholder="${editing && account.has_secret ? 'Leave empty to keep the saved one' : ''}">
          <small>Kept encrypted on this server. Never shown again, and never written in a log.</small>
        </label>
        ${deezerSelect(state, account)}
      </div>
      <div class="nd-form-test" data-nd-form-test></div>
      <div class="button-row">
        <button type="button" class="btn btn--ghost btn--sm" data-nd-form-test-btn>Test the connection</button>
        <button type="submit" class="btn btn--sm">${editing ? 'Save' : 'Add the account'}</button>
        <button type="button" class="btn btn--ghost btn--sm" data-nd-cancel>Cancel</button>
      </div>
    </form>`;
}

function switchHtml(account, preview) {
  if (!preview.ok) return `<p class="nd-warn">${preview.problems.map(escapeHtml).join(' ')}</p>`;
  const old = preview.old.length
    ? `<li>The ${preview.old.length === 1 ? 'copy' : `${preview.old.length} copies`} Navidrome imported from them ${preview.old.length === 1 ? 'is' : 'are'} removed from Navidrome: ${preview.old.map(p => escapeHtml(p.name)).join(', ')}.</li>`
    : '';
  const unknown = preview.database ? '' : '<li>Navidrome\'s database is not mounted, so the old copies imported from the files cannot be found: remove them in Navidrome afterwards.</li>';
  const owner = preview.can_remove_old ? '' : '<p class="nd-warn">This user is not an admin and does not own the old copies: remove them in Navidrome afterwards.</p>';
  return `
    <div class="nd-switch" data-nd-switch-panel>
      <p>The ${plural(preview.playlists, 'playlist')} of ${escapeHtml(account.label)} become private playlists of <b>${escapeHtml(account.username)}</b>, made and kept up to date through Navidrome's API.</p>
      <ul>
        <li>${plural(preview.files, '.m3u8 file')} written by this app ${preview.files === 1 ? 'is' : 'are'} removed from the playlists folder, so Navidrome does not import ${preview.files === 1 ? 'it' : 'them'} again.</li>
        ${old}${unknown}
      </ul>
      ${owner}
      <p class="muted">If Navidrome refuses a playlist, what was made is undone and nothing changes.</p>
      <div class="button-row">
        <button type="button" class="btn btn--sm" data-nd-switch-go>Switch now</button>
        <button type="button" class="btn btn--ghost btn--sm" data-nd-switch-cancel>Cancel</button>
      </div>
    </div>`;
}

function footerHtml(state) {
  const key = state.encryption.source === 'env'
    ? '<p class="muted">Passwords and API keys are encrypted with your D2N_ENCRYPTION_KEY.</p>'
    : '<p class="muted">Passwords and API keys are encrypted with a key kept in /data/encryption.key. Set D2N_ENCRYPTION_KEY to keep the key out of the data folder, so a copy of it reveals nothing.</p>';
  const db = state.navidrome_db.mounted
    ? `<p class="muted">Navidrome's database is mounted: ${plural(state.navidrome_db.users.length, 'user')} found (${state.navidrome_db.users.map(escapeHtml).join(', ')}).</p>`
    : '<p class="muted">Navidrome\'s database is not mounted at /import/navidrome: telling each user\'s plays and stars apart will need it.</p>';
  return `<div class="nd-footer">${key}${db}</div>`;
}

export function initNavidromeAccounts() {
  const picker = document.querySelector('[data-nd-account]');
  if (picker) {
    const chosen = picker.value;
    picker.addEventListener('change', async () => {
      const option = picker.selectedOptions[0];
      if (option?.hasAttribute('data-nd-manage')) {
        picker.value = chosen;
        showView('settings');
        document.getElementById('navidrome-accounts')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        return;
      }
      picker.disabled = true;
      const { ok, data } = await fetchJSON('/api/navidrome/active', { json: { id: picker.value } });
      if (!ok) {
        picker.disabled = false;
        picker.value = chosen;
        toast(data?.error || 'Could not change the account', { tone: 'error' });
        return;
      }
      window.location.reload();
    });
  }

  const root = document.querySelector('[data-nd-accounts]');
  if (!root) return;
  const cell = root.closest('section');
  let state = null;
  let editing = null; // null: no form, '': new account, 'nd2': that account

  function render() {
    const form = editing === null ? '' : formHtml(editing ? state.accounts.find(a => a.id === editing) : null, state);
    root.innerHTML = `
      <div class="nd-accounts">${state.accounts.map(a => accountRow(a, state)).join('')}</div>
      ${form}
      ${footerHtml(state)}`;
    root.querySelector('[data-nd-form] input[name="url"], [data-nd-form] input[name="label"]')?.focus();
  }

  async function load() {
    const [{ ok, data }, deezer] = await Promise.all([fetchJSON(scoped('/api/navidrome/accounts')),
      fetchJSON(scoped('/api/deezer/accounts'))]);
    if (!ok) {
      root.innerHTML = `<p class="nd-warn">${escapeHtml(data?.error || 'Could not load the accounts.')}</p>`;
      return;
    }
    state = { ...data, deezer: deezer.ok ? deezer.data : null };
    render();
  }

  // Editing, a field left empty that was empty already is not sent: the account
  // made from the install can choose its Deezer account before its address.
  function formValues(form) {
    const values = Object.fromEntries(new FormData(form));
    if (!values.secret) delete values.secret;
    const saved = state.accounts.find(a => a.id === form.dataset.ndFormId);
    if (saved) {
      for (const key of ['url', 'username']) {
        if (!values[key] && !saved[key]) delete values[key];
      }
    }
    return values;
  }

  async function send(url, options, done) {
    const { ok, data } = await fetchJSON(scoped(url), options);
    if (!ok) {
      toast(data?.error || 'That did not work', { tone: 'error' });
      return null;
    }
    if (data.accounts) state = { ...data, deezer: state?.deezer || null };
    if (done) done(data);
    return data;
  }

  cell.addEventListener('click', event => {
    if (event.target.closest('[data-nd-add]') && state) {
      editing = '';
      render();
    }
  });
  on(root, 'click', '[data-nd-cancel]', () => {
    editing = null;
    render();
  });
  on(root, 'click', '[data-nd-edit]', (_, button) => {
    editing = button.closest('[data-nd-id]').dataset.ndId;
    render();
  });
  on(root, 'change', '[data-nd-form] select[name="auth_type"]', (_, select) => {
    root.querySelector('[data-nd-secret-label]').textContent = select.value === 'apikey' ? 'API key' : 'Password';
  });
  on(root, 'click', '[data-nd-form-test-btn]', async (_, button) => {
    const form = button.closest('form');
    const out = form.querySelector('[data-nd-form-test]');
    button.disabled = true;
    out.innerHTML = '<p class="muted">Testing…</p>';
    const body = { ...formValues(form), id: form.dataset.ndFormId || '' };
    const { ok, data } = await fetchJSON(scoped('/api/navidrome/accounts/test'), { json: body });
    button.disabled = false;
    out.innerHTML = ok ? testSummary(data.test) : `<p class="nd-warn">${escapeHtml(data?.error || 'The test failed.')}</p>`;
  });
  on(root, 'submit', '[data-nd-form]', async (event, form) => {
    event.preventDefault();
    const id = form.dataset.ndFormId;
    const submit = form.querySelector('button[type="submit"]');
    submit.disabled = true;
    const done = await send(id ? `/api/navidrome/accounts/${encodeURIComponent(id)}` : '/api/navidrome/accounts',
      { method: id ? 'PATCH' : 'POST', json: formValues(form) });
    submit.disabled = false;
    if (!done) return;
    editing = null;
    render();
    toast(id ? 'Account saved' : 'Account added');
    const saved = id || done.created;
    if (saved) root.querySelector(`[data-nd-id="${saved}"] [data-nd-test]`)?.click();
  });
  on(root, 'click', '[data-nd-test]', async (_, button) => {
    const row = button.closest('[data-nd-id]');
    const out = row.querySelector('[data-nd-test-result]');
    button.disabled = true;
    out.innerHTML = '<p class="muted">Testing…</p>';
    const { ok, data } = await fetchJSON(scoped(`/api/navidrome/accounts/${encodeURIComponent(row.dataset.ndId)}/test`), { method: 'POST' });
    button.disabled = false;
    if (!ok) {
      out.innerHTML = `<p class="nd-warn">${escapeHtml(data?.error || 'The test failed.')}</p>`;
      return;
    }
    state = { ...data, deezer: state?.deezer || null };
    const id = row.dataset.ndId;
    render();
    root.querySelector(`[data-nd-id="${id}"] [data-nd-test-result]`).innerHTML = testSummary(data.test);
  });
  on(root, 'click', '[data-nd-switch]', async (_, button) => {
    const row = button.closest('[data-nd-id]');
    const account = state.accounts.find(a => a.id === row.dataset.ndId);
    const out = row.querySelector('[data-nd-test-result]');
    button.disabled = true;
    out.innerHTML = '<p class="muted">Looking at what would change…</p>';
    const { ok, data } = await fetchJSON(scoped(`/api/navidrome/accounts/${encodeURIComponent(account.id)}/switch`));
    button.disabled = false;
    out.innerHTML = ok ? switchHtml(account, data.preview) : `<p class="nd-warn">${escapeHtml(data?.error || 'That did not work')}</p>`;
  });
  on(root, 'click', '[data-nd-switch-cancel]', (_, button) => {
    button.closest('[data-nd-test-result]').innerHTML = '';
  });
  on(root, 'click', '[data-nd-switch-go]', async (_, button) => {
    const row = button.closest('[data-nd-id]');
    const account = state.accounts.find(a => a.id === row.dataset.ndId);
    if (!armed(button, 'Click again to switch')) return;
    button.disabled = true;
    const result = await runServerTask(`Playlists as ${account.label}`, scoped(`/api/navidrome/accounts/${encodeURIComponent(account.id)}/switch`));
    await load();
    if (!result?.error) toast(`${account.label}: playlists published as ${account.username}`);
  });
  on(root, 'click', '[data-nd-default]', (_, button) => {
    const id = button.closest('[data-nd-id]').dataset.ndId;
    send(`/api/navidrome/accounts/${encodeURIComponent(id)}/default`, { method: 'POST' }, () => render());
  });
  on(root, 'click', '[data-nd-delete]', (_, button) => {
    const row = button.closest('[data-nd-id]');
    const account = state.accounts.find(a => a.id === row.dataset.ndId);
    if (!armed(button, `Click again to remove ${account.label}`)) return;
    send(`/api/navidrome/accounts/${encodeURIComponent(account.id)}`, { method: 'DELETE' }, () => {
      render();
      toast(`${account.label} removed`);
      if (picker) window.location.reload();
    });
  });
  document.addEventListener('d2n:subject', () => {
    editing = null;
    load();
  });

  load();
}
