// Stats view: the latest recap on top, charts for a chosen period below it, and
// your recent plays. Everything is loaded when the view is shown; opening a
// recap and the rebuild controls live in their own modules.

import { escapeHtml, fetchJSON, on } from './core.js';
import { playButton } from './player.js';
import { onViewShown } from './views.js';

const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
const numberFormat = new Intl.NumberFormat();
const dateFormat = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
const dateTimeFormat = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
const monthFormat = new Intl.DateTimeFormat(undefined, { month: 'short', year: '2-digit', timeZone: 'UTC' });
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const state = {
  period: 'month',
  key: '',
  index: null,
  query: '',
  page: 1,
  searchTimer: null,
};

const $ = selector => document.querySelector(`[data-stats] ${selector}`);
const $$ = selector => [...document.querySelectorAll(`[data-stats] ${selector}`)];

export const count = value => numberFormat.format(value || 0);

export function duration(seconds) {
  const minutes = Math.round((seconds || 0) / 60);
  const hours = Math.floor(minutes / 60);
  if (!hours) return `${minutes} min`;
  return minutes % 60 ? `${count(hours)} h ${minutes % 60} min` : `${count(hours)} h`;
}

export const plural = (n, word) => `${count(n)} ${word}${n === 1 ? '' : 's'}`;

function hueOf(text) {
  let hash = 5381;
  for (const char of String(text)) hash = ((hash << 5) + hash + char.codePointAt(0)) | 0;
  return Math.abs(hash) % 360;
}

function initials(name) {
  return [...String(name || '?').trim()].length
    ? String(name).trim().split(/\s+/).slice(0, 2).map(word => [...word][0]).join('').toUpperCase()
    : '?';
}

// A cover, or the name's initials on a color of its own while there is none.
export function art(image, name) {
  const picture = image && /^\/stats\/cover\//.test(image) ? `<img src="${escapeHtml(image)}" alt="" loading="lazy" data-stats-img>` : '';
  return `<span class="st-art" style="--hue:${hueOf(name)}" aria-hidden="true">${escapeHtml(initials(name))}${picture}</span>`;
}

function pad(n) {
  return String(n).padStart(2, '0');
}

function isoWeekKey(date) {
  const day = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  day.setUTCDate(day.getUTCDate() + 4 - (day.getUTCDay() || 7));
  const yearStart = new Date(Date.UTC(day.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((day - yearStart) / 86400000 + 1) / 7);
  return `${day.getUTCFullYear()}-W${pad(week)}`;
}

function keyOfDate(period, date) {
  if (period === 'week') return isoWeekKey(date);
  if (period === 'month') return `${date.getFullYear()}-${pad(date.getMonth() + 1)}`;
  if (period === 'year') return String(date.getFullYear());
  return '';
}

function dateOfKey(period, key) {
  if (period === 'month') {
    const [year, month] = key.split('-').map(Number);
    return new Date(year, month - 1, 1);
  }
  if (period === 'year') return new Date(Number(key), 0, 1);
  // Monday of an ISO week: 4 January is always in week 1.
  const [year, week] = key.split('-W').map(Number);
  const fourth = new Date(year, 0, 4);
  const monday = new Date(year, 0, 4 - ((fourth.getDay() + 6) % 7) + (week - 1) * 7);
  return monday;
}

function stepKey(period, key, step) {
  const date = dateOfKey(period, key);
  if (period === 'week') date.setDate(date.getDate() + step * 7);
  else if (period === 'month') date.setMonth(date.getMonth() + step);
  else date.setFullYear(date.getFullYear() + step);
  return keyOfDate(period, date);
}

function earliestKey(period) {
  const months = state.index?.months || [];
  if (!months.length) return null;
  const oldest = months[months.length - 1].key;
  if (period === 'month') return oldest;
  if (period === 'year') return oldest.slice(0, 4);
  return keyOfDate('week', dateOfKey('month', oldest));
}

function syncStepper(label) {
  $('[data-stats-label]').textContent = label;
  const prev = $('[data-stats-step="-1"]');
  const next = $('[data-stats-step="1"]');
  if (state.period === 'all') {
    prev.disabled = true;
    next.disabled = true;
    return;
  }
  const earliest = earliestKey(state.period);
  prev.disabled = !earliest || dateOfKey(state.period, state.key) <= dateOfKey(state.period, earliest);
  next.disabled = dateOfKey(state.period, state.key) >= dateOfKey(state.period, keyOfDate(state.period, new Date()));
}

function failure(message, action) {
  return `<p class="st-none">${escapeHtml(message)} <button type="button" class="btn btn--ghost btn--sm" data-stats-retry="${action}">Try again</button></p>`;
}

// ── Recaps ────────────────────────────────────────────────────────────────────

function shelfCard(entry, kind) {
  const tags = [];
  if (entry.so_far) tags.push('so far');
  if (entry.partial) tags.push('partial');
  const note = tags.length ? tags.join(', ') : plural(entry.plays, 'play');
  return `<button type="button" class="st-shelf-card${kind === 'year' ? ' st-shelf-card--year' : ''}" data-action="open-recap" data-kind="${kind}" data-key="${escapeHtml(entry.key)}">
    <strong>${escapeHtml(entry.label)}</strong><span>${escapeHtml(note)}</span>
  </button>`;
}

function renderHero(index, recap) {
  const hero = $('[data-stats-hero]');
  if (!recap) {
    const only = index.months[0];
    hero.innerHTML = `<div>
      <h2 class="st-hero-title">${escapeHtml(only.label)}</h2>
      <p class="st-hero-text">Your first month is still going: ${plural(only.plays, 'play')} so far.</p>
      <button type="button" class="btn" data-action="open-recap" data-kind="month" data-key="${escapeHtml(only.key)}">Play your recap so far</button>
    </div>`;
    return;
  }
  const top = recap.top.artists[0];
  const sentence = `${plural(recap.totals.plays, 'play')} and about ${duration(recap.totals.seconds)} of music${top ? `, with ${top.name} on top` : ''}.`;
  const sleeves = recap.top.albums.slice(0, 3).map(album => art(album.image, album.title)).join('');
  hero.innerHTML = `
    <div>
      <h2 class="st-hero-title">${escapeHtml(recap.label)}</h2>
      <p class="st-hero-text">${escapeHtml(sentence)}</p>
      <button type="button" class="btn" data-action="open-recap" data-kind="month" data-key="${escapeHtml(recap.key)}">Play your recap</button>
    </div>
    <div class="st-sleeves" aria-hidden="true">${sleeves}</div>`;
}

async function loadRecaps() {
  const { ok, data } = await fetchJSON(`/api/stats/recaps?tz=${encodeURIComponent(tz)}`);
  const hero = $('[data-stats-hero]');
  if (!ok) {
    hero.innerHTML = failure(data?.error || 'Your recaps could not be loaded.', 'recaps');
    return null;
  }
  state.index = data;
  const empty = !data.months.length;
  $('[data-stats-empty]').hidden = !empty;
  document.querySelector('.st-recaps').hidden = empty;
  $$('[data-stats-content]').forEach(el => { el.hidden = empty; });
  if (empty) return data;

  const latest = data.latest_complete;
  let recap = null;
  if (latest) {
    const response = await fetchJSON(`/api/stats/recap?type=month&key=${encodeURIComponent(latest)}&tz=${encodeURIComponent(tz)}`);
    if (response.ok) recap = response.data;
  }
  renderHero(data, recap);

  const shelf = $('[data-stats-shelf]');
  const months = data.months.filter(entry => entry.key !== recap?.key).map(entry => shelfCard(entry, 'month'));
  const years = data.years.map(entry => shelfCard(entry, 'year'));
  shelf.innerHTML = [...months, ...years].join('');
  shelf.hidden = !months.length && !years.length;
  return data;
}

// ── Period charts ─────────────────────────────────────────────────────────────

function renderTotals(data) {
  const { totals, coverage } = data;
  const figures = [
    ['Estimated listening', duration(totals.seconds)],
    ['Plays', count(totals.plays)],
    ['Artists', count(totals.artists)],
    ['Albums', count(totals.albums)],
    ['Tracks', count(totals.tracks)],
  ];
  $('[data-stats-totals]').innerHTML = figures.map(([label, value]) => `<div><dt>${label}</dt><dd>${escapeHtml(value)}</dd></div>`).join('');
  const note = $('[data-stats-coverage]');
  note.hidden = coverage.length_pct >= 100;
  note.textContent = note.hidden ? '' : `Track lengths are known for ${coverage.length_pct}% of these plays, so the real time is higher.`;
}

function renderRank(kind, rows) {
  const list = $(`[data-stats-top="${kind}"]`);
  if (!rows.length) {
    list.innerHTML = '<li class="st-none">No plays in this period.</li>';
    return;
  }
  const entity = { artists: 'artist', albums: 'album', tracks: 'track' }[kind];
  const max = rows[0].plays || 1;
  list.innerHTML = rows.map((row, i) => {
    const name = row.name || row.title;
    const play = row.deezer_track_id ? playButton(row.deezer_track_id, `Play a preview of ${name}`) : '';
    return `<li class="st-row st-row--link" data-stats-entity="${entity}" data-id="${row.id}">
      <span class="st-rank-n">${i + 1}</span>
      ${art(row.image, name)}
      <span class="st-row-main">
        <button type="button" class="st-row-name" title="${escapeHtml(name)}">${escapeHtml(name)}</button>
        ${row.artist ? `<span class="st-row-sub">${escapeHtml(row.artist)}</span>` : ''}
        <span class="st-bar" style="width:${Math.max(2, (row.plays / max) * 100)}%"></span>
      </span>
      <span class="st-row-value">${count(row.plays)}${play}</span>
    </li>`;
  }).join('');
}

function renderGenres(data) {
  const list = $('[data-stats-genres]');
  const note = $('[data-stats-genre-note]');
  note.textContent = data.totals.plays && data.coverage.genre_pct < 100 ? `Known for ${data.coverage.genre_pct}% of plays, and filling in as Deezer is checked.` : '';
  if (!data.genres.length) {
    list.innerHTML = '<li class="st-none">No genres known for this period yet.</li>';
    return;
  }
  const max = data.genres[0].plays || 1;
  list.innerHTML = data.genres.slice(0, 8).map(genre => `<li class="st-genre">
    <div class="st-genre-top"><span>${escapeHtml(genre.name)}</span><span>${Math.round(genre.share * 100)}%, ${duration(genre.seconds)}</span></div>
    <span class="st-bar" style="width:${Math.max(2, (genre.plays / max) * 100)}%"></span>
  </li>`).join('');
}

function renderHabits({ heatmap, busiest_day: busiest, longest_streak: streak }) {
  const host = $('[data-stats-heatmap]');
  const note = $('[data-stats-habits-note]');
  const max = Math.max(0, ...heatmap.flat());
  if (!max) {
    note.textContent = '';
    host.innerHTML = '<p class="st-none">No plays in this period.</p>';
    return;
  }
  const parts = [`Busiest day: ${dateFormat.format(new Date(`${busiest.date}T12:00:00`))}, ${plural(busiest.plays, 'play')}.`];
  if (streak.days > 1) parts.push(`Longest streak: ${count(streak.days)} days in a row.`);
  note.textContent = parts.join(' ');

  let peak = { day: 0, hour: 0, plays: 0 };
  let cells = '<span></span>';
  for (let hour = 0; hour < 24; hour++) {
    cells += `<span class="st-heat-axis">${hour % 6 === 0 ? `${pad(hour)}h` : ''}</span>`;
  }
  heatmap.forEach((hours, day) => {
    cells += `<span class="st-heat-day">${DAYS[day]}</span>`;
    hours.forEach((plays, hour) => {
      if (plays > peak.plays) peak = { day, hour, plays };
      const level = plays ? Math.round(15 + (plays / max) * 85) : 0;
      const attrs = plays ? ` data-level style="--level:${level}"` : '';
      cells += `<span class="st-heat-cell"${attrs} title="${DAYS[day]} ${pad(hour)}:00, ${plural(plays, 'play')}"></span>`;
    });
  });
  host.innerHTML = `<div class="st-heat" role="img" aria-label="Plays by weekday and hour. Most plays: ${DAYS[peak.day]} at ${pad(peak.hour)}:00, ${plural(peak.plays, 'play')}.">${cells}</div>
    <div class="st-heat-legend" aria-hidden="true"><span>Fewer</span><span class="st-heat-scale"></span><span>More</span></div>`;
}

async function loadOverview() {
  const params = new URLSearchParams({ period: state.period, key: state.key, tz });
  const { ok, data } = await fetchJSON(`/api/stats/overview?${params}`);
  if (!ok) {
    $('[data-stats-totals]').innerHTML = failure(data?.error || 'These stats could not be loaded.', 'overview');
    return;
  }
  // A slower answer for a period you already left must not replace the new one.
  if (data.period !== state.period || data.key !== state.key) return;
  syncStepper(data.label);
  renderTotals(data);
  for (const kind of ['artists', 'albums', 'tracks']) renderRank(kind, data.top[kind]);
  renderGenres(data);
  renderHabits(data.habits);
}

// ── Recent plays ──────────────────────────────────────────────────────────────

async function loadPlays() {
  const host = $('[data-stats-plays]');
  const pager = $('[data-stats-pager]');
  const params = new URLSearchParams({ q: state.query, page: state.page });
  const asked = params.toString();
  const { ok, data } = await fetchJSON(`/api/stats/plays?${params}`);
  if (asked !== new URLSearchParams({ q: state.query, page: state.page }).toString()) return;
  if (!ok) {
    host.innerHTML = failure(data?.error || 'Your plays could not be loaded.', 'plays');
    pager.innerHTML = '';
    return;
  }
  if (!data.plays.length) {
    host.innerHTML = `<p class="st-none">${state.query ? 'No plays match this search.' : 'No plays yet.'}</p>`;
    pager.innerHTML = '';
    return;
  }
  host.innerHTML = `<table class="table">
    <thead><tr><th>Played</th><th>Title</th><th>Artist</th><th>Album</th></tr></thead>
    <tbody>${data.plays.map(play => `<tr>
      <td>${escapeHtml(dateTimeFormat.format(new Date(play.listened_at * 1000)))}</td>
      <td><button type="button" class="st-row-name" data-stats-entity="track" data-id="${play.track_id}">${escapeHtml(play.title)}</button></td>
      <td>${escapeHtml(play.artist)}</td>
      <td>${escapeHtml(play.album || '')}</td>
    </tr>`).join('')}</tbody>
  </table>`;
  pager.innerHTML = `<span>Page ${count(data.page)} of ${count(data.pages)}, ${plural(data.total, 'play')}</span>
    <button type="button" class="btn btn--ghost btn--sm" data-stats-page="${data.page - 1}" ${data.page <= 1 ? 'disabled' : ''}>Newer</button>
    <button type="button" class="btn btn--ghost btn--sm" data-stats-page="${data.page + 1}" ${data.page >= data.pages ? 'disabled' : ''}>Older</button>`;
}

// ── Details ───────────────────────────────────────────────────────────────────

function detailHtml(data) {
  const max = Math.max(1, ...data.by_month.map(month => month.plays));
  const months = data.by_month.map(month => {
    const [year, m] = month.key.split('-').map(Number);
    return `<li class="st-month"><span>${escapeHtml(monthFormat.format(new Date(Date.UTC(year, m - 1, 1))))}</span>
      <span class="st-bar" style="width:${Math.max(2, (month.plays / max) * 100)}%"></span><span>${count(month.plays)}</span></li>`;
  }).join('');
  const tracks = data.top_tracks.length ? `<h3 class="st-detail-heading">Top tracks</h3>
    <ol class="st-rank">${data.top_tracks.map((track, i) => `<li class="st-row" style="grid-template-columns:1.4em minmax(0,1fr) auto">
      <span class="st-rank-n">${i + 1}</span>
      <span class="st-row-main"><span class="st-row-name">${escapeHtml(track.title)}</span>${data.kind === 'artist' ? '' : `<span class="st-row-sub">${escapeHtml(track.artist)}</span>`}</span>
      <span class="st-row-value">${count(track.plays)}</span>
    </li>`).join('')}</ol>` : '';
  return `<header class="detail-head">
      <div>
        <h2 class="detail-title">${escapeHtml(data.name)}</h2>
        ${data.artist ? `<p class="detail-sub">${escapeHtml(data.artist)}</p>` : ''}
      </div>
    </header>
    <dl class="st-detail-figures">
      <div><dt>Plays</dt><dd>${count(data.plays)}</dd></div>
      <div><dt>Estimated listening</dt><dd>${duration(data.seconds)}</dd></div>
      <div><dt>First listen</dt><dd>${data.first_play ? escapeHtml(dateFormat.format(new Date(data.first_play * 1000))) : '-'}</dd></div>
      <div><dt>Last listen</dt><dd>${data.last_play ? escapeHtml(dateFormat.format(new Date(data.last_play * 1000))) : '-'}</dd></div>
    </dl>
    <h3 class="st-detail-heading">Plays by month</h3>
    <ol class="st-months">${months}</ol>
    ${tracks}`;
}

async function openEntity(drawer, kind, id) {
  drawer.open({ html: '<p class="muted">Loading…</p>', label: 'Details' });
  const { ok, data } = await fetchJSON(`/api/stats/${kind}/${encodeURIComponent(id)}?tz=${encodeURIComponent(tz)}`);
  if (!ok) {
    drawer.open({ html: `<p class="st-none">${escapeHtml(data?.error || 'These details could not be loaded.')}</p>`, label: 'Details' });
    return;
  }
  drawer.open({ html: detailHtml(data), label: data.name });
}

// ── Wiring ────────────────────────────────────────────────────────────────────

async function refresh() {
  await loadRecaps();
  if (state.index?.months.length) {
    await Promise.all([loadOverview(), loadPlays()]);
  }
}

function setPeriod(period) {
  state.period = period;
  state.key = keyOfDate(period, new Date());
  $$('[data-stats-period]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.statsPeriod === period)));
  loadOverview();
}

export function initStats(drawer) {
  const root = document.querySelector('[data-stats]');
  if (!root) return;
  state.key = keyOfDate(state.period, new Date());

  // A cover that fails to load leaves the initials showing.
  root.addEventListener('error', event => {
    if (event.target.matches?.('[data-stats-img]')) event.target.remove();
  }, true);

  on(root, 'click', '[data-stats-period]', (_, button) => setPeriod(button.dataset.statsPeriod));
  on(root, 'click', '[data-stats-step]', (_, button) => {
    if (button.disabled) return;
    state.key = stepKey(state.period, state.key, Number(button.dataset.statsStep));
    loadOverview();
  });
  on(root, 'click', '[data-stats-entity]', (event, el) => {
    if (event.target.closest('[data-play-track]')) return;
    openEntity(drawer, el.dataset.statsEntity, el.dataset.id);
  });
  on(root, 'click', '[data-stats-page]', (_, button) => {
    state.page = Number(button.dataset.statsPage);
    loadPlays();
  });
  on(root, 'click', '[data-stats-retry]', (_, button) => {
    const action = button.dataset.statsRetry;
    if (action === 'plays') loadPlays();
    else if (action === 'overview') loadOverview();
    else refresh();
  });
  $('[data-stats-search]').addEventListener('input', event => {
    clearTimeout(state.searchTimer);
    state.searchTimer = setTimeout(() => {
      state.query = event.target.value.trim();
      state.page = 1;
      loadPlays();
    }, 250);
  });

  onViewShown(name => {
    if (name === 'stats') refresh();
  });
}
