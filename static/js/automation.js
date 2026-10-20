// Playlist automation: scheduler countdowns, chips on tiles, and the
// settings section in the playlist drawer.

import { escapeHtml, fetchJSON, toast } from './core.js';

let schedulerData = null;

export function settingsFromTile(tile) {
  return {
    enabled: tile?.dataset.autoScan === 'true',
    download: tile?.dataset.autoDownload === 'true',
    interval: parseInt(tile?.dataset.autoInterval, 10) || 60,
  };
}

function schedulerEntry(playlistId) {
  return (schedulerData?.playlists || []).find(p => p.id === playlistId) || null;
}

function formatInterval(minutes) {
  if (minutes % 1440 === 0) return `every ${minutes / 1440} d`;
  if (minutes >= 60) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return `every ${h} h${m ? ` ${m}` : ''}`;
  }
  return `every ${minutes} min`;
}

function formatCountdown(secs) {
  if (secs <= 0) return 'Scanning soon';
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = Math.floor(secs % 60);
  if (h > 0) return `Next scan in ${h}h ${String(m).padStart(2, '0')}m`;
  return `Next scan in ${m}:${String(s).padStart(2, '0')}`;
}

export function automationChips(playlistId, { enabled, download, interval }, { showOff = false } = {}) {
  if (!enabled) {
    return showOff ? '<span class="chip">Auto scan off</span>' : '';
  }
  return `
    <span class="chip chip--ok" title="Quick scan runs ${escapeHtml(formatInterval(interval))}">Auto scan</span>
    ${download ? '<span class="chip chip--info" title="Missing tracks are sent to Deezer Downloader after each scan">Auto download</span>' : ''}
    <span class="chip chip--clock" data-next-scan="${escapeHtml(playlistId)}" data-interval="${interval}">${escapeHtml(formatInterval(interval))}</span>
  `;
}

function updateCountdowns() {
  const now = Math.floor(Date.now() / 1000);
  document.querySelectorAll('[data-next-scan]').forEach(el => {
    const entry = schedulerEntry(el.dataset.nextScan);
    if (entry?.next_run_at) {
      el.textContent = formatCountdown(Math.max(0, entry.next_run_at - now));
    } else {
      el.textContent = formatInterval(parseInt(el.dataset.interval, 10) || 60);
    }
  });
}

export async function loadSchedulerStatus() {
  const { ok, data } = await fetchJSON('/api/scheduler/status');
  if (ok && data) {
    schedulerData = data;
    updateCountdowns();
  }
}

export function initAutomation() {
  loadSchedulerStatus();
  setInterval(loadSchedulerStatus, 30000);
  setInterval(updateCountdowns, 1000);
}

function toValueUnit(minutes) {
  if (minutes >= 1440 && minutes % 1440 === 0) return [minutes / 1440, '1440'];
  if (minutes >= 60 && minutes % 60 === 0) return [minutes / 60, '60'];
  return [minutes, '1'];
}

function lastRunText(playlistId) {
  const entry = schedulerEntry(playlistId);
  if (!entry?.last_run_at) return '';
  const ago = Math.max(0, Math.floor((Date.now() / 1000 - entry.last_run_at) / 60));
  if (ago < 1) return 'Last automatic scan: just now';
  if (ago < 90) return `Last automatic scan: ${ago} min ago`;
  return `Last automatic scan: ${Math.round(ago / 60)} h ago`;
}

export function automationSection(playlistId, settings) {
  const [value, unit] = toValueUnit(settings.interval);
  const unitOption = (v, label) => `<option value="${v}" ${unit === v ? 'selected' : ''}>${label}</option>`;
  const lastRun = settings.enabled ? lastRunText(playlistId) : '';

  return `
    <div class="automation" data-automation="${escapeHtml(playlistId)}">
      <div class="auto-row">
        <div>
          <div class="auto-row-title" id="auto-scan-label">Scan automatically</div>
          <div class="auto-row-desc">Runs a quick scan on a schedule to pick up new tracks.</div>
        </div>
        <label class="switch">
          <input type="checkbox" data-auto="enabled" aria-labelledby="auto-scan-label" ${settings.enabled ? 'checked' : ''}>
          <span class="switch-slider"></span>
        </label>
      </div>
      <div class="auto-interval" data-auto="interval-row" ${settings.enabled ? '' : 'hidden'}>
        <label for="auto-value">Every</label>
        <input type="number" id="auto-value" data-auto="value" min="1" max="999" value="${value}">
        <select data-auto="unit" aria-label="Interval unit">
          ${unitOption('1', 'minutes')}${unitOption('60', 'hours')}${unitOption('1440', 'days')}
        </select>
      </div>
      <div class="auto-row ${settings.enabled ? '' : 'is-disabled'}" data-auto="download-row">
        <div>
          <div class="auto-row-title" id="auto-dl-label">Download missing tracks</div>
          <div class="auto-row-desc">After each automatic scan, send unmatched tracks to Deezer Downloader.</div>
        </div>
        <label class="switch">
          <input type="checkbox" data-auto="download" aria-labelledby="auto-dl-label" ${settings.download ? 'checked' : ''} ${settings.enabled ? '' : 'disabled'}>
          <span class="switch-slider"></span>
        </label>
      </div>
      ${lastRun ? `<p class="auto-status">${escapeHtml(lastRun)}</p>` : ''}
      <div class="auto-actions">
        <button type="button" class="btn btn--ghost" data-auto="save">Save automation</button>
      </div>
    </div>
  `;
}

// Wires the section rendered by automationSection(); onSaved receives the new settings.
export function bindAutomationSection(root, playlistId, onSaved) {
  const box = root.querySelector(`[data-automation="${CSS.escape(playlistId)}"]`);
  if (!box) return;
  const field = name => box.querySelector(`[data-auto="${name}"]`);

  field('enabled').addEventListener('change', () => {
    const enabled = field('enabled').checked;
    field('interval-row').hidden = !enabled;
    field('download-row').classList.toggle('is-disabled', !enabled);
    field('download').disabled = !enabled;
    if (!enabled) field('download').checked = false;
  });

  field('save').addEventListener('click', async () => {
    const enabled = field('enabled').checked;
    const value = parseInt(field('value').value, 10) || 1;
    const unit = parseInt(field('unit').value, 10) || 60;
    const settings = { enabled, download: field('download').checked, interval: value * unit };

    field('save').disabled = true;
    const { data } = await fetchJSON(`/playlist/${playlistId}/automation`, {
      json: {
        auto_scan_enabled: settings.enabled,
        auto_scan_interval_minutes: settings.interval,
        auto_download_after_scan: settings.download,
      },
    });
    field('save').disabled = false;

    if (!data?.ok) {
      toast(data?.error || 'Automation settings were not saved', { tone: 'error' });
      return;
    }

    toast(settings.enabled ? 'Automation saved' : 'Automatic scans turned off', { tone: 'ok' });
    await loadSchedulerStatus();
    onSaved?.(settings);
  });
}
