// Made for you: turn the generated playlists on, set the rules of the quarantine,
// and decide about the tracks they downloaded.

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
  // With several Navidrome profiles, each has its own mixes: say whose these are.
  const profile = state.profile?.several
    ? `<p class="muted mfy-profile">For <b>${escapeHtml(state.profile.label)}</b>: built from ${escapeHtml(state.profile.label)}'s listening history and published for this profile only. Each profile has its own settings and quarantine.</p>`
    : '';
  return `
    <h3 class="doc-title">Versions</h3>
    ${profile}
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
        ${limitField(settings, 'daily_hours', 'Daily Mix / Daily Mix+ every (hours)', 1, 168)}
        ${limitField(settings, 'discover_days', 'Discover every (days)', 1, 90)}
      </div>
      <div class="mfy-limit-group">
        <h5>Length</h5>
        ${limitField(settings, 'mix_size', 'Tracks in each Daily Mix / Daily Mix+', 12, 100)}
        ${limitField(settings, 'discover_size', 'Tracks in Discover', 1, 200)}
      </div>
      <div class="mfy-limit-group">
        <h5>New tracks percent</h5>
        ${limitField(settings, 'blend_new_percent', 'New tracks in each Daily Mix+ (%)', 1, 90)}
        <p class="muted">Daily Mix+ only. Unheard tracks on trial take these places before anything new is downloaded.</p>
      </div>
      <div class="mfy-limit-group">
        <h5>Disk Limit</h5>
        ${limitField(settings, 'max_unheard', 'Stop downloading at this many unheard tracks', 1, 10000)}
        ${limitField(settings, 'max_trial_gb', 'Stop downloading at this quarantine size (GB)', 1, 10000)}
        <p class="muted">In quarantine now${state.profile?.several ? ', every profile together' : ''}: ${(usage.bytes / 1024 ** 3).toFixed(1)} GB, ${plural(usage.unheard, 'unheard track')}.</p>
        ${state.profile?.several ? '<p class="muted">The same for every profile: they share the disk.</p>' : ''}
      </div>
      <div class="mfy-limits-save">
        <p class="muted">New values apply from the next refresh.</p>
        <button type="submit" class="btn btn--ghost btn--sm">Save limits</button>
      </div>
    </form>
    ${trialRulesHtml(state)}`;
}

function limitField(settings, name, label, min = 1, max = null, extra = '') {
  return `<label class="mfy-limit"><span>${label}</span><input type="number" min="${min}" ${max ? `max="${max}"` : ''} name="${name}" value="${settings[name]}" ${extra}></label>`;
}

// Settings that only matter while automatic validation is on.
const needsAuto = settings => `data-mfy-needs-auto ${settings.trial_auto ? '' : 'disabled'}`;

function switchField(settings, name, label, extra = '') {
  return `
        <label class="mfy-switch-row">
          <span>${label}</span>
          <span class="switch">
            <input type="checkbox" name="${name}" ${settings[name] ? 'checked' : ''} ${extra}>
            <span class="switch-slider"></span>
          </span>
        </label>`;
}

function trialRulesHtml(state) {
  const { settings } = state;
  return `
    <h4 class="help-h">Trial</h4>
    <form class="mfy-limits" data-mfy-trial>
      <div class="mfy-limit-group mfy-limit-group--wide">
        <h5>Automatic validation</h5>
        ${switchField(settings, 'trial_auto', 'Decide about tracks on trial with the rules below')}
        <p class="muted">Off: tracks stay on trial until you keep or remove them. The trash still empties itself.</p>
      </div>
      <div class="mfy-limit-group">
        <h5>Durations</h5>
        ${limitField(settings, 'trial_days', 'Days on trial', 1, 365, needsAuto(settings))}
        ${limitField(settings, 'trash_days', 'Days in the trash', 1, 365)}
        <p class="muted">A new length also applies to tracks already there.</p>
      </div>
      <div class="mfy-limit-group">
        <h5>Rules</h5>
        ${switchField(settings, 'trial_delete', 'Delete permanently after the trial period ends', needsAuto(settings))}
        ${switchField(settings, 'trial_bypass', 'Bypass user review', needsAuto(settings))}
        ${limitField(settings, 'trial_plays', 'Plays to validate a track', 1, 50, needsAuto(settings))}
        ${switchField(settings, 'trial_marks', 'Starred or rated 4-5 in Navidrome counts', needsAuto(settings))}
        ${state.navidrome_mounted ? '' : '<p class="muted">Navidrome\'s database is not mounted at /import/navidrome, so stars and ratings cannot be read.</p>'}
      </div>
      <div class="mfy-limits-save">
        <p class="muted">Rules apply at once to the tracks already in quarantine.</p>
        <button type="submit" class="btn btn--ghost btn--sm">Save trial rules</button>
      </div>
    </form>`;
}

// --- The three lists ------------------------------------------------------------

const SOURCES = [['Daily Mix+', 'From Daily Mix+'], ['Discover', 'From Discover']];
const byText = key => (a, b) => a[key].localeCompare(b[key], undefined, { sensitivity: 'base' });
const SORTS = {
  newest_download: (a, b) => b.downloaded_at - a.downloaded_at,
  newest_state: (a, b) => b.state_at - a.state_at,
  ending: (a, b) => a.days_left - b.days_left || b.downloaded_at - a.downloaded_at,
  trash_ending: (a, b) => a.trash_days_left - b.trash_days_left || b.state_at - a.state_at,
  plays: (a, b) => b.plays - a.plays || b.downloaded_at - a.downloaded_at,
  artist: (a, b) => byText('artist')(a, b) || byText('title')(a, b),
  title: byText('title'),
};

const LISTS = {
  trial: {
    key: 'on_trial',
    title: 'On trial',
    empty: 'No track on trial.',
    sorts: [['newest_download', 'Newest'], ['ending', 'Ending soonest'], ['plays', 'Most played'], ['artist', 'Artist'], ['title', 'Title']],
    filters: () => [['all', 'All tracks'], ...SOURCES, ['played', 'Played'], ['unplayed', 'Never played']],
    detail: t => `${playsText(t.plays)} · ${plural(t.days_left, 'day')} left`,
    actions: t => `${action(t.id, 'keep', 'Keep')} ${action(t.id, 'remove', 'Remove')}`,
  },
  review: {
    key: 'pending',
    title: 'To review',
    empty: 'Nothing to confirm right now.',
    sorts: [['newest_state', 'Newest'], ['plays', 'Most played'], ['artist', 'Artist'], ['title', 'Title']],
    filters: tracks => [['all', 'All tracks'], ...SOURCES,
      ...[...new Set(tracks.map(t => t.reason).filter(Boolean))].sort().map(reason => [`reason:${reason}`, reason])],
    // The reason often is the plays already: said once.
    detail: t => (!t.reason || t.reason === playsText(t.plays) || /^(Played|Never played)/.test(t.reason)
      ? t.reason || playsText(t.plays) : `${t.reason} · ${playsText(t.plays)}`),
    actions: t => `${action(t.id, 'keep', 'Keep', 'mfy-btn--review')} ${action(t.id, 'remove', 'Remove')}`,
  },
  trash: {
    key: 'trash',
    title: 'Trash',
    empty: 'The trash is empty.',
    sorts: [['trash_ending', 'Deleted soonest'], ['newest_state', 'Recently removed'], ['artist', 'Artist'], ['title', 'Title']],
    filters: () => [['all', 'All tracks'], ...SOURCES],
    detail: t => `${t.reason || 'Removed'} · deleted in ${plural(t.trash_days_left, 'day')}`,
    actions: t => action(t.id, 'restore', 'Restore'),
  },
};

const VIEWS_KEY = 'mfy-list-views';

function loadViews() {
  try {
    return JSON.parse(localStorage.getItem(VIEWS_KEY)) || {};
  } catch {
    return {};
  }
}

// Sort and filter are remembered; a search is not.
function saveViews(views) {
  const kept = Object.fromEntries(Object.entries(views).map(([name, { sort, filter }]) => [name, { sort, filter }]));
  try {
    localStorage.setItem(VIEWS_KEY, JSON.stringify(kept));
  } catch {
    // Private window or blocked storage: the choice lasts until the page closes.
  }
}

function view(views, name) {
  const list = LISTS[name];
  const current = { q: '', sort: list.sorts[0][0], filter: 'all', ...(views[name] || {}) };
  if (!list.sorts.some(([key]) => key === current.sort)) current.sort = list.sorts[0][0];
  return current;
}

function shown(name, tracks, current) {
  const words = current.q.trim().toLowerCase();
  const kept = tracks.filter(t => {
    if (words && !`${t.title} ${t.artist} ${t.album}`.toLowerCase().includes(words)) return false;
    const filter = current.filter;
    if (filter === 'all') return true;
    if (filter === 'played') return t.plays > 0;
    if (filter === 'unplayed') return !t.plays;
    if (filter.startsWith('reason:')) return t.reason === filter.slice(7);
    return t.source === filter;
  });
  return kept.sort(SORTS[current.sort]);
}

function introHtml(name, state) {
  const s = state.settings;
  if (name === 'trial') {
    if (!s.trial_auto) return '<p>Automatic validation is off: tracks stay here until you keep or remove them.</p>';
    const marks = s.trial_marks ? ', or star it or rate it 4 or 5 in Navidrome' : '';
    const then = s.trial_bypass ? 'it is kept at once' : 'it waits under To review';
    const end = s.trial_delete ? 'it is deleted' : 'it goes to the trash';
    const mount = s.trial_marks && !state.navidrome_mounted
      ? '<p class="muted">Stars and ratings cannot be read: Navidrome\'s database is not mounted at /import/navidrome.</p>' : '';
    return `<p>Play a track ${plural(s.trial_plays, 'time')}${marks}, and ${then}. After ${plural(s.trial_days, 'day')} without that, ${end}. The On trial playlist has all of them.</p>${mount}`;
  }
  if (name === 'review') {
    return '<p>These tracks earned their place. <b>Keep</b> moves them to your downloads, <b>Remove</b> sends them to the trash. They wait here as long as needed.</p>';
  }
  return `<p>Removed tracks wait here for ${plural(s.trash_days, 'day')}, then the file is deleted. They are never proposed again.</p>`;
}

function rowsHtml(name, tracks) {
  const list = LISTS[name];
  return tracks.map(t => trackRow(t, list.detail(t), list.actions(t))).join('');
}

function headHtml(name, state, visible) {
  const all = state[LISTS[name].key];
  const count = visible.length === all.length ? plural(all.length, 'track') : `${visible.length} of ${plural(all.length, 'track')}`;
  let bulk = '';
  if (name === 'review' && visible.length) {
    bulk = `<button type="button" class="btn btn--sm mfy-btn--review" data-mfy-keep-all>Keep ${visible.length === all.length ? 'all' : 'these'} ${visible.length}</button>`;
  } else if (name === 'trash' && all.length) {
    bulk = '<button type="button" class="btn btn--sm mfy-btn--trash" data-mfy-empty-trash>Empty trash</button>';
  }
  return `<span class="muted">${count}</span>${bulk}`;
}

function listHtml(name, state, current) {
  const list = LISTS[name];
  const all = state[list.key];
  const intro = introHtml(name, state);
  if (!all.length) return `<h3 class="doc-title">${list.title}</h3>${intro}<p class="empty">${list.empty}</p>`;
  const options = (items, selected) => items.map(([key, label]) =>
    `<option value="${escapeHtml(key)}" ${key === selected ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('');
  const visible = shown(name, all, current);
  return `
    <h3 class="doc-title">${list.title}</h3>
    ${intro}
    <div class="mfy-toolbar">
      <input class="search-input mfy-search" type="search" placeholder="Search title, artist or album" aria-label="Search ${list.title}" autocomplete="off" data-mfy-q="${name}" value="${escapeHtml(current.q)}">
      <select data-mfy-sort="${name}" aria-label="Sort ${list.title}">${options(list.sorts, current.sort)}</select>
      <select data-mfy-filter="${name}" aria-label="Show in ${list.title}">${options(list.filters(all), current.filter)}</select>
    </div>
    <div class="mfy-list-head" data-mfy-head="${name}">${headHtml(name, state, visible)}</div>
    <div class="mfy-tracks" data-play-queue data-mfy-list="${name}">${visible.length ? rowsHtml(name, visible) : '<p class="empty">No track matches.</p>'}</div>`;
}

function trackRow(track, detail, actions) {
  return `
    <div class="mfy-track">
      <span class="mfy-cover" aria-hidden="true"><img src="${escapeHtml(track.cover)}" alt="" loading="lazy" data-mfy-cover></span>
      ${playButton(track.id, `Play a preview of ${track.artist} - ${track.title}`)}
      <div class="mfy-track-name">
        <strong>${escapeHtml(track.title)}</strong>
        <span>${escapeHtml(track.artist)}${track.album ? ` · ${escapeHtml(track.album)}` : ''}</span>
        <span class="muted">${escapeHtml(detail)} · <span class="mfy-source">${escapeHtml(track.source)}</span>${track.shared_with?.length ? ` · <span class="mfy-shared" title="One file for both: each profile decides for itself">Also on trial for ${track.shared_with.map(escapeHtml).join(', ')}</span>` : ''}</span>
      </div>
      <div class="mfy-track-actions">${actions}</div>
    </div>`;
}

const action = (id, name, label, extra = 'btn--ghost') =>
  `<button type="button" class="btn ${extra} btn--sm" data-mfy-action="${name}" data-mfy-id="${escapeHtml(id)}">${label}</button>`;

const playsText = count => (count ? plural(count, 'play') : 'Never played');

export function initMadeForYou(modal) {
  const root = modal.el;
  const tabs = [...root.querySelectorAll('[data-mfy-tab]')];
  let state = null;
  const views = loadViews();

  function panel(name) {
    return root.querySelector(`[data-mfy-panel="${name}"]`);
  }

  // What the panel holds that is not saved yet, and where the keyboard was.
  function renderVersions(keepDrafts) {
    const target = panel('versions');
    const fields = '[data-mfy-limits] input, [data-mfy-trial] input';
    const changed = input => (input.type === 'checkbox' ? input.checked !== input.defaultChecked : input.value !== input.defaultValue);
    const drafts = keepDrafts ? [...target.querySelectorAll(fields)].filter(changed) : [];
    const active = target.contains(document.activeElement) ? document.activeElement : null;
    const focus = active?.matches('[data-mfy-mode]') ? `[data-mfy-mode][value="${active.value}"]`
      : active?.matches('[data-mfy-discover]') ? '[data-mfy-discover]'
        : active?.matches(fields) ? `[name="${active.name}"]` : '';

    target.innerHTML = versionsHtml(state);

    drafts.forEach(input => {
      const field = target.querySelector(`[name="${input.name}"]`);
      if (input.type === 'checkbox') field.checked = input.checked;
      else field.value = input.value;
    });
    syncTrialRules();
    if (focus) target.querySelector(focus)?.focus();
  }

  function syncTrialRules() {
    const form = root.querySelector('[data-mfy-trial]');
    if (!form) return;
    const on = form.elements.trial_auto.checked;
    form.querySelectorAll('[data-mfy-needs-auto]').forEach(input => {
      input.disabled = !on;
    });
  }

  function renderList(name) {
    panel(name).innerHTML = listHtml(name, state, view(views, name));
  }

  // Typing in the search keeps its focus: only the rows and the count change.
  function refreshRows(name) {
    const current = view(views, name);
    const visible = shown(name, state[LISTS[name].key], current);
    const rows = panel(name).querySelector('[data-mfy-list]');
    if (!rows) return renderList(name);
    rows.innerHTML = visible.length ? rowsHtml(name, visible) : '<p class="empty">No track matches.</p>';
    panel(name).querySelector('[data-mfy-head]').innerHTML = headHtml(name, state, visible);
  }

  function setView(name, change) {
    views[name] = { ...view(views, name), ...change };
    saveViews(views);
    refreshRows(name);
  }

  function renderCounter() {
    const counter = document.querySelector('[data-mfy-counter]');
    if (!counter) return;
    const counts = { trial: state.on_trial.length, review: state.pending.length, trash: state.trash.length };
    Object.entries(counts).forEach(([name, count]) => {
      counter.querySelector(`[data-mfy-counter-value="${name}"]`).textContent = count;
    });
    counter.hidden = !Object.values(counts).some(Boolean);
  }

  function showMode(mode) {
    root.querySelector('.mfy-mode').dataset.mode = mode;
    root.querySelector(`[data-mfy-mode][value="${mode}"]`).checked = true;
    root.querySelector('.mfy-mode-text').textContent = modeText(mode, state.settings);
  }

  function render({ keepDrafts = true } = {}) {
    renderVersions(keepDrafts);
    Object.keys(LISTS).forEach(name => {
      const search = panel(name).querySelector('[data-mfy-q]');
      if (search && search === document.activeElement) refreshRows(name);
      else renderList(name);
    });
    const counts = { review: state.pending.length, trial: state.on_trial.length, trash: state.trash.length };
    Object.entries(counts).forEach(([name, count]) => {
      root.querySelector(`[data-mfy-count="${name}"]`).textContent = count || '';
    });
    renderCounter();
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
  on(root, 'change', '[data-mfy-trial] [name="trial_auto"]', () => syncTrialRules());
  on(root, 'submit', '[data-mfy-trial]', async (event, form) => {
    event.preventDefault();
    // Read every field, the greyed ones too: switching the validation off keeps the rules.
    const values = {};
    [...form.querySelectorAll('input[name]')].forEach(input => {
      values[input.name] = input.type === 'checkbox' ? input.checked : input.value;
    });
    if (await send('/api/mixes/settings', { json: values }, { keepDrafts: false })) toast('Trial rules saved');
  });
  on(root, 'input', '[data-mfy-q]', (_, input) => setView(input.dataset.mfyQ, { q: input.value }));
  on(root, 'change', '[data-mfy-sort]', (_, select) => setView(select.dataset.mfySort, { sort: select.value }));
  on(root, 'change', '[data-mfy-filter]', (_, select) => setView(select.dataset.mfyFilter, { filter: select.value }));
  // A file without a picture: the empty square stays.
  root.addEventListener('error', event => {
    if (event.target.matches?.('[data-mfy-cover]')) event.target.hidden = true;
  }, true);
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
  on(root, 'click', '[data-mfy-keep-all]', (_, button) => {
    const ids = shown('review', state.pending, view(views, 'review')).map(t => t.id);
    if (!armed(button, `Click again to keep ${plural(ids.length, 'track')}`)) return;
    button.disabled = true;
    send('/api/mixes/trial/keep-pending', { json: { ids } });
  });
  on(root, 'click', '[data-mfy-empty-trash]', (_, button) => {
    if (!armed(button, `Click again: deletes ${plural(state.trash.length, 'file')} for good`)) return;
    button.disabled = true;
    send('/api/mixes/trial/empty-trash');
  });
  on(document, 'click', '[data-action="fix-metadata"]', async (_, button) => {
    if (!armed(button, 'Click again: adds tags to your files')) return;
    button.disabled = true;
    await runServerTask('Fix missing metadata', '/api/metadata/fix');
    button.disabled = false;
  });
  function open(tab) {
    showTab(tab);
    modal.open({ label: 'Made for you' });
    load();
  }
  on(document, 'click', '[data-action="made-for-you"]', () => open(state?.pending.length ? 'review' : 'versions'));
  on(document, 'click', '[data-mfy-open]', (_, cell) => open(cell.dataset.mfyOpen));

  load();
}
