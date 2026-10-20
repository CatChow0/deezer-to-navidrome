// Current version in the topbar, plus a badge when a newer release exists.

import { fetchJSON } from './core.js';

const VERSION_CHECK_INTERVAL = 15 * 60 * 1000;

async function displayCurrentVersion() {
  const { data } = await fetchJSON('/api/version');
  const tag = document.getElementById('version-tag');
  if (tag && data?.version) tag.textContent = `v${data.version}`;
}

async function checkForLatestVersion() {
  const { data } = await fetchJSON('/api/latest-version');
  if (!data?.update_available || !data.latest_version) return;

  const badge = document.getElementById('new-version-tag');
  if (!badge) return;
  badge.href = data.url || '#';
  badge.textContent = `Update to v${data.latest_version}`;
  badge.title = `v${data.current_version} is installed, v${data.latest_version} is available`;
  badge.classList.remove('hidden');
}

export function initVersion() {
  displayCurrentVersion();
  checkForLatestVersion();
  setInterval(checkForLatestVersion, VERSION_CHECK_INTERVAL);
}
