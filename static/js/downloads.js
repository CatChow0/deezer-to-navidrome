// Download buttons: queue a download and show where it is on the button
// itself (Queued → 42% or 3/14 → Downloaded), while the Activity cell shows
// the details. A failed or partly failed download can be started again: the
// tracks already saved are kept.

import { escapeHtml, fetchJSON, on, toast } from './core.js';
import { runServerTask, watchTask } from './activity.js';

// States that mean "leave it alone, it is running or it is done".
const LOCKED = new Set(['busy', 'queued', 'active', 'done']);

function setState(btn, state, label, title, progress) {
  btn.dataset.state = state;
  btn.textContent = label;
  btn.disabled = LOCKED.has(state);
  if (title) btn.title = title;
  if (typeof progress === 'number') btn.style.setProperty('--p', `${Math.max(0, Math.min(100, progress))}%`);
  else btn.style.removeProperty('--p');
}

// `label` names the download in Activity; `json` carries extra fields such as
// the playlist the track belongs to.
export async function queueDownload(btn, { url, json = {}, label = '' }) {
  if (LOCKED.has(btn.dataset.state)) return;
  const original = btn.dataset.label || btn.textContent;
  btn.dataset.label = original;
  setState(btn, 'busy', 'Sending…');

  const { ok, data } = await fetchJSON(url, { json: { ...json, label } });
  if (!ok || !data?.task_id) {
    const message = data?.error || 'The download could not be started';
    setState(btn, 'error', 'Retry', message);
    toast(message, { tone: 'error' });
    return;
  }

  watchTask(data.task_id, `Download: ${label || 'track'}`, {
    onStatus(payload) {
      if (payload.done) return;
      if (payload.stage === 'queued') {
        setState(btn, 'queued', 'Queued', payload.message);
      } else if (payload.stage === 'downloading') {
        setState(btn, 'active', payload.short || 'Downloading…', payload.message, payload.progress ?? undefined);
      }
    },
    onDone(payload) {
      if (payload.error) {
        // Activity already says it failed; the button keeps the reason.
        setState(btn, 'error', 'Retry', payload.message);
        return;
      }
      const summary = payload.summary || {};
      const failed = summary.failed || [];
      if (failed.length) {
        setState(btn, 'partial', `${summary.saved}/${summary.total} saved`, `${payload.message}\nClick to try the missing tracks again.`);
        toast(payload.message, { tone: 'error', timeout: 8000 });
      } else {
        setState(btn, 'done', summary.already ? 'Already there' : 'Downloaded', payload.message, 100);
        toast(payload.message, { tone: 'ok' });
      }
    },
    onError() {
      setState(btn, 'error', 'Retry', 'Lost track of the download. It may still be running: check Activity.');
    },
  });
}

export function downloadButton({ type, id, label = 'Download', small = true, name = '' }) {
  return `<button type="button" class="btn btn--ghost dl-btn${small ? ' btn--sm' : ''}" data-action="download" data-download-type="${escapeHtml(type)}" data-download-id="${escapeHtml(id)}" data-download-name="${escapeHtml(name)}">${escapeHtml(label)}</button>`;
}

export function handleDownloadClick(btn) {
  queueDownload(btn, {
    url: '/deezer-dl/download/start',
    json: { type: btn.dataset.downloadType, music_id: btn.dataset.downloadId },
    label: btn.dataset.downloadName,
  });
}

export function initDownloads() {
  on(document, 'click', '[data-action="download"]', (_, btn) => handleDownloadClick(btn));
  on(document, 'click', '[data-action="repair-downloads"]', async (_, btn) => {
    btn.disabled = true;
    await runServerTask('Repair downloads', '/deezer-dl/repair/start');
    btn.disabled = false;
  });
}
