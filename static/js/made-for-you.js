// Made for you: turn the generated playlists on, and decide about the tracks they
// downloaded. Nothing leaves the quarantine without a click here.

import { armed, escapeHtml, fetchJSON, on, toast } from './core.js';
import { runServerTask } from './activity.js';
import { playButton } from './player.js';

const MODES = [
  ['off', 'Off', () => 'No Daily Mix. Turning it off removes these playlists, and tracks on trial stay on trial.'],
  ['daily', 'Daily Mix', () => 'Up to 4 mixes around a track, an album or an artist you keep coming back to, only with music you already have.'],
  ['blend', 'Daily Mix+', settings => `The same idea as Daily Mix, with ${settings.blend_new_percent}% of tracks you do not have yet. They are downloaded and go on trial.`],
];

const MODE_SLIDE_MS = 280;
const modeText = (mode, settings) => MODES.find(([key]) => key === mode)[2](settings);

const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;

function versionsHtml(state) {
  const { settings, analysis, usage, last_run: lastRun } = state;
  const measured = analysis.total - analysis.left;
  const mode = settings.mix_mode;
  const blendBlocked = mode !== 'blend' ? state.downloads_blocked : '';
  const discoverBlocked = !settings.discover ? state.downloads_blocked : '';
  const anyOn = mode !== 'off' || settings.discover;
  const positions = MODES.map(([key, label]) => `
        <label class="mfy-mode-option">
          <input type="radio" name="mfy-mode" value="${key}" data-mfy-mode ${key === mode ? 'checked' : ''} ${key === 'blend' && blendBlocked ? 'disabled' : ''}>
          <span>${label}</span>
        </label>`).join('');
  return `
    <h3 class="doc-title">Versions</h3>
    <fieldset class="mfy-mode" data-mode="${mode}">
      <legend class="sr-only">Daily mixes</legend>
      <span class="mfy-mode-thumb" aria-hidden="true"></span>${positions}
    </fieldset>
    <p class="mfy-mode-text">${modeText(mode, settings)}</p>
    ${blendBlocked ? `<p class="help-live help-live--warn">Daily Mix+ cannot be chosen. ${escapeHtml(blendBlocked)}</p>` : ''}
    <div class="mfy-version">
      <div>
        <strong>Discover</strong>
        <p>Only new releases and tracks you never heard, chosen from your habits. They are downloaded and go on trial.</p>
        ${discoverBlocked ? `<p class="help-live help-live--warn">${escapeHtml(discoverBlocked)}</p>` : ''}
      </div>
      <label class="switch" title="Discover">
        <input type="checkbox" data-mfy-discover aria-label="Discover" ${settings.discover ? 'checked' : ''} ${discoverBlocked ? 'disabled' : ''}>
        <span class="switch-slider"></span>
      </label>
    </div>
    <p class="muted" data-mfy-analysis>${analysis.left
      ? `Missing metadata: ${measured} of ${analysis.total} files done. ${anyOn ? 'Mixes start once most of it is done.' : 'Turning a version on starts it: it adds the missing tempo and genre to your files\' tags.'}`
      : `Tempo and genre checked for all ${analysis.total} files.`}</p>
    <p class="muted">${plural(analysis.tagged, 'file')} tagged${analysis.only_in_app ? `, ${analysis.only_in_app} kept only in the app (format without tags, or writing turned off)` : ''}.</p>
    ${analysis.write_errors ? `<p class="help-live help-live--warn">${plural(analysis.write_errors, 'file')} could not be tagged. Is the folder mounted read-only? Their results still count for the mixes, and writing is tried again every day.</p>` : ''}
    ${analysis.paused ? '<p class="muted">Fix missing metadata was cancelled, so it does not run on its own. <b>Fix missing metadata</b> or turning a version on starts it again, from where it stopped.</p>' : ''}
    ${analysis.write_off ? '<p class="muted">Writing to your files is off since the last undo. <b>Fix missing metadata</b> turns it back on.</p>' : ''}
    ${lastRun?.notes?.length ? `<p class="help-live help-live--warn">${lastRun.notes.map(escapeHtml).join(' ')}</p>` : ''}
    <div class="button-row">
      <button type="button" class="btn btn--sm" data-mfy-generate ${!anyOn || state.running ? 'disabled' : ''}>${state.running ? 'Generating…' : 'Regenerate now'}</button>
      ${analysis.can_undo ? `<button type="button" class="btn btn--ghost btn--sm" data-mfy-undo>Undo metadata fix</button>` : ''}
    </div>
    <h4 class="help-h">Limits</h4>
    <form class="mfy-limits" data-mfy-limits>
      <div class="mfy-limit-group">
        <h5>Refresh Rate</h5>
        ${limitField(settings, 'daily_hours', 'Daily Mix / Daily Mix+ every (hours)')}
        ${limitField(settings, 'discover_days', 'Discover every (days)')}
      </div>
      <div class="mfy-limit-group">
        <h5>Length</h5>
        ${limitField(settings, 'mix_size', 'Tracks in each Daily Mix / Daily Mix+', 12, 100)}
        ${limitField(settings, 'discover_size', 'Tracks in Discover')}
      </div>
      <div class="mfy-limit-group">
        <h5>New tracks percent</h5>
        ${limitField(settings, 'blend_new_percent', 'New tracks in each Daily Mix+ (%)', 1, 90)}
        <p class="muted">Daily Mix+ only. Unheard tracks on trial take these places before anything new is downloaded.</p>
      </div>
      <div class="mfy-limit-group">
        <h5>Disk Limit</h5>
        ${limitField(settings, 'max_unheard', 'Stop downloading at this many unheard tracks')}
        ${limitField(settings, 'max_trial_gb', 'Stop downloading at this quarantine size (GB)')}
        <p class="muted">In quarantine now: ${(usage.bytes / 1024 ** 3).toFixed(1)} GB, ${plural(usage.unheard, 'unheard track')}.</p>
      </div>
      <div class="mfy-limits-save">
        <p class="muted">New values apply from the next refresh.</p>
        <button type="submit" class="btn btn--ghost btn--sm">Save limits</button>
      </div>
    </form>`;
}

function limitField(settings, name, label, min = 1, max = null) {
  return `<label class="mfy-limit"><span>${label}</span><input type="number" min="${min}" ${max ? `max="${max}"` : ''} name="${name}" value="${settings[name]}"></label>`;
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

  // What the panel holds that is not saved yet, and where the keyboard was.
  function renderVersions(keepDrafts) {
    const target = panel('versions');
    const drafts = keepDrafts
      ? [...target.querySelectorAll('[data-mfy-limits] input')].filter(input => input.value !== input.defaultValue)
      : [];
    const active = target.contains(document.activeElement) ? document.activeElement : null;
    const focus = active?.matches('[data-mfy-mode]') ? `[data-mfy-mode][value="${active.value}"]`
      : active?.matches('[data-mfy-discover]') ? '[data-mfy-discover]'
        : active?.matches('[data-mfy-limits] input') ? `[name="${active.name}"]` : '';

    target.innerHTML = versionsHtml(state);

    drafts.forEach(input => {
      target.querySelector(`[name="${input.name}"]`).value = input.value;
    });
    if (focus) target.querySelector(focus)?.focus();
  }

  function showMode(mode) {
    root.querySelector('.mfy-mode').dataset.mode = mode;
    root.querySelector(`[data-mfy-mode][value="${mode}"]`).checked = true;
    root.querySelector('.mfy-mode-text').textContent = modeText(mode, state.settings);
  }

  function render({ keepDrafts = true } = {}) {
    renderVersions(keepDrafts);
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
    render({ keepDrafts: false });
  }

  async function send(url, options = { method: 'POST' }, renderOptions = {}) {
    const { ok, data } = await fetchJSON(url, options);
    if (!ok) {
      toast(data?.error || 'That did not work', { tone: 'error' });
      return false;
    }
    state = data;
    render(renderOptions);
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

  on(root, 'change', '[data-mfy-mode]', async (_, radio) => {
    // The switch answers at once. Saving rewrites the panel, so it waits for the slide.
    showMode(radio.value);
    await new Promise(resolve => setTimeout(resolve, MODE_SLIDE_MS));
    const done = await send('/api/mixes/settings', { json: { mix_mode: radio.value } });
    if (!done) showMode(state.settings.mix_mode);
  });
  on(root, 'change', '[data-mfy-discover]', async (_, box) => {
    const done = await send('/api/mixes/settings', { json: { discover: box.checked } });
    if (!done) box.checked = !box.checked;
  });
  on(root, 'submit', '[data-mfy-limits]', async (event, form) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(form));
    if (await send('/api/mixes/settings', { json: values }, { keepDrafts: false })) toast('Limits saved');
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
  on(root, 'click', '[data-mfy-undo]', async (_, button) => {
    if (!armed(button, `Click again: removes what was added to ${state.analysis.can_undo} files`)) return;
    button.disabled = true;
    await runServerTask('Undo metadata fix', '/api/metadata/undo');
    load();
  });
  on(root, 'click', '[data-mfy-remove-all]', (_, button) => {
    if (armed(button, `Click again to remove ${state.pending.length} tracks`)) send('/api/mixes/trial/remove-pending');
  });
  on(document, 'click', '[data-action="fix-metadata"]', async (_, button) => {
    if (!armed(button, 'Click again: adds tags to your files')) return;
    button.disabled = true;
    await runServerTask('Fix missing metadata', '/api/metadata/fix');
    button.disabled = false;
  });
  on(document, 'click', '[data-action="made-for-you"]', () => {
    showTab(state?.pending.length ? 'review' : 'versions');
    modal.open({ label: 'Made for you' });
    load();
  });

  load();
}
