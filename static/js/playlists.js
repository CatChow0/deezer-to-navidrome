// Playlists: tiles in the dashboard, and the detail drawer with match
// breakdown, scans, downloads, automation and the track table.

import { armed, escapeHtml, fetchJSON, on } from './core.js';
import { runServerTask } from './activity.js';
import { queueDownload } from './downloads.js';
import { automationChips, automationSection, bindAutomationSection, settingsFromTile } from './automation.js';

let drawer = null;
let openId = null;

// playlistId → Map(number → row), kept as the source of truth for the table.
const rowsByPlaylist = new Map();

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

function downloadCell(row) {
  if (!row.track_id || row.matched === true) return '';
  if (row.downloaded) return '<span class="dl-mark">Sent to downloader</span>';
  return `<button type="button" class="btn btn--ghost btn--sm dl-btn" data-action="download-track" data-track-id="${escapeHtml(row.track_id)}">Download</button>`;
}

function rowHtml(row) {
  const state = matchState(row);
  const status = STATUS[state];
  return `
    <tr data-number="${escapeHtml(row.number)}" data-matched="${state}" data-track-id="${escapeHtml(row.track_id ?? '')}">
      <td class="num">${escapeHtml(row.number)}</td>
      <td class="track-name">${escapeHtml(row.deezer_name)}</td>
      <td class="track-match">${row.matched === true ? escapeHtml(row.source_name || '') : ''}</td>
      <td><span class="track-status"><span class="dot ${status.dot}"></span>${status.label}</span></td>
      <td class="actions">${downloadCell(row)}</td>
    </tr>
  `;
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
};

// Shows a message when the active filter hides every row.
function syncFilterEmpty(tbody) {
  tbody.querySelector('.filter-empty')?.remove();
  const filter = tbody.dataset.filter;
  if (!FILTER_EMPTY[filter]) return;
  const state = { missing: 'false', found: 'true', unchecked: 'none' }[filter];
  if (tbody.querySelector(`tr[data-matched="${state}"]`)) return;
  if (!tbody.querySelector('tr[data-number]')) return;
  tbody.insertAdjacentHTML('beforeend', `<tr class="filter-empty" data-matched="${state}"><td colspan="5" class="empty">${FILTER_EMPTY[filter]}</td></tr>`);
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
  renderRows(playlistId);
  renderBreakdown(playlistId);
  refreshDownloadStateFromQueue(playlistId);
}

// ── Drawer ────────────────────────────────────────────────────────────────────

function drawerHtml(tile) {
  const id = tile.dataset.playlistId;
  const title = tile.dataset.title;
  const cover = tile.dataset.cover;
  const settings = settingsFromTile(tile);

  return `
    <header class="detail-head">
      ${cover ? `<img class="detail-cover" src="${escapeHtml(cover)}" alt="">` : '<div class="detail-cover"></div>'}
      <div>
        <p class="detail-kind">Deezer playlist ${escapeHtml(id)}</p>
        <h2 class="detail-title">${escapeHtml(title)}</h2>
        <div class="chips detail-chips" data-drawer-chips>${automationChips(id, settings)}</div>
        <div class="breakdown" data-breakdown></div>
        <div class="detail-actions">
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

    <section class="detail-section">
      <h3 class="section-title">Automation</h3>
      ${automationSection(id, settings)}
    </section>

    <section class="detail-section">
      <div class="track-filter segmented" role="group" aria-label="Show tracks">
        <button type="button" data-filter="all" aria-pressed="true">All</button>
        <button type="button" data-filter="missing" aria-pressed="false">Missing</button>
        <button type="button" data-filter="found" aria-pressed="false">In library</button>
        <button type="button" data-filter="unchecked" aria-pressed="false">Not checked</button>
      </div>
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th class="num">#</th>
              <th>Deezer track</th>
              <th>Matched file</th>
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
  }
  loadPreview(playlistId);
}

// ── Actions ───────────────────────────────────────────────────────────────────

async function startScan(playlistId, mode) {
  const title = tileOf(playlistId)?.dataset.title || playlistId;
  await runServerTask(`${mode === 'quick' ? 'Quick scan' : 'Full scan'}: ${title}`, `/playlist/${playlistId}/convert/start`, {
    json: { mode },
    onRow: row => applyRowUpdate(playlistId, row),
  });
}

async function startDownloadMissing(playlistId) {
  const title = tileOf(playlistId)?.dataset.title || playlistId;
  const result = await runServerTask(`Download missing: ${title}`, `/playlist/${playlistId}/download-missing/start`, {
    logMode: 'replace',
    onRow: row => applyRowUpdate(playlistId, row),
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

  on(content, 'click', '[data-action="download-track"]', (_, btn) => {
    queueDownload(btn, { url: `/deezer-dl/track/${encodeURIComponent(btn.dataset.trackId)}` });
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
}
