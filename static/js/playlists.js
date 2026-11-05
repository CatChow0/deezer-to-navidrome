// Playlists: tiles in the dashboard, and the detail drawer with match
// breakdown, scans, downloads, automation and the track table.

import { armed, escapeHtml, explicitMark, fetchJSON, on, toast } from './core.js';
import { onTaskRow, runServerTask } from './activity.js';
import { queueDownload } from './downloads.js';
import { playButton } from './player.js';
import { automationChips, automationSection, bindAutomationSection, settingsFromTile } from './automation.js';

let drawer = null;
let openId = null;

// playlistId → Map(number → row), kept as the source of truth for the table.
const rowsByPlaylist = new Map();
// playlistId → summary of a playlist imported from another platform (source, truncated…).
const xpByPlaylist = new Map();

const tileOf = id => document.querySelector(`.tile[data-playlist-id="${CSS.escape(id)}"]`);

// ── Rows ──────────────────────────────────────────────────────────────────────

function matchState(row) {
  if (row.matched === true) return 'true';
  if (row.matched === false) return 'false';
  return 'none';
}

const STATUS = {
  true: { dot: 'dot--ok', label: 'In library' },
  false: { dot: 'dot--miss', label: 'Missing' },
  none: { dot: '', label: 'Not checked' },
};

// Imported tracks without a Deezer track have an ID such as "src:sp:…":
// nothing to play or download for them.
const isDeezerId = id => /^\d+$/.test(String(id ?? ''));

// Imported tracks whose Deezer match is worth a look: unsure, or none at all.
function needsReview(row) {
  if (!row.xp) return false;
  return row.xp.status === 'uncertain' || (!row.xp.on_deezer && row.xp.status !== 'pending');
}

function xpChip(row) {
  const { status, on_deezer: onDeezer } = row.xp;
  if (status === 'pending') return ' <span class="chip">Finding on Deezer…</span>';
  if (!onDeezer) {
    const how = status === 'manual' ? 'Marked by hand' : 'No close enough track on Deezer';
    return ` <span class="chip chip--miss" title="${how}">Not on Deezer</span>`;
  }
  if (status === 'uncertain') return ' <span class="chip chip--partial" title="The closest Deezer track, but not a sure match: check it with Find on Deezer">Review</span>';
  if (status === 'manual') return ' <span class="chip chip--info" title="Deezer track picked by hand, kept by every sync">Picked by hand</span>';
  return '';
}

// Letters and digits only: "Dreams (2004 Remaster)" and "Dreams - 2004 Remaster" are the same name.
const plainName = text => String(text || '').toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '');

// The track as the other platform names it, when Deezer names it differently.
function xpSourceLine(row, playlistId) {
  const source = `${row.xp.source_artist} - ${row.xp.source_title}`;
  if (!row.xp.on_deezer || plainName(source) === plainName(row.deezer_name)) return '';
  const name = xpByPlaylist.get(playlistId)?.source_name || 'Source';
  return `<span class="xp-source">${escapeHtml(name)}: ${escapeHtml(source)}</span>`;
}

function actionsCell(row) {
  if (!row.track_id) return '';
  const find = row.xp
    ? `<button type="button" class="btn btn--ghost btn--sm" data-action="xp-find" data-number="${escapeHtml(row.number)}" title="Pick the Deezer track of this song by hand">Find on Deezer</button>`
    : '';
  const fix = row.matched === null || row.matched === undefined
    ? ''
    : `<button type="button" class="btn btn--ghost btn--sm" data-action="fix-match" data-number="${escapeHtml(row.number)}" title="Pick the right file, or mark the track as missing">Fix</button>`;
  if (row.matched === true || !isDeezerId(row.track_id)) return `${find} ${fix}`;
  if (row.downloaded) return `<span class="dl-mark">Downloaded</span> ${find} ${fix}`;
  return `<button type="button" class="btn btn--ghost btn--sm dl-btn" data-action="download-track" data-track-id="${escapeHtml(row.track_id)}">Download</button> ${find} ${fix}`;
}

function rowHtml(row) {
  const state = matchState(row);
  const status = STATUS[state];
  const manual = row.manual ? ' <span class="chip chip--info" title="Set by hand, kept by every scan">Manual</span>' : '';
  const name = row.xp ? `${escapeHtml(row.deezer_name)}${xpChip(row)}${xpSourceLine(row, openId)}` : escapeHtml(row.deezer_name);
  return `
    <tr data-number="${escapeHtml(row.number)}" data-matched="${state}" data-review="${needsReview(row)}" data-track-id="${escapeHtml(row.track_id ?? '')}">
      <td class="num">${escapeHtml(row.number)}</td>
      <td class="track-name">${name}</td>
      <td class="track-match">${row.matched === true ? escapeHtml(row.source_name || '') : ''}${manual}</td>
      <td><span class="track-status"><span class="dot ${status.dot}"></span>${status.label}</span></td>
      <td class="actions">${isDeezerId(row.track_id) ? playButton(row.track_id, `Play a preview of ${row.deezer_name}`) : ''} ${actionsCell(row)}</td>
    </tr>
  `;
}

// ── Finding the Deezer track of an imported song by hand ──────────────────────

function formatSeconds(seconds) {
  if (!seconds) return '';
  return `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, '0')}`;
}

function xpResultsHtml(results, row) {
  if (!results.length) return '<p class="muted">Nothing on Deezer looks like this. Try other words.</p>';
  return results.map(item => {
    const current = String(item.id) === String(row.track_id);
    const meta = [item.artist, item.album, formatSeconds(item.duration)].filter(Boolean).join(', ');
    return `
      <div class="fix-result xp-result">
        ${item.cover ? `<img class="xp-cover" src="${escapeHtml(item.cover)}" alt="" loading="lazy">` : '<span class="xp-cover"></span>'}
        <div>
          <strong>${escapeHtml(item.title)}${explicitMark(item)}</strong>
          <span class="muted">${escapeHtml(meta)}</span>
        </div>
        ${playButton(item.id, `Play a preview of ${item.artist} - ${item.title}`)}
        <button type="button" class="btn btn--ghost btn--sm" data-action="xp-use" data-deezer-id="${escapeHtml(item.id)}" ${current ? 'disabled' : ''}>${current ? 'In use' : 'Use this track'}</button>
      </div>
    `;
  }).join('');
}

async function searchDeezerCandidates(panel, query, row) {
  const list = panel.querySelector('[data-xp-results]');
  list.innerHTML = '<p class="muted">Searching Deezer…</p>';
  const { data } = await fetchJSON(`/search?q=${encodeURIComponent(query)}&type=track`);
  if (!data?.ok) {
    list.innerHTML = `<p class="muted">${escapeHtml(data?.error || 'The search failed.')}</p>`;
    return;
  }
  list.innerHTML = xpResultsHtml(data.results || [], row);
}

function openXpPanel(number) {
  const row = rowsByPlaylist.get(openId)?.get(Number(number));
  const tr = drawer.content.querySelector(`[data-tracks] tr[data-number="${number}"]`);
  if (!row?.xp || !tr) return;

  const alreadyOpen = tr.nextElementSibling?.classList.contains('xp-row');
  closeFixPanels();
  if (alreadyOpen) return;

  const { source_artist: artist, source_title: title, source_duration: duration, status, on_deezer: onDeezer } = row.xp;
  const query = [String(artist || '').split(',')[0], title].filter(Boolean).join(' ');
  const length = duration ? `, ${formatSeconds(duration)}` : '';
  tr.insertAdjacentHTML('afterend', `
    <tr class="fix-row xp-row" data-matched="${matchState(row)}" data-review="${needsReview(row)}" data-fix-number="${escapeHtml(row.number)}">
      <td colspan="5">
        <div class="fix-panel">
          <p class="xp-panel-title">Deezer track for <strong>${escapeHtml(artist)} - ${escapeHtml(title)}</strong>${escapeHtml(length)}</p>
          <form class="fix-search" data-xp-search>
            <input type="search" name="q" value="${escapeHtml(query)}" aria-label="Search Deezer">
            <button type="submit" class="btn btn--ghost btn--sm">Search</button>
          </form>
          <div class="fix-results" data-xp-results data-play-queue></div>
          <div class="fix-actions">
            ${onDeezer || status !== 'manual' ? '<button type="button" class="btn btn--ghost btn--sm" data-action="xp-none">Not on Deezer</button>' : ''}
            ${status === 'manual' ? '<button type="button" class="btn btn--ghost btn--sm" data-action="xp-auto">Back to automatic matching</button>' : ''}
            <button type="button" class="btn btn--ghost btn--sm" data-action="fix-close">Cancel</button>
          </div>
        </div>
      </td>
    </tr>
  `);
  const panel = tr.nextElementSibling;
  panel.querySelector('input').focus();
  searchDeezerCandidates(panel, query, row);
}

async function saveXpPick(button, deezerId) {
  const panel = button.closest('.fix-row');
  const number = Number(panel.dataset.fixNumber);
  const playlistId = openId;
  const row = rowsByPlaylist.get(playlistId)?.get(number);
  if (!row?.xp) return;

  button.disabled = true;
  const { data } = await fetchJSON(`/playlist/${playlistId}/source-match`, { json: { key: row.xp.key, deezer_id: deezerId } });
  button.disabled = false;
  if (!data?.ok) {
    toast(data?.error || 'The Deezer track was not saved', { tone: 'error' });
    return;
  }
  if (data.xp) xpByPlaylist.set(playlistId, data.xp);
  closeFixPanels();
  applyRowUpdate(playlistId, data.row);
  const message = deezerId === null ? 'Marked as not on Deezer'
    : deezerId === 'auto' ? 'Back to the automatic Deezer match'
      : 'Deezer track saved and playlist file updated';
  toast(message, { tone: 'ok' });
}

// ── Fixing a match by hand ────────────────────────────────────────────────────

function closeFixPanels() {
  drawer.content.querySelectorAll('.fix-row').forEach(el => el.remove());
}

function fixResultsHtml(results) {
  if (!results.length) return '<p class="muted">No file in the library looks like this. Try other words.</p>';
  return results.map(item => `
    <div class="fix-result">
      <div>
        <strong>${escapeHtml(item.artist ? `${item.artist} - ${item.title}` : item.title)}</strong>
        <span class="muted">${escapeHtml([item.album, item.file].filter(Boolean).join(', '))}</span>
      </div>
      <button type="button" class="btn btn--ghost btn--sm" data-action="fix-use" data-path="${escapeHtml(item.path)}">Use this file</button>
    </div>
  `).join('');
}

async function searchFixCandidates(panel, query) {
  const list = panel.querySelector('[data-fix-results]');
  list.innerHTML = '<p class="muted">Searching the library…</p>';
  const { data } = await fetchJSON(`/api/library/search?q=${encodeURIComponent(query)}`);
  list.innerHTML = fixResultsHtml(data?.results || []);
}

function openFixPanel(number) {
  const row = rowsByPlaylist.get(openId)?.get(Number(number));
  const tr = drawer.content.querySelector(`[data-tracks] tr[data-number="${number}"]`);
  if (!row || !tr) return;

  const alreadyOpen = tr.nextElementSibling?.classList.contains('fix-row');
  closeFixPanels();
  if (alreadyOpen) return;

  const query = [row.deezer_artist, row.deezer_title].filter(Boolean).join(' ') || row.deezer_name;
  const canMarkMissing = !(row.matched === false && row.manual);
  tr.insertAdjacentHTML('afterend', `
    <tr class="fix-row" data-matched="${matchState(row)}" data-fix-number="${escapeHtml(row.number)}">
      <td colspan="5">
        <div class="fix-panel">
          <form class="fix-search" data-fix-search>
            <input type="search" name="q" value="${escapeHtml(query)}" aria-label="Search the library">
            <button type="submit" class="btn btn--ghost btn--sm">Search</button>
          </form>
          <div class="fix-results" data-fix-results></div>
          <div class="fix-actions">
            ${canMarkMissing ? '<button type="button" class="btn btn--ghost btn--sm" data-action="fix-missing">Not in my library</button>' : ''}
            ${row.manual ? '<button type="button" class="btn btn--ghost btn--sm" data-action="fix-auto">Back to automatic matching</button>' : ''}
            <button type="button" class="btn btn--ghost btn--sm" data-action="fix-close">Cancel</button>
          </div>
        </div>
      </td>
    </tr>
  `);
  const panel = tr.nextElementSibling;
  panel.querySelector('input').focus();
  searchFixCandidates(panel, query);
}

async function saveFix(button, body) {
  const panel = button.closest('.fix-row');
  const number = Number(panel.dataset.fixNumber);
  const playlistId = openId;
  const row = rowsByPlaylist.get(playlistId)?.get(number);
  if (!row) return;

  button.disabled = true;
  const { data } = await fetchJSON(`/playlist/${playlistId}/match`, { json: { track_id: row.track_id, ...body } });
  button.disabled = false;
  if (!data?.ok) {
    toast(data?.error || 'The match was not saved', { tone: 'error' });
    return;
  }
  closeFixPanels();
  applyRowUpdate(playlistId, data.row);
  toast(
    body.mode === 'auto' ? 'Back to automatic matching. The next scan will match it again.' : 'Match saved and playlist file updated',
    { tone: 'ok' },
  );
}

function counts(playlistId) {
  const rows = rowsByPlaylist.get(playlistId);
  const c = { found: 0, missing: 0, unchecked: 0, total: 0 };
  if (!rows) return c;
  for (const row of rows.values()) {
    c.total++;
    if (row.matched === true) c.found++;
    else if (row.matched === false) c.missing++;
    else c.unchecked++;
  }
  return c;
}

function renderBreakdown(playlistId) {
  const host = drawer.content.querySelector('[data-breakdown]');
  if (!host || openId !== playlistId) return;
  const c = counts(playlistId);
  if (!c.total) {
    host.innerHTML = '';
    return;
  }
  host.innerHTML = `
    <div class="breakdown-bar" role="img" aria-label="${c.found} in library, ${c.missing} missing, ${c.unchecked} not checked">
      <span class="is-ok" style="flex-grow:${c.found}"></span>
      <span class="is-miss" style="flex-grow:${c.missing}"></span>
      <span class="is-idle" style="flex-grow:${c.unchecked}"></span>
    </div>
    <div class="breakdown-legend">
      <span><span class="dot dot--ok"></span><b>${c.found}</b> in library</span>
      <span><span class="dot dot--miss"></span><b>${c.missing}</b> missing</span>
      ${c.unchecked ? `<span><span class="dot"></span><b>${c.unchecked}</b> not checked</span>` : ''}
    </div>
  `;
}

const FILTER_EMPTY = {
  missing: 'Nothing is missing from your library.',
  found: 'None of these tracks are in your library yet.',
  unchecked: 'Every track has been checked.',
  review: 'Nothing to review: every track has a sure Deezer match.',
};

// The attribute a row needs to stay visible under each filter.
const FILTER_ATTR = {
  missing: 'data-matched="false"',
  found: 'data-matched="true"',
  unchecked: 'data-matched="none"',
  review: 'data-review="true"',
};

// Shows a message when the active filter hides every row.
function syncFilterEmpty(tbody) {
  tbody.querySelector('.filter-empty')?.remove();
  const filter = tbody.dataset.filter;
  if (!FILTER_EMPTY[filter]) return;
  const attr = FILTER_ATTR[filter];
  if (tbody.querySelector(`tr[data-number][${attr}]`)) return;
  if (!tbody.querySelector('tr[data-number]')) return;
  tbody.insertAdjacentHTML('beforeend', `<tr class="filter-empty" ${attr}><td colspan="5" class="empty">${FILTER_EMPTY[filter]}</td></tr>`);
}

// Imported playlists: how many tracks were found on Deezer, and what to check.
function renderXpSummary(playlistId) {
  const host = drawer.content.querySelector('[data-xp-summary]');
  const info = xpByPlaylist.get(playlistId);
  if (!host || openId !== playlistId || !info) return;
  const c = { found: 0, review: 0, missing: 0, pending: 0 };
  for (const row of rowsByPlaylist.get(playlistId)?.values() || []) {
    if (!row.xp) continue;
    if (row.xp.status === 'pending') c.pending++;
    else if (!row.xp.on_deezer) c.missing++;
    else if (row.xp.status === 'uncertain') c.review++;
    else c.found++;
  }
  const truncated = info.truncated
    ? `<p class="xp-note">${escapeHtml(info.source_name)} only shows the first 100 tracks of a public playlist. Import an <a href="https://exportify.app" target="_blank" rel="noopener">Exportify</a> CSV of it to get them all.</p>`
    : '';
  host.innerHTML = `
    <div class="breakdown-legend xp-legend">
      <span><b>${c.found + c.review}</b> found on Deezer</span>
      ${c.review ? `<span><span class="dot xp-dot--review"></span><b>${c.review}</b> to review</span>` : ''}
      ${c.missing ? `<span><span class="dot dot--miss"></span><b>${c.missing}</b> not on Deezer</span>` : ''}
      ${c.pending ? `<span><span class="dot"></span><b>${c.pending}</b> being found…</span>` : ''}
    </div>
    ${truncated}
  `;
}

function renderRows(playlistId) {
  const tbody = drawer.content.querySelector('[data-tracks]');
  if (!tbody || openId !== playlistId) return;
  const rows = [...(rowsByPlaylist.get(playlistId)?.values() || [])].sort((a, b) => a.number - b.number);
  tbody.innerHTML = rows.length
    ? rows.map(rowHtml).join('')
    : '<tr><td colspan="5" class="empty">This playlist has no tracks yet.</td></tr>';
  syncFilterEmpty(tbody);
}

function applyRowUpdate(playlistId, row) {
  if (!rowsByPlaylist.has(playlistId)) rowsByPlaylist.set(playlistId, new Map());
  const rows = rowsByPlaylist.get(playlistId);
  rows.set(Number(row.number), { ...rows.get(Number(row.number)), ...row, number: Number(row.number) });

  if (openId !== playlistId) return;
  const tr = drawer.content.querySelector(`[data-tracks] tr[data-number="${row.number}"]`);
  if (tr) tr.outerHTML = rowHtml(rows.get(Number(row.number)));
  const tbody = drawer.content.querySelector('[data-tracks]');
  if (tbody) syncFilterEmpty(tbody);
  renderBreakdown(playlistId);
  renderXpSummary(playlistId);
}

// Marks rows whose download finished in Deezer Downloader's queue.
async function refreshDownloadStateFromQueue(playlistId) {
  const { ok, data } = await fetchJSON('/deezer-dl/queue');
  if (!ok || !Array.isArray(data)) return;

  const finished = new Set();
  for (const item of data) {
    if (item.state !== 'mission accomplished' || typeof item.args !== 'string') continue;
    const m = item.args.match(/'track_id'\s*:\s*(\d+)/);
    if (m) finished.add(m[1]);
  }
  if (!finished.size) return;

  const rows = rowsByPlaylist.get(playlistId);
  let changed = false;
  for (const row of rows?.values() || []) {
    if (row.track_id && finished.has(String(row.track_id)) && !row.downloaded) {
      row.downloaded = true;
      changed = true;
    }
  }
  if (changed) renderRows(playlistId);
}

async function loadPreview(playlistId) {
  const tbody = drawer.content.querySelector('[data-tracks]');
  if (tbody) tbody.innerHTML = '<tr><td colspan="5" class="empty">Loading tracks…</td></tr>';

  const { data } = await fetchJSON(`/playlist/${playlistId}/preview`);
  if (openId !== playlistId) return;
  if (!data?.ok) {
    if (tbody) tbody.innerHTML = `<tr><td colspan="5" class="empty">${escapeHtml(data?.error || 'Could not load this playlist.')}</td></tr>`;
    return;
  }

  const rows = new Map();
  for (const row of data.playlist.rows || []) rows.set(Number(row.number), { ...row, number: Number(row.number) });
  rowsByPlaylist.set(playlistId, rows);
  if (data.playlist.xp) xpByPlaylist.set(playlistId, data.playlist.xp);
  renderRows(playlistId);
  renderBreakdown(playlistId);
  renderXpSummary(playlistId);
  refreshDownloadStateFromQueue(playlistId);
}

// ── Drawer ────────────────────────────────────────────────────────────────────

function drawerHtml(tile) {
  const id = tile.dataset.playlistId;
  const title = tile.dataset.title;
  const cover = tile.dataset.cover;
  const settings = settingsFromTile(tile);
  const imported = tile.dataset.kind === 'xp';
  const generated = tile.dataset.kind === 'auto';
  let kindLine = `Deezer playlist ${escapeHtml(id)}`;
  if (generated) kindLine = `Made for you. ${escapeHtml(tile.dataset.subtitle)}`;
  if (tile.dataset.kind === 'mix') kindLine = 'Mix made for you by Deezer, refreshed at each scan';
  if (imported) {
    kindLine = tile.dataset.source === 'spotify'
      ? `Spotify playlist matched to Deezer, synced at each scan. <a href="https://open.spotify.com/playlist/${escapeHtml(id.replace(/^xp-spotify-/, ''))}" target="_blank" rel="noopener">Open on Spotify</a>`
      : 'CSV import matched to Deezer';
  }

  return `
    <header class="detail-head">
      ${cover ? `<img class="detail-cover" src="${escapeHtml(cover)}" alt="">` : '<div class="detail-cover"></div>'}
      <div>
        <p class="detail-kind">${kindLine}</p>
        <h2 class="detail-title">${escapeHtml(title)}</h2>
        <div class="chips detail-chips" data-drawer-chips>${automationChips(id, settings)}</div>
        <div class="breakdown" data-breakdown></div>
        ${imported ? '<div class="xp-summary" data-xp-summary></div>' : ''}
        <div class="detail-actions" ${generated ? 'hidden' : ''}>
          <button type="button" class="btn" data-action="scan" data-mode="quick" title="Re-match only tracks that are missing or not checked yet">Quick scan</button>
          <button type="button" class="btn btn--ghost" data-action="scan" data-mode="full" title="Re-match every track from scratch">Full scan</button>
          <button type="button" class="btn btn--ghost" data-action="download-missing">Download missing</button>
          <span class="spacer"></span>
          <form method="post" action="${escapeHtml(tile.dataset.deleteUrl)}" data-delete-form>
            <button type="submit" class="btn btn--danger">Delete playlist</button>
          </form>
        </div>
      </div>
    </header>

    <section class="detail-section" ${generated ? 'hidden' : ''}>
      <h3 class="section-title">Automation</h3>
      ${automationSection(id, settings)}
    </section>

    <section class="detail-section">
      <div class="track-filter segmented" role="group" aria-label="Show tracks" ${generated ? 'hidden' : ''}>
        <button type="button" data-filter="all" aria-pressed="true">All</button>
        <button type="button" data-filter="missing" aria-pressed="false">Missing</button>
        <button type="button" data-filter="found" aria-pressed="false">In library</button>
        <button type="button" data-filter="unchecked" aria-pressed="false">Not checked</button>
        ${imported ? '<button type="button" data-filter="review" aria-pressed="false">To review</button>' : ''}
      </div>
      <div class="table-wrap" data-play-queue>
        <table class="table">
          <thead>
            <tr>
              <th class="num">#</th>
              <th>${generated ? 'Track' : 'Deezer track'}</th>
              <th>${generated ? 'File' : 'Matched file'}</th>
              <th>Status</th>
              <th class="actions"><span class="sr-only">Download</span></th>
            </tr>
          </thead>
          <tbody data-tracks data-filter="all"></tbody>
        </table>
      </div>
    </section>
  `;
}

function refreshChips(playlistId) {
  const tile = tileOf(playlistId);
  if (!tile) return;
  const settings = settingsFromTile(tile);
  const tileChips = tile.querySelector('[data-tile-chips]');
  if (tileChips) tileChips.innerHTML = automationChips(playlistId, settings);
  if (openId === playlistId) {
    const drawerChips = drawer.content.querySelector('[data-drawer-chips]');
    if (drawerChips) drawerChips.innerHTML = automationChips(playlistId, settings);
  }
}

function openPlaylist(playlistId) {
  const tile = tileOf(playlistId);
  if (!tile) return;
  openId = playlistId;

  drawer.open({
    html: drawerHtml(tile),
    label: tile.dataset.title,
    closeHandler: () => {
      openId = null;
    },
  });

  bindAutomationSection(drawer.content, playlistId, settings => {
    tile.dataset.autoScan = String(settings.enabled);
    tile.dataset.autoDownload = String(settings.download);
    tile.dataset.autoInterval = String(settings.interval);
    refreshChips(playlistId);
  });

  if (rowsByPlaylist.has(playlistId)) {
    renderRows(playlistId);
    renderBreakdown(playlistId);
    renderXpSummary(playlistId);
  }
  loadPreview(playlistId);
}

// ── Actions ───────────────────────────────────────────────────────────────────

async function startScan(playlistId, mode) {
  const title = tileOf(playlistId)?.dataset.title || playlistId;
  await runServerTask(`${mode === 'quick' ? 'Quick scan' : 'Full scan'}: ${title}`, `/playlist/${playlistId}/convert/start`, {
    json: { mode },
    playlistId,
  });
}

async function startDownloadMissing(playlistId) {
  const title = tileOf(playlistId)?.dataset.title || playlistId;
  const result = await runServerTask(`Download missing: ${title}`, `/playlist/${playlistId}/download-missing/start`, {
    logMode: 'replace',
    playlistId,
  });
  if (!result.error && openId === playlistId) loadPreview(playlistId);
}

// ── Wiring ────────────────────────────────────────────────────────────────────

export function initPlaylists(drawerApi) {
  drawer = drawerApi;

  document.querySelectorAll('.tile[data-playlist-id]').forEach(tile => refreshChips(tile.dataset.playlistId));

  on(document, 'click', '.tile[data-playlist-id]', (_, tile) => openPlaylist(tile.dataset.playlistId));

  const content = drawer.content;
  on(content, 'click', '[data-action="scan"]', (_, btn) => openId && startScan(openId, btn.dataset.mode));
  on(content, 'click', '[data-action="download-missing"]', () => openId && startDownloadMissing(openId));

  // Row updates from any scan: this page, another tab, or the scheduler.
  onTaskRow(({ task, row }) => {
    if (task.playlist_id) applyRowUpdate(String(task.playlist_id), row);
  });

  on(content, 'click', '[data-action="fix-match"]', (_, btn) => openFixPanel(btn.dataset.number));
  on(content, 'click', '[data-action="fix-close"]', () => closeFixPanels());
  on(content, 'click', '[data-action="fix-use"]', (_, btn) => saveFix(btn, { mode: 'file', path: btn.dataset.path }));
  on(content, 'click', '[data-action="fix-missing"]', (_, btn) => saveFix(btn, { mode: 'missing' }));
  on(content, 'click', '[data-action="fix-auto"]', (_, btn) => saveFix(btn, { mode: 'auto' }));
  content.addEventListener('submit', event => {
    const form = event.target.closest('[data-fix-search]');
    if (!form) return;
    event.preventDefault();
    searchFixCandidates(form.closest('.fix-row'), form.elements.q.value.trim());
  });

  on(content, 'click', '[data-action="xp-find"]', (_, btn) => openXpPanel(btn.dataset.number));
  on(content, 'click', '[data-action="xp-use"]', (_, btn) => saveXpPick(btn, btn.dataset.deezerId));
  on(content, 'click', '[data-action="xp-none"]', (_, btn) => saveXpPick(btn, null));
  on(content, 'click', '[data-action="xp-auto"]', (_, btn) => saveXpPick(btn, 'auto'));
  content.addEventListener('submit', event => {
    const form = event.target.closest('[data-xp-search]');
    if (!form) return;
    event.preventDefault();
    const panel = form.closest('.fix-row');
    const row = rowsByPlaylist.get(openId)?.get(Number(panel.dataset.fixNumber));
    if (row) searchDeezerCandidates(panel, form.elements.q.value.trim(), row);
  });

  on(content, 'click', '[data-action="download-track"]', (_, btn) => {
    const row = rowsByPlaylist.get(openId)?.get(Number(btn.closest('tr')?.dataset.number));
    queueDownload(btn, {
      url: `/deezer-dl/track/${encodeURIComponent(btn.dataset.trackId)}`,
      json: { playlist_id: openId },
      label: row?.deezer_name || '',
    });
  });

  on(content, 'click', '[data-filter]', (_, btn) => {
    const tbody = content.querySelector('[data-tracks]');
    if (!tbody || btn.tagName !== 'BUTTON') return;
    tbody.dataset.filter = btn.dataset.filter;
    syncFilterEmpty(tbody);
    btn.parentElement.querySelectorAll('[data-filter]').forEach(b => b.setAttribute('aria-pressed', String(b === btn)));
  });

  content.addEventListener('submit', event => {
    const form = event.target.closest('[data-delete-form]');
    if (!form) return;
    if (!armed(form.querySelector('button'), 'Click again to delete')) event.preventDefault();
  });

  const addForm = document.getElementById('add-playlist-form');
  addForm?.addEventListener('submit', () => {
    const btn = addForm.querySelector('button');
    btn.disabled = true;
    btn.textContent = 'Adding…';
  });

  // Choosing the file is enough: no second button to press.
  const importForm = document.getElementById('import-csv-form');
  importForm?.querySelector('input[type="file"]').addEventListener('change', event => {
    if (!event.target.files.length) return;
    const label = importForm.querySelector('label');
    label.lastChild.textContent = ' Importing…';
    label.classList.add('is-busy');
    importForm.submit();
  });

  // An import or a link added lands on its drawer: /?playlist=<id>.
  const wanted = new URLSearchParams(location.search).get('playlist');
  if (wanted && tileOf(wanted)) {
    openPlaylist(wanted);
    history.replaceState(history.state, '', location.pathname);
  }
}
