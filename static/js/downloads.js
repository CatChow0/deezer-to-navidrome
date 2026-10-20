// Download buttons: send a request to Deezer Downloader and show the outcome
// on the button itself (Sending… → Queued, or Retry on failure).

import { escapeHtml, fetchJSON, on, streamTask, toast } from './core.js';

function setState(btn, state, label, title) {
  btn.dataset.state = state;
  btn.textContent = label;
  btn.disabled = state === 'busy' || state === 'queued';
  if (title) btn.title = title;
}

export async function queueDownload(btn, { url, json }) {
  if (btn.dataset.state === 'busy' || btn.dataset.state === 'queued') return;
  setState(btn, 'busy', 'Sending…');

  const { ok, data } = await fetchJSON(url, json !== undefined ? { json } : { method: 'POST' });
  if (!ok || !data?.task_id) {
    const message = data?.error || 'Deezer Downloader did not accept the request';
    setState(btn, 'error', 'Retry', message);
    toast(message, { tone: 'error' });
    return;
  }

  let lastMessage = '';
  streamTask(data.task_id, {
    onStatus(payload) {
      if (payload.message) lastMessage = payload.message;
    },
    onDone(payload) {
      if (payload.error) {
        setState(btn, 'error', 'Retry', lastMessage);
        toast(lastMessage || 'Download request failed', { tone: 'error' });
      } else {
        setState(btn, 'queued', 'Queued', 'Sent to Deezer Downloader');
      }
    },
    onError() {
      setState(btn, 'error', 'Retry', 'Lost connection to the task stream');
    },
  });
}

export function downloadButton({ type, id, label = 'Download', small = true }) {
  return `<button type="button" class="btn btn--ghost dl-btn${small ? ' btn--sm' : ''}" data-action="download" data-download-type="${escapeHtml(type)}" data-download-id="${escapeHtml(id)}">${escapeHtml(label)}</button>`;
}

export function handleDownloadClick(btn) {
  queueDownload(btn, {
    url: '/deezer-dl/download/start',
    json: { type: btn.dataset.downloadType, music_id: btn.dataset.downloadId },
  });
}

export function initDownloads() {
  on(document, 'click', '[data-action="download"]', (_, btn) => handleDownloadClick(btn));
}
