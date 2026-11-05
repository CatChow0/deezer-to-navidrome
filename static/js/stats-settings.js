// Listening stats, in two places: Settings holds the token Navidrome sends new
// plays with; the Stats tab shows the history and rebuilds it from its sources.

import { armed, escapeHtml, fetchJSON, on, toast } from './core.js';
import { runServerTask } from './activity.js';
import { count, plural } from './stats.js';
import { onViewShown } from './views.js';

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });

function when(seconds) {
  return seconds ? dateFormat.format(new Date(seconds * 1000)) : 'never';
}

function sourceLine(name, source, extra = '') {
  const found = source.found;
  return `<li><span class="dot ${found ? 'dot--ok' : 'dot--miss'}"></span>
    <span><strong>${escapeHtml(name)}</strong>: ${found ? 'found at' : 'not found at'} <code>${escapeHtml(source.path)}</code>${extra ? ` ${escapeHtml(extra)}` : ''}</span></li>`;
}

function reportBlock(report) {
  if (!report) return '<p class="muted">The history has not been imported yet.</p>';
  const mode = report.mode === 'clean' ? 'Start clean' : 'Merge';
  const warnings = (report.warnings || []).map(text => `<p class="help-live help-live--warn">${escapeHtml(text)}</p>`).join('');
  return `<p class="muted">Last rebuild (${mode}), ${escapeHtml(when(report.finished_at))}: ${plural(report.after, 'play')} now, ${count(report.added)} added, ${count(report.updated)} updated, ${count(report.merged)} joined as the same play, ${count(report.removed)} removed. ${count(report.maloja_only)} exist only in Maloja's history.</p>${warnings}`;
}

function renderHistory(host, status) {
  const { sources } = status;
  const kept = sources.maloja.kept_copy ? `A copy saved on ${when(sources.maloja.kept_at)} is used when it is gone.` : '';
  const pendingNote = status.enrich.pending
    ? `Deezer is still being checked for ${plural(status.enrich.pending, 'track')}.`
    : 'Every track has been checked on Deezer.';
  host.innerHTML = `
    <div class="st-history-part">
      <h3>History</h3>
      <p class="muted">${plural(status.plays, 'play')}, the last one on ${escapeHtml(when(status.last_play_at))}. ${escapeHtml(pendingNote)}</p>
      ${reportBlock(status.last_import)}
      <ul class="st-sources">
        ${sourceLine('Navidrome', sources.navidrome)}
        ${sourceLine('Maloja', sources.maloja, kept)}
      </ul>
    </div>
    <div class="st-history-part">
      <h3>Rebuild the history</h3>
      <p class="muted"><strong>Merge</strong> adds what the sources have that is missing here and refreshes track details. It never removes a play.</p>
      <p class="muted"><strong>Start clean</strong> wipes the history and rebuilds it from the sources only, so plays they no longer have are lost. It needs Navidrome's database.</p>
      <p class="muted">Both keep a backup of the current history in the data folder (the last 3).</p>
      <div class="button-row">
        <button type="button" class="btn btn--sm" data-stats-rebuild="merge" ${sources.can_merge && !status.import_running ? '' : 'disabled'}>Rebuild (merge)</button>
        <button type="button" class="btn btn--danger btn--sm" data-stats-rebuild="clean" ${sources.can_clean && !status.import_running ? '' : 'disabled'}>Start clean</button>
      </div>
      <p class="help-live help-live--warn" data-stats-clean-note hidden></p>
      ${sources.can_merge ? '' : '<p class="muted">Mount Navidrome\'s or Maloja\'s database to import your history.</p>'}
      ${sources.can_clean || !sources.can_merge ? '' : '<p class="muted">Start clean is off because Navidrome\'s database is not mounted: without it, most of your history could not be rebuilt.</p>'}
      ${status.import_running ? '<p class="muted">A rebuild is running: follow it in Settings → Activity.</p>' : ''}
    </div>`;
}

function renderToken(host, status) {
  const token = status.token || '';
  host.innerHTML = `
    <div class="security-block">
      <h3>Record new plays</h3>
      <p class="muted">In Navidrome, set this and restart it, then link ListenBrainz in your Navidrome personal settings using the token below.</p>
      <div class="secret-row">
        <input class="mono" type="text" readonly value="ND_LISTENBRAINZ_BASEURL=${escapeHtml(status.base_url_hint)}" aria-label="Navidrome setting" data-stats-setting>
        <button type="button" class="btn btn--ghost btn--sm" data-stats-copy="setting">Copy</button>
      </div>
      <p class="muted">Change the host if Navidrome reaches this app under another name.</p>
      ${token ? `
        <div class="secret-row">
          <input type="password" class="mono" value="${escapeHtml(token)}" readonly data-stats-token aria-label="Token for Navidrome">
          <button type="button" class="btn btn--ghost btn--sm" data-stats-reveal>Show</button>
          <button type="button" class="btn btn--ghost btn--sm" data-stats-copy="token">Copy</button>
        </div>` : '<p class="muted">No token yet: Navidrome cannot send plays until you create one.</p>'}
      ${status.token_from_env
        ? '<p class="muted">Set by the SCROBBLE_TOKEN environment variable.</p>'
        : `<div class="button-row">
            <button type="button" class="btn btn--ghost btn--sm" data-stats-token-new>${token ? 'Make a new token' : 'Create a token'}</button>
            ${token ? '<button type="button" class="btn btn--ghost btn--sm" data-stats-token-delete>Remove the token</button>' : ''}
          </div>
          <form class="secret-row" data-stats-token-form>
            <input class="mono" type="text" name="token" autocomplete="off" placeholder="Or paste a token you already use" aria-label="Paste a token" required>
            <button type="submit" class="btn btn--ghost btn--sm">Use this token</button>
          </form>`}
    </div>`;
}

async function loadStatus() {
  const { ok, data } = await fetchJSON('/api/stats/status');
  return ok ? data : null;
}

async function copy(value, label) {
  try {
    await navigator.clipboard.writeText(value);
    toast(`${label} copied`, { tone: 'ok' });
  } catch (_) {
    toast('Your browser refused the copy: select the text and copy it yourself', { tone: 'error' });
  }
}

export function initStatsSettings() {
  const tokenHost = document.querySelector('[data-stats-settings]');
  const historyHost = document.querySelector('[data-stats-history]');

  const failed = '<p class="st-none">This could not be loaded.</p>';
  const reloadToken = async () => {
    const status = await loadStatus();
    if (status) renderToken(tokenHost, status);
    else tokenHost.innerHTML = failed;
  };
  const reloadHistory = async () => {
    const status = await loadStatus();
    if (status) renderHistory(historyHost, status);
    else historyHost.innerHTML = failed;
  };

  if (tokenHost) {
    on(tokenHost, 'click', '[data-stats-copy]', (_, button) => {
      if (button.dataset.statsCopy === 'token') copy(tokenHost.querySelector('[data-stats-token]').value, 'Token');
      else copy(tokenHost.querySelector('[data-stats-setting]').value, 'Setting');
    });
    on(tokenHost, 'click', '[data-stats-reveal]', (_, button) => {
      const field = tokenHost.querySelector('[data-stats-token]');
      const shown = field.type === 'text';
      field.type = shown ? 'password' : 'text';
      button.textContent = shown ? 'Show' : 'Hide';
    });
    on(tokenHost, 'click', '[data-stats-token-new]', async (_, button) => {
      // A new token stops Navidrome until it is linked again.
      if (button.textContent.startsWith('Make') && !armed(button, 'Navidrome must be linked again: click to confirm')) return;
      const { ok, data } = await fetchJSON('/api/stats/token', { json: {} });
      if (!ok) return toast(data?.error || 'The token was not created', { tone: 'error' });
      toast('Token created', { tone: 'ok' });
      await reloadToken();
    });
    on(tokenHost, 'click', '[data-stats-token-delete]', async (_, button) => {
      if (!armed(button, 'Navidrome will stop recording: click to confirm')) return;
      const { ok, data } = await fetchJSON('/api/stats/token', { method: 'DELETE' });
      if (!ok) return toast(data?.error || 'The token was not removed', { tone: 'error' });
      toast('Token removed', { tone: 'ok' });
      await reloadToken();
    });
    tokenHost.addEventListener('submit', async event => {
      if (!event.target.matches('[data-stats-token-form]')) return;
      event.preventDefault();
      const token = new FormData(event.target).get('token');
      const { ok, data } = await fetchJSON('/api/stats/token', { json: { token } });
      if (!ok) return toast(data?.error || 'The token was not saved', { tone: 'error' });
      toast('Token saved', { tone: 'ok' });
      await reloadToken();
    });
  }

  if (historyHost) {
    on(historyHost, 'click', '[data-stats-rebuild]', async (_, button) => {
      const mode = button.dataset.statsRebuild;
      if (mode === 'clean' && button.dataset.armed !== 'true') {
        button.disabled = true;
        const { ok, data } = await fetchJSON('/api/stats/import/preview', { method: 'POST' });
        button.disabled = false;
        if (!ok) return toast(data?.error || 'Start clean could not be checked', { tone: 'error' });
        const note = historyHost.querySelector('[data-stats-clean-note]');
        note.hidden = false;
        note.textContent = `Start clean would lose ${plural(data.removed, 'play')}: ${count(data.before)} now, ${count(data.after)} afterwards. Plays the sources no longer have cannot come back, except from a backup.`;
        armed(button, `Lose ${plural(data.removed, 'play')}: click to confirm`);
        return;
      }
      if (mode === 'clean') armed(button);
      button.disabled = true;
      const finished = async () => {
        await reloadHistory();
        document.dispatchEvent(new CustomEvent('stats:changed'));
      };
      await runServerTask(mode === 'clean' ? 'Stats history: start clean' : 'Stats history: merge', '/api/stats/import', {
        json: { mode },
        onDone: finished,
        onError: finished,
      });
      await reloadHistory();
    });
  }

  onViewShown(name => {
    if (name === 'settings' && tokenHost) reloadToken();
    if (name === 'stats' && historyHost) reloadHistory();
  });
}
