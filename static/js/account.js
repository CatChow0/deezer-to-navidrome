// Settings: the Deezer accounts. The first one powers the mixes and the
// release feed; a second one can be added for the downloads when the first
// is free (a free account only gets MP3_128).

import { escapeHtml, fetchJSON, toast } from './core.js';

const HELP = `
  <details class="account-help">
    <summary>Where do I find the ARL?</summary>
    <p>Log in to deezer.com in your browser, open the developer tools, then Application (Storage in Firefox) → Cookies → https://www.deezer.com, and copy the value of <code>arl</code>. It stays on this server, in <code>data/secrets.json</code>.</p>
  </details>
`;

// The badge says what the account can do: Premium, Free, or Free with the
// downloads running on a premium account.
export function planBadge(status) {
  const downloads = status.downloads || {};
  let plan = '<span class="chip">Free account</span>';
  if (status.premium) {
    plan = '<span class="chip chip--ok">Premium account</span>';
  } else if (downloads.has_premium_arl && downloads.premium) {
    plan = '<span class="chip chip--partial">Free account · downloads in Premium</span>';
  }
  return `${plan} ${countryBadge(status.country)}`;
}

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

const FORMAT_LABEL = { FLAC: 'FLAC', MP3_320: 'MP3 320', MP3_128: 'MP3 128' };

function downloadNote(status) {
  const downloads = status.downloads || {};
  const format = FORMAT_LABEL[downloads.format] || downloads.format;
  if (status.premium) {
    return `<p class="muted">The downloads use this account, in ${escapeHtml(format || 'the best quality it allows')}.</p>`;
  }
  if (downloads.has_premium_arl && downloads.premium) {
    const other = downloads.country && downloads.country !== status.country ? `, with the catalogue of ${escapeHtml(countryName(downloads.country))}` : '';
    return `<p class="muted">The downloads use your second, premium account, in ${escapeHtml(format || 'the best quality it allows')}${other}.</p>`;
  }
  return '<p class="muted">A free account only downloads MP3_128. Add a premium account below to get FLAC.</p>';
}

function premiumForm(status) {
  const downloads = status.downloads || {};
  if (status.premium) return '';

  if (downloads.has_premium_arl) {
    return `
      <div class="account-form">
        <p class="account-state"><span class="dot dot--ok"></span>A premium account is connected for the downloads.</p>
        <button type="button" class="btn btn--danger btn--sm" data-premium-disconnect>Remove it</button>
      </div>
    `;
  }

  return `
    <form class="account-form" data-premium-form>
      <label class="form-field">
        <span>ARL of a premium account</span>
        <input type="password" name="arl" autocomplete="off" spellcheck="false" placeholder="Paste the arl cookie value" required>
        <small>Only used for the downloads, so your mixes keep using the first account.</small>
      </label>
      <button type="submit" class="btn btn--sm">Use it for the downloads</button>
    </form>
  `;
}

function render(host, status) {
  if (status.connected) {
    host.innerHTML = `
      <p class="account-state"><span class="dot dot--ok"></span>Connected as <strong>${escapeHtml(status.name || 'your account')}</strong></p>
      <p class="account-badges">${planBadge(status)}</p>
      ${downloadNote(status)}
      ${status.from_env
        ? '<p class="muted">Set by the DEEZER_ARL environment variable. Change it there to use another account.</p>'
        : '<button type="button" class="btn btn--danger btn--sm" data-account-disconnect>Disconnect</button>'}
      ${premiumForm(status)}
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
    const form = event.target.closest('[data-account-form], [data-premium-form]');
    if (!form) return;
    event.preventDefault();
    const premium = form.matches('[data-premium-form]');
    const button = form.querySelector('button');
    button.disabled = true;
    button.textContent = 'Checking…';
    const url = premium ? '/api/deezer/premium-account' : '/api/deezer/account';
    const result = await fetchJSON(url, { json: { arl: form.elements.arl.value.trim() } });
    if (result.data?.ok) {
      toast(premium ? 'Premium account connected for the downloads' : `Connected as ${result.data.name || 'your Deezer account'}`, { tone: 'ok' });
      render(host, result.data);
    } else {
      toast(result.data?.error || 'Deezer did not accept this ARL', { tone: 'error' });
      button.disabled = false;
      button.textContent = premium ? 'Use it for the downloads' : 'Connect';
    }
  });

  host.addEventListener('click', async event => {
    if (event.target.closest('[data-account-disconnect]')) {
      const { data: status } = await fetchJSON('/api/deezer/account', { method: 'DELETE' });
      toast('Deezer account disconnected');
      render(host, status || { connected: false });
      return;
    }
    if (event.target.closest('[data-premium-disconnect]')) {
      const { data: status } = await fetchJSON('/api/deezer/premium-account', { method: 'DELETE' });
      toast('The premium account was removed');
      render(host, status || { connected: false });
    }
  });
}
