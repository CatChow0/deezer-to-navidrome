// Duplicate review: run the scan, show groups per album with one column per
// folder, then quarantine or delete the files left unchecked.

import { armed, escapeHtml, fetchJSON, on, toast } from './core.js';
import { runServerTask } from './activity.js';

let modal = null;
const state = { report: null, selections: {} };

const $ = id => document.getElementById(id);

function setSummary(text) {
  const el = $('dedup-summary');
  if (el) el.textContent = text;
}

function setApplyEnabled(enabled) {
  document.querySelectorAll('[data-dedup-apply], [data-dedup-preset]').forEach(btn => {
    btn.disabled = !enabled;
  });
}

function defaultSelections(report) {
  const selections = {};
  for (const group of report.groups || []) selections[group.group_id] = new Set();

  const hints = report.keeper_hints || {};
  for (const [groupId, keepPaths] of Object.entries(hints)) {
    if (Array.isArray(keepPaths) && selections[groupId]) selections[groupId] = new Set(keepPaths);
  }
  for (const group of report.groups || []) {
    if (!hints[group.group_id] && group.keeper?.path_str) selections[group.group_id].add(group.keeper.path_str);
  }
  return selections;
}

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

function formatSize(bytes) {
  if (!bytes) return '—';
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDuration(seconds) {
  if (!seconds) return '—';
  return `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, '0')}`;
}

function summaryText(report) {
  const parts = [`${plural(report.group_count ?? 0, 'group')} to review`, plural(report.duplicate_file_count ?? 0, 'duplicate file')];
  const validated = (report.total_group_count ?? 0) - (report.group_count ?? 0);
  if (validated > 0) parts.push(`${validated} already reviewed`);
  if (report.ignored_group_count) parts.push(`${report.ignored_group_count} ignored`);
  return `${parts.join(', ')}. Checked files are kept.`;
}

function render() {
  const host = $('dedup-groups');
  const report = state.report;
  if (!host || !report) return;

  setSummary(summaryText(report));
  const albums = report.album_groups || [];
  setApplyEnabled(albums.length > 0);

  if (!albums.length) {
    host.innerHTML = '<p class="empty">No duplicates left to review.</p>';
    return;
  }

  host.innerHTML = albums.map(album => {
    const folders = new Set();
    const byTrack = {};
    let fileCount = 0;

    for (const group of album.tracks || []) {
      const track = group.identity?.base_title || 'Unknown';
      byTrack[track] = byTrack[track] || {};
      for (const folder of group.folders || []) {
        folders.add(folder.folder);
        byTrack[track][folder.folder] = (folder.entries || []).map(entry => ({
          entry,
          groupId: group.group_id,
          isKeeper: entry.path_str === group.keeper?.path_str,
        }));
      }
      fileCount += (group.entries || []).length;
    }

    const folderList = [...folders].sort();
    const trackList = Object.keys(byTrack).sort();

    return `
      <section class="dedup-album">
        <h3>${escapeHtml(album.artist || 'Unknown artist')}, ${escapeHtml(album.album || 'Unknown album')}</h3>
        <p>${plural(trackList.length, 'track')}, ${plural(fileCount, 'file')}</p>
        <div class="table-wrap">
          <table class="table dedup-table">
            <thead>
              <tr>
                <th>Track</th>
                ${folderList.map(folder => `
                  <th>
                    <div class="dedup-folder-head">
                      <span class="dedup-folder-path">${escapeHtml(folder)}</span>
                      <div>
                        <button type="button" class="btn btn--ghost btn--sm" data-folder-action="keep" data-folder="${escapeHtml(folder)}">Keep all</button>
                        <button type="button" class="btn btn--ghost btn--sm" data-folder-action="drop" data-folder="${escapeHtml(folder)}">Uncheck all</button>
                      </div>
                    </div>
                  </th>
                `).join('')}
              </tr>
            </thead>
            <tbody>
              ${trackList.map(track => `
                <tr>
                  <td class="dedup-track">${escapeHtml(track)}</td>
                  ${folderList.map(folder => `
                    <td>
                      ${(byTrack[track][folder] || []).map(({ entry, groupId, isKeeper }) => `
                        <label class="dedup-entry">
                          <input type="checkbox" data-group-id="${escapeHtml(groupId)}" data-path="${escapeHtml(entry.path_str)}" ${state.selections[groupId]?.has(entry.path_str) ? 'checked' : ''}>
                          <span class="dedup-entry-info">
                            <span class="dedup-entry-title">${entry.track_number ? `${String(entry.track_number).padStart(2, '0')}. ` : ''}${escapeHtml(entry.tag_title || entry.parsed_track_title || entry.stem_norm || 'Unknown')}</span>
                            <span class="dedup-entry-meta">${formatDuration(entry.duration)}, ${formatSize(entry.size)}, quality ${(entry.quality_score || 0).toFixed(1)}</span>
                          </span>
                          <span class="chip ${isKeeper ? 'chip--ok' : 'chip--miss'}">${isKeeper ? 'Best copy' : 'Duplicate'}</span>
                        </label>
                      `).join('')}
                    </td>
                  `).join('')}
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </section>
    `;
  }).join('');
}

async function loadReport() {
  const { data } = await fetchJSON('/dedup/report');
  if (!data?.ok) {
    state.report = null;
    setSummary(data?.error || 'No duplicate report yet. Run a scan to create one.');
    $('dedup-groups').innerHTML = '';
    setApplyEnabled(false);
    return false;
  }
  state.report = data.report;
  state.selections = defaultSelections(data.report);
  render();
  return true;
}

export async function openLastReport() {
  modal.open();
  setSummary('Loading the last report…');
  await loadReport();
}

export async function startScan() {
  modal.open();
  state.report = null;
  setSummary('Scanning the library for duplicates…');
  $('dedup-groups').innerHTML = '';
  setApplyEnabled(false);
  document.querySelectorAll('[data-action="dedup-scan"]').forEach(btn => (btn.disabled = true));

  const result = await runServerTask('Duplicate scan', '/dedup/start', {
    onStatus: payload => {
      if (!state.report && payload.message) setSummary(payload.message);
    },
    onEvent: payload => {
      if (payload.type === 'dedup_result') loadReport();
    },
  });

  document.querySelectorAll('[data-action="dedup-scan"]').forEach(btn => (btn.disabled = false));
  if (result.error) setSummary('The duplicate scan failed. Details are in Activity.');
  else if (!state.report) loadReport();
}

function presetAll(keepEverything) {
  for (const group of state.report?.groups || []) {
    if (keepEverything) {
      state.selections[group.group_id] = new Set((group.entries || []).map(e => e.path_str).filter(Boolean));
    } else {
      state.selections[group.group_id] = group.keeper?.path_str ? new Set([group.keeper.path_str]) : new Set();
    }
  }
  render();
}

function applyFolder(folder, keep) {
  for (const album of state.report?.album_groups || []) {
    for (const group of album.tracks || []) {
      for (const folderObj of group.folders || []) {
        if (folderObj.folder !== folder) continue;
        const set = state.selections[group.group_id] || (state.selections[group.group_id] = new Set());
        for (const entry of folderObj.entries || []) {
          if (keep) set.add(entry.path_str);
          else set.delete(entry.path_str);
        }
      }
    }
  }
  render();
}

async function apply(mode, btn) {
  const decisions = Object.entries(state.selections).map(([group_id, set]) => ({ group_id, keep_paths: [...set] }));
  btn.disabled = true;
  const { data } = await fetchJSON('/dedup/apply', { json: { decisions, mode } });
  btn.disabled = false;

  if (!data?.ok) {
    toast(data?.error || 'Nothing was changed', { tone: 'error' });
    return;
  }
  const verb = mode === 'delete' ? 'deleted' : 'moved to quarantine';
  toast(`${plural(data.processed, 'file')} ${verb}`, { tone: 'ok' });
  modal.close();
}

export function initDedup(modalApi) {
  modal = modalApi;
  const root = modal.el;

  on(document, 'click', '[data-action="dedup-scan"]', () => startScan());
  on(document, 'click', '[data-action="dedup-open"]', () => openLastReport());

  on(root, 'change', 'input[type="checkbox"][data-group-id]', (_, input) => {
    const set = state.selections[input.dataset.groupId] || (state.selections[input.dataset.groupId] = new Set());
    if (input.checked) set.add(input.dataset.path);
    else set.delete(input.dataset.path);
  });

  on(root, 'click', '[data-folder-action]', (_, btn) => applyFolder(btn.dataset.folder, btn.dataset.folderAction === 'keep'));
  on(root, 'click', '[data-dedup-preset]', (_, btn) => presetAll(btn.dataset.dedupPreset === 'all'));

  on(root, 'click', '[data-dedup-apply]', (_, btn) => {
    if (btn.dataset.dedupApply === 'delete' && !armed(btn, 'Click again to delete for good')) return;
    apply(btn.dataset.dedupApply, btn);
  });
}
