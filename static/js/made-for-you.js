// Made for you: turn the generated playlists on, and decide about the tracks they
// downloaded. Nothing leaves the quarantine without a click here.

import { escapeHtml, fetchJSON, on, toast } from './core.js';
import { runServerTask } from './activity.js';
import { playButton } from './player.js';

const VERSIONS = [
  ['daily', 'Daily Mix', 'Up to 4 mixes a day around a track, an album or an artist you keep coming back to, only with music you already have.', false],
  ['blend', 'Daily Mix+', 'The same idea, with about a third of tracks you do not have yet. They are downloaded and go on trial.', true],
  ['discover', 'Discover', 'Every week, only new releases and tracks you never heard, chosen from your habits. They are downloaded and go on trial.', true],
];

const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;

function versionsHtml(state) {
  const { settings, analysis, usage, last_run: lastRun } = state;
  const measured = analysis.total - analysis.left;
  const rows = VERSIONS.map(([key, title, text, downloads]) => {
    const blocked = downloads && !settings[key] ? state.downloads_blocked : '';
    return `
      <div class="mfy-version">
        <div>
          <strong>${title}</strong>
          <p>${text}</p>
          ${blocked ? `<p class="help-live help-live--warn">${escapeHtml(blocked)}</p>` : ''}
        </div>
        <label class="switch" title="${title}">
          <input type="checkbox" data-mfy-version="${key}" aria-label="${title}" ${settings[key] ? 'checked' : ''} ${blocked ? 'disabled' : ''}>
          <span class="switch-slider"></span>
        </label>
      </div>`;
  }).join('');
  const anyOn = VERSIONS.some(([key]) => settings[key]);
  return `
    <h3 class="doc-title">Versions</h3>
    <div class="mfy-versions">${rows}</div>
    <p class="muted" data-mfy-analysis>${analysis.left
      ? `Measuring the tempo of your music: ${measured} of ${analysis.total} files. ${anyOn ? 'Mixes start once most of it is done.' : 'It starts when you turn a version on.'}`
      : `Tempo measured for all ${analysis.total} files.`}</p>
    ${lastRun?.notes?.length ? `<p class="help-live help-live--warn">${lastRun.notes.map(escapeHtml).join(' ')}</p>` : ''}
    <div class="button-row">
      <button type="button" class="btn btn--sm" data-mfy-generate ${!anyOn || state.running ? 'disabled' : ''}>${state.running ? 'Generating…' : 'Regenerate now'}</button>
    </div>
    <h4 class="help-h">Limits</h4>
    <form class="mfy-limits" data-mfy-limits>
      <label><span>Refresh Daily Mixes every (hours)</span><input type="number" min="1" name="daily_hours" value="${settings.daily_hours}"></label>
      <label><span>Refresh Discover every (days)</span><input type="number" min="1" name="discover_days" value="${settings.discover_days}"></label>
      <label><span>New tracks per Daily Mix+ refresh</span><input type="number" min="1" name="blend_new_per_run" value="${settings.blend_new_per_run}"></label>
      <label><span>Tracks in Discover</span><input type="number" min="1" name="discover_size" value="${settings.discover_size}"></label>
      <label><span>Stop downloading at this many unheard tracks</span><input type="number" min="1" name="max_unheard" value="${settings.max_unheard}"></label>
      <label><span>Stop downloading at this quarantine size (GB)</span><input type="number" min="1" name="max_trial_gb" value="${settings.max_trial_gb}"></label>
      <div class="button-row"><button type="submit" class="btn btn--ghost btn--sm">Save limits</button></div>
    </form>
    <p class="muted">In quarantine now: ${(usage.bytes / 1024 ** 3).toFixed(1)} GB, ${plural(usage.unheard, 'unheard track')}.</p>`;
}

function trackRow(track, detail, actions) {
  return `
    <div class="mfy-track">
      ${playButton(track.id, `Play a preview of ${track.artist} - ${track.title}`)}
      <div class="mfy-track-name">
        <strong>${escapeHtml(track.title)}</strong>
        <span>${escapeHtml(track.artist)}</span>
        <span class="muted">${escapeHtml(detail)}</span>
      </div>
      <div class="mfy-track-actions">${actions}</div>
    </div>`;
}

const action = (id, name, label, extra = 'btn--ghost') =>
  `<button type="button" class="btn ${extra} btn--sm" data-mfy-action="${name}" data-mfy-id="${escapeHtml(id)}">${label}</button>`;

const playsText = count => (count ? plural(count, 'play') : 'Never played');

function reviewHtml(state) {
  const intro = '<p>The trial of these tracks ended without you keeping them. They stay here until you decide.</p>';
  if (!state.pending.length) {
    return `<h3 class="doc-title">To review</h3>${intro}<p class="empty">Nothing to decide right now.</p>`;
  }
  return `
    <h3 class="doc-title">To review</h3>
    ${intro}
    <div class="button-row"><button type="button" class="btn btn--danger btn--sm" data-mfy-remove-all>Remove all ${state.pending.length}</button></div>
    <div class="mfy-tracks" data-play-queue>${state.pending.map(t => trackRow(t, t.reason, `${action(t.id, 'keep', 'Keep')} ${action(t.id, 'remove', 'Remove')}`)).join('')}</div>`;
}

function trialHtml(state) {
  const how = `A track is kept once you play it twice or ${state.navidrome_mounted ? 'star it, or rate it 4 or 5 in Navidrome' : 'keep it here'}. After 30 days without that, it moves to To review.`;
  const mount = state.navidrome_mounted ? '' : '<p class="muted">Stars and ratings cannot be read: Navidrome\'s database is not mounted at /import/navidrome.</p>';
  if (!state.on_trial.length) {
    return `<h3 class="doc-title">On trial</h3><p>${how}</p>${mount}<p class="empty">No track on trial.</p>`;
  }
  return `
    <h3 class="doc-title">On trial</h3>
    <p>${how} The On trial playlist has all of them.</p>
    ${mount}
    <div class="mfy-tracks" data-play-queue>${state.on_trial.map(t => trackRow(t, `${playsText(t.plays)}, ${plural(t.days_left, 'day')} left`, `${action(t.id, 'keep', 'Keep')} ${action(t.id, 'remove', 'Remove')}`)).join('')}</div>`;
}

function trashHtml(state) {
  const intro = '<p>Removed tracks wait here for 30 days, then the file is deleted. They are never proposed again.</p>';
  if (!state.trash.length) return `<h3 class="doc-title">Trash</h3>${intro}<p class="empty">The trash is empty.</p>`;
  return `
    <h3 class="doc-title">Trash</h3>
    ${intro}
    <div class="mfy-tracks" data-play-queue>${state.trash.map(t => trackRow(t, `Deleted in ${plural(t.trash_days_left, 'day')}`, action(t.id, 'restore', 'Restore'))).join('')}</div>`;
}

export function initMadeForYou(modal) {
  const root = modal.el;
  const tabs = [...root.querySelectorAll('[data-mfy-tab]')];
  let state = null;

  function panel(name) {
    return root.querySelector(`[data-mfy-panel="${name}"]`);
  }

  function render() {
    panel('versions').innerHTML = versionsHtml(state);
    panel('review').innerHTML = reviewHtml(state);
    panel('trial').innerHTML = trialHtml(state);
    panel('trash').innerHTML = trashHtml(state);
    const counts = { review: state.pending.length, trial: state.on_trial.length, trash: state.trash.length };
    Object.entries(counts).forEach(([name, count]) => {
      root.querySelector(`[data-mfy-count="${name}"]`).textContent = count || '';
    });
    const badge = document.querySelector('[data-mfy-badge]');
    if (badge) {
      badge.textContent = state.pending.length ? `${state.pending.length} to review` : '';
      badge.hidden = !state.pending.length;
    }
  }

  async function load() {
    const { ok, data } = await fetchJSON('/api/mixes');
    if (!ok) return;
    state = data;
    render();
  }

  async function send(url, options = { method: 'POST' }) {
    const { ok, data } = await fetchJSON(url, options);
    if (!ok) {
      toast(data?.error || 'That did not work', { tone: 'error' });
      return false;
    }
    state = data;
    render();
    return true;
  }

  function showTab(name, { focus = false } = {}) {
    tabs.forEach(tab => {
      const active = tab.dataset.mfyTab === name;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      if (active && focus) tab.focus();
    });
    root.querySelectorAll('[data-mfy-panel]').forEach(item => {
      item.hidden = item.dataset.mfyPanel !== name;
    });
    root.querySelector('.doc-article').scrollTop = 0;
  }

  on(root, 'click', '[data-mfy-tab]', (_, tab) => showTab(tab.dataset.mfyTab));
  on(root, 'keydown', '[data-mfy-tab]', (event, tab) => {
    const horizontal = getComputedStyle(tab.parentElement).flexDirection === 'row';
    const next = horizontal ? 'ArrowRight' : 'ArrowDown';
    const previous = horizontal ? 'ArrowLeft' : 'ArrowUp';
    let index = tabs.indexOf(tab);
    if (event.key === next) index += 1;
    else if (event.key === previous) index -= 1;
    else return;
    event.preventDefault();
    showTab(tabs[(index + tabs.length) % tabs.length].dataset.mfyTab, { focus: true });
  });

  on(root, 'change', '[data-mfy-version]', async (_, box) => {
    const done = await send('/api/mixes/settings', { json: { [box.dataset.mfyVersion]: box.checked } });
    if (!done) box.checked = !box.checked;
  });
  on(root, 'submit', '[data-mfy-limits]', async (event, form) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(form));
    if (await send('/api/mixes/settings', { json: values })) toast('Limits saved');
  });
  on(root, 'click', '[data-mfy-generate]', async (_, button) => {
    button.disabled = true;
    modal.close();
    await runServerTask('Generating your mixes', '/api/mixes/generate');
    window.location.reload();
  });
  on(root, 'click', '[data-mfy-action]', (_, button) => {
    button.disabled = true;
    send(`/api/mixes/trial/${encodeURIComponent(button.dataset.mfyId)}/${button.dataset.mfyAction}`);
  });
  on(root, 'click', '[data-mfy-remove-all]', (_, button) => {
    if (button.dataset.armed) {
      send('/api/mixes/trial/remove-pending');
      return;
    }
    button.dataset.armed = '1';
    button.textContent = `Click again to remove ${state.pending.length} tracks`;
  });
  on(document, 'click', '[data-action="made-for-you"]', () => {
    showTab(state?.pending.length ? 'review' : 'versions');
    modal.open({ label: 'Made for you' });
    load();
  });

  load();
}
