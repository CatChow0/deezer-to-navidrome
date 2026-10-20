// Library cell: what the cache knows about, and refreshing it.

import { fetchJSON, on } from './core.js';
import { runServerTask } from './activity.js';

const numberFormat = new Intl.NumberFormat();

function timeAgo(epochSeconds) {
  if (!epochSeconds) return 'never';
  const minutes = Math.floor((Date.now() / 1000 - epochSeconds) / 60);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return new Date(epochSeconds * 1000).toLocaleDateString();
}

export async function loadLibraryStats() {
  const { data } = await fetchJSON('/api/library/stats');
  if (!data?.ok) return;

  const set = (key, value) => {
    const el = document.querySelector(`[data-stat="${key}"]`);
    if (el) el.textContent = value;
  };
  set('count', numberFormat.format(data.count || 0));
  set('artists', numberFormat.format(data.artists || 0));
  set('albums', numberFormat.format(data.albums || 0));
  set('updated', data.count ? `Indexed ${timeAgo(data.generated_at)}` : 'The library has not been indexed yet. Refresh it to find your files.');
}

export function initLibrary() {
  loadLibraryStats();

  on(document, 'click', '[data-action="cache-refresh"]', async (_, btn) => {
    const mode = btn.dataset.mode === 'full' ? 'full' : 'incremental';
    btn.disabled = true;
    await runServerTask(mode === 'full' ? 'Full library rebuild' : 'Library refresh', `/cache/${mode}/start`);
    btn.disabled = false;
    loadLibraryStats();
  });
}
