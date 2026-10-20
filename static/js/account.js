// Settings: connecting the Deezer account whose ARL powers mixes and the release feed.

import { escapeHtml, fetchJSON, toast } from './core.js';

const HELP = `
  <details class="account-help">
    <summary>Where do I find the ARL?</summary>
    <p>Log in to deezer.com in your browser, open the developer tools, then Application (Storage in Firefox) → Cookies → https://www.deezer.com, and copy the value of <code>arl</code>. It stays on this server, in <code>data/secrets.json</code>.</p>
  </details>
`;

function render(host, status) {
  if (status.connected) {
    host.innerHTML = `
      <p class="account-state"><span class="dot dot--ok"></span>Connected as <strong>${escapeHtml(status.name || 'your account')}</strong></p>
      ${status.from_env
        ? '<p class="muted">Set by the DEEZER_ARL environment variable. Change it there to use another account.</p>'
        : '<button type="button" class="btn btn--danger btn--sm" data-account-disconnect>Disconnect</button>'}
    `;
    return;
  }
  host.innerHTML = `
    ${status.error ? `<p class="account-state"><span class="dot dot--miss"></span>${escapeHtml(status.error)}</p>` : ''}
    <form class="account-form" data-account-form>
      <label class="form-field">
        <span>ARL</span>
        <input type="password" name="arl" autocomplete="off" spellcheck="false" placeholder="Paste the arl cookie value" required>
      </label>
      <button type="submit" class="btn btn--sm">Connect</button>
    </form>
    ${HELP}
  `;
}

export async function initAccount() {
  const host = document.querySelector('[data-account]');
  if (!host) return;

  const { data } = await fetchJSON('/api/deezer/account');
  render(host, data || { connected: false, error: 'Could not read the account status' });

  host.addEventListener('submit', async event => {
    const form = event.target.closest('[data-account-form]');
    if (!form) return;
    event.preventDefault();
    const button = form.querySelector('button');
    button.disabled = true;
    button.textContent = 'Checking…';
    const result = await fetchJSON('/api/deezer/account', { json: { arl: form.elements.arl.value.trim() } });
    if (result.data?.ok) {
      toast(`Connected as ${result.data.name || 'your Deezer account'}`, { tone: 'ok' });
      render(host, result.data);
    } else {
      toast(result.data?.error || 'Deezer did not accept this ARL', { tone: 'error' });
      button.disabled = false;
      button.textContent = 'Connect';
    }
  });

  host.addEventListener('click', async event => {
    if (!event.target.closest('[data-account-disconnect]')) return;
    const { data: status } = await fetchJSON('/api/deezer/account', { method: 'DELETE' });
    toast('Deezer account disconnected');
    render(host, status || { connected: false });
  });
}
