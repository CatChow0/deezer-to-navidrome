// Settings → Users (Admins): the accounts of this app. What each button may do
// comes from the server (core/users.can), which checks it again.

import { armed, escapeHtml, fetchJSON, on, toast } from './core.js';
import { setSubject } from './subject.js';

const ROLE = { superadmin: 'Super-Admin', admin: 'Admin', standard: 'Standard' };
const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;

function editHtml(user, me) {
  const roles = user.role === 'superadmin' || !(user.can.promote || user.can.demote) ? ''
    : `<label class="form-field"><span>Privilege</span><select name="role">
        ${['standard', 'admin'].map(r => `<option value="${r}" ${user.role === r ? 'selected' : ''}>${ROLE[r]}</option>`).join('')}
      </select></label>`;
  const others = user.id === me ? '' : `
      <label class="form-field"><span>Temporary password</span>
        <input type="password" name="password" minlength="8" autocomplete="new-password" placeholder="Leave empty to keep it">
        <small>They choose their own at the next sign-in; their devices are signed out.</small></label>`;
  return `
    <form class="nd-form" data-user-form>
      <div class="nd-form-grid">
        <label class="form-field"><span>Username</span>
          <input type="text" name="username" required value="${escapeHtml(user.username)}" ${user.from_env ? 'disabled' : ''}></label>
        ${roles}${user.from_env ? '' : others}
      </div>
      <div class="button-row">
        <button type="submit" class="btn btn--sm">Save</button>
        ${user.id === me ? '' : '<button type="button" class="btn btn--ghost btn--sm" data-user-recovery>Make a recovery code</button>'}
        <button type="button" class="btn btn--ghost btn--sm" data-user-accounts>Manage their accounts</button>
        <button type="button" class="btn btn--ghost btn--sm" data-user-cancel>Cancel</button>
      </div>
      <p class="login-code" data-user-code hidden><code></code></p>
    </form>`;
}

function deleteHtml(user, users) {
  const heirs = users.filter(u => u.id !== user.id);
  return `
    <form class="nd-form" data-user-delete-form>
      <p>Their ${plural(user.navidrome_accounts, 'Navidrome account')} and ${plural(user.deezer_accounts, 'Deezer account')}:</p>
      <label class="toggle"><input type="radio" name="keep" value="give" checked> Give them to
        <select name="heir">${heirs.map(u => `<option value="${escapeHtml(u.id)}">${escapeHtml(u.username)}</option>`).join('')}</select></label>
      <label class="toggle"><input type="radio" name="keep" value="remove"> Remove them, with their playlists</label>
      <div class="button-row">
        <button type="submit" class="btn btn--danger btn--sm">Remove ${escapeHtml(user.username)}</button>
        <button type="button" class="btn btn--ghost btn--sm" data-user-cancel>Cancel</button>
      </div>
    </form>`;
}

function newHtml() {
  return `
    <form class="nd-form" data-user-new-form>
      <h3>New account</h3>
      <div class="nd-form-grid">
        <label class="form-field"><span>Username</span><input type="text" name="username" required autocomplete="off"></label>
        <label class="form-field"><span>Temporary password</span>
          <input type="password" name="password" minlength="8" required autocomplete="new-password">
          <small>Give it to them: they choose their own at the first sign-in.</small></label>
        <label class="form-field"><span>Privilege</span><select name="role">
          <option value="standard">Standard</option><option value="admin">Admin</option></select></label>
      </div>
      <div class="button-row">
        <button type="submit" class="btn btn--sm">Add the account</button>
        <button type="button" class="btn btn--ghost btn--sm" data-user-cancel>Cancel</button>
      </div>
    </form>`;
}

export function initUsers() {
  const root = document.querySelector('[data-users]');
  if (!root) return;
  let state = null;
  let open = null; // {id, mode: 'edit'|'delete'} or {mode: 'new'}

  function render() {
    const rows = state.users.map(user => `
      <tr data-user-id="${escapeHtml(user.id)}">
        <td><strong>${escapeHtml(user.username)}</strong>${user.id === state.me ? ' <span class="muted">(you)</span>' : ''}
          ${user.must_change ? '<span class="chip chip--partial">Must choose a password</span>' : ''}</td>
        <td>${ROLE[user.role]}</td>
        <td class="muted">${plural(user.navidrome_accounts, 'Navidrome')} · ${plural(user.deezer_accounts, 'Deezer')}</td>
        <td class="actions">
          <button type="button" class="btn btn--ghost btn--sm" data-user-edit ${user.can.edit ? '' : 'disabled'}>Edit</button>
          <button type="button" class="btn btn--danger btn--sm" data-user-delete ${user.can.delete ? '' : 'disabled'}>Delete</button>
        </td>
      </tr>
      ${open?.id === user.id ? `<tr><td colspan="4">${open.mode === 'edit' ? editHtml(user, state.me) : deleteHtml(user, state.users)}</td></tr>` : ''}`).join('');
    root.innerHTML = `
      <div class="table-wrap"><table class="table">
        <thead><tr><th>Username</th><th>Privilege</th><th>Accounts</th><th class="actions"></th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
      ${open?.mode === 'new' ? newHtml() : ''}`;
  }

  async function send(url, options, message) {
    const { ok, data } = await fetchJSON(url, options);
    if (!ok) {
      toast(data?.error || 'That did not work', { tone: 'error' });
      return null;
    }
    if (data.users) {
      state = data;
      open = null;
      render();
    }
    if (message) toast(message, { tone: 'ok' });
    return data;
  }

  // Its forms are only ever shown for the open account.
  const userOf = () => state.users.find(u => u.id === open?.id);

  document.querySelector('[data-user-add]')?.addEventListener('click', () => {
    open = { mode: 'new' };
    render();
  });
  on(root, 'click', '[data-user-cancel]', () => {
    open = null;
    render();
  });
  on(root, 'click', '[data-user-edit], [data-user-delete]', (_, button) => {
    open = { id: button.closest('[data-user-id]').dataset.userId, mode: button.matches('[data-user-edit]') ? 'edit' : 'delete' };
    render();
  });
  on(root, 'click', '[data-user-accounts]', (_, button) => {
    setSubject(userOf().id);
    document.querySelector('[data-space-tab="accounts"]')?.click();
  });
  on(root, 'click', '[data-user-recovery]', async (_, button) => {
    const user = userOf();
    if (!armed(button, 'Click again: their old code stops working')) return;
    const data = await send(`/api/users/${encodeURIComponent(user.id)}/recovery`, { method: 'POST' });
    if (!data) return;
    const out = button.closest('form').querySelector('[data-user-code]');
    out.querySelector('code').textContent = data.code;
    out.hidden = false;
  });
  on(root, 'submit', '[data-user-new-form]', (event, form) => {
    event.preventDefault();
    send('/api/users', { json: Object.fromEntries(new FormData(form)) }, 'Account added: give them the temporary password');
  });
  on(root, 'submit', '[data-user-form]', async (event, form) => {
    event.preventDefault();
    const user = userOf();
    const { password, ...fields } = Object.fromEntries(new FormData(form));
    const base = `/api/users/${encodeURIComponent(user.id)}`;
    if (password && !await send(`${base}/password`, { json: { password } })) return;
    send(base, { method: 'PATCH', json: fields }, 'Account saved');
  });
  on(root, 'submit', '[data-user-delete-form]', (event, form) => {
    event.preventDefault();
    const user = userOf();
    if (!armed(form.querySelector('button[type="submit"]'), 'Click again: this cannot be undone')) return;
    const values = Object.fromEntries(new FormData(form));
    const heir = values.keep === 'give' ? values.heir : '';
    send(`/api/users/${encodeURIComponent(user.id)}`, { method: 'DELETE', json: { heir } }, `${user.username} removed`);
  });

  fetchJSON('/api/users').then(({ ok, data }) => {
    if (!ok) {
      root.innerHTML = `<p class="dz-warn">${escapeHtml(data?.error || 'Could not load the accounts.')}</p>`;
      return;
    }
    state = data;
    render();
  });
}
