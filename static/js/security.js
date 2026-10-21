// Settings: password, the API token other apps (CatBoard) use, and the
// webhook URL CatBoard gives, called when the release feed or the library
// index changed.

import { armed, escapeHtml, fetchJSON, on, toast } from './core.js';

function passwordBlock(status) {
  if (status.account_from_env) {
    return `<div class="security-block"><h3>Account</h3><p class="muted">Signed in as <strong>${escapeHtml(status.username)}</strong>. Set by APP_USERNAME / APP_PASSWORD: change it there.</p></div>`;
  }
  return `
    <form class="security-block" data-password-form>
      <h3>Account</h3>
      <p class="muted">Signed in as <strong>${escapeHtml(status.username)}</strong>. A new password signs out your other browsers.</p>
      <label class="form-field">
        <span>Current password</span>
        <input type="password" name="current" autocomplete="current-password" required>
      </label>
      <label class="form-field">
        <span>New password</span>
        <input type="password" name="new" autocomplete="new-password" minlength="8" required>
      </label>
      <div class="button-row"><button type="submit" class="btn btn--sm">Change the password</button></div>
    </form>
  `;
}

function tokenBlock(status) {
  const token = status.token || '';
  return `
    <div class="security-block">
      <h3>API token</h3>
      <p class="muted">Paste it in CatBoard (Settings → Integrations → Deezer to Navidrome). It only reads the release feed and checks the library.</p>
      ${token ? `
        <div class="secret-row">
          <input type="password" class="mono" value="${escapeHtml(token)}" readonly data-token-field aria-label="API token">
          <button type="button" class="btn btn--ghost btn--sm" data-token-reveal>Show</button>
          <button type="button" class="btn btn--ghost btn--sm" data-token-copy>Copy</button>
        </div>` : '<p class="muted">No token yet.</p>'}
      ${status.token_from_env
        ? '<p class="muted">Set by the API_TOKEN environment variable.</p>'
        : `<div class="button-row"><button type="button" class="btn btn--ghost btn--sm" data-token-new>${token ? 'Make a new token' : 'Create a token'}</button></div>`}
    </div>
  `;
}

function webhookBlock(status) {
  return `
    <form class="security-block" data-webhook-form>
      <h3>CatBoard webhook</h3>
      <p class="muted">Copy the webhook URL from CatBoard (Settings → Integrations → Deezer to Navidrome). It is called when the release feed or the library index is refreshed, so CatBoard updates at once.</p>
      <label class="form-field">
        <span>Webhook URL</span>
        <input type="url" name="url" class="mono" value="${escapeHtml(status.webhook_url || '')}" placeholder="http://catboard:3000/api/integrations/deezer/webhook?token=…" autocomplete="off" spellcheck="false">
      </label>
      <div class="button-row">
        <button type="submit" class="btn btn--sm">Save</button>
        ${status.webhook_url ? '<button type="button" class="btn btn--ghost btn--sm" data-webhook-test>Send a test</button><button type="button" class="btn btn--danger btn--sm" data-webhook-remove>Remove</button>' : ''}
      </div>
    </form>
  `;
}

function render(host, status) {
  if (status.disabled) {
    host.innerHTML = '<p class="muted">Sign-in is turned off (DISABLE_AUTH). Other apps can read the release feed without a token.</p>';
    return;
  }
  host.innerHTML = passwordBlock(status) + tokenBlock(status) + webhookBlock(status);
}

async function load(host) {
  const { data } = await fetchJSON('/api/auth/status');
  if (data?.ok) render(host, data);
  else host.innerHTML = '<p class="muted">Could not load these settings.</p>';
}

export async function initSecurity() {
  const host = document.querySelector('[data-security]');
  if (!host) return;
  await load(host);

  host.addEventListener('submit', async event => {
    const form = event.target;
    event.preventDefault();
    if (form.matches('[data-password-form]')) {
      const fields = Object.fromEntries(new FormData(form));
      const { ok, data } = await fetchJSON('/api/auth/password', { json: fields });
      if (!ok) return toast(data?.error || 'The password was not changed', { tone: 'error' });
      form.reset();
      toast('Password changed', { tone: 'ok' });
    } else if (form.matches('[data-webhook-form]')) {
      const url = new FormData(form).get('url');
      const { ok, data } = await fetchJSON('/api/webhook', { method: 'PUT', json: { url } });
      if (!ok) return toast(data?.error || 'Not saved', { tone: 'error' });
      toast(url ? 'Webhook saved' : 'Webhook removed', { tone: 'ok' });
      await load(host);
    }
  });

  on(host, 'click', '[data-token-reveal]', (_, button) => {
    const field = host.querySelector('[data-token-field]');
    const shown = field.type === 'text';
    field.type = shown ? 'password' : 'text';
    button.textContent = shown ? 'Show' : 'Hide';
  });

  on(host, 'click', '[data-token-copy]', async () => {
    const value = host.querySelector('[data-token-field]').value;
    try {
      await navigator.clipboard.writeText(value);
      toast('Token copied', { tone: 'ok' });
    } catch {
      toast('Copy failed: show the token and copy it by hand', { tone: 'error' });
    }
  });

  on(host, 'click', '[data-token-new]', async (_, button) => {
    // A new token stops the old one: ask twice when one exists.
    if (host.querySelector('[data-token-field]') && !armed(button, 'Click again: CatBoard will need the new one')) return;
    const { ok, data } = await fetchJSON('/api/auth/token', { method: 'POST' });
    if (!ok) return toast(data?.error || 'No new token', { tone: 'error' });
    toast('New token created: update it in CatBoard', { tone: 'ok' });
    await load(host);
  });

  on(host, 'click', '[data-webhook-test]', async () => {
    const { ok, data } = await fetchJSON('/api/webhook/test', { method: 'POST' });
    toast(ok ? 'CatBoard received the test' : data?.message || 'The test failed', { tone: ok ? 'ok' : 'error' });
  });

  on(host, 'click', '[data-webhook-remove]', async (_, button) => {
    if (!armed(button)) return;
    await fetchJSON('/api/webhook', { method: 'DELETE' });
    toast('Webhook removed', { tone: 'ok' });
    await load(host);
  });
}
