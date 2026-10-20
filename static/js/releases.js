// Releases view: recent releases of your favorite Deezer artists, with what
// you already own. The feed is built on the server and loaded the first time
// the view is shown.

import { escapeHtml, fetchJSON, on, toast } from './core.js';
import { runServerTask } from './activity.js';
import { downloadButton } from './downloads.js';
import { playAlbumButton } from './player.js';
import { libraryCheck, openAlbum } from './search.js';
import { onViewShown } from './views.js';

const TYPE_LABEL = { album: 'Album', ep: 'EP', single: 'Single', compile: 'Compilation' };
const dateFormat = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
const monthFormat = new Intl.DateTimeFormat(undefined, { month: 'long', year: 'numeric' });

let feed = null;
let owned = {};
let typeFilter = 'all';
let hideOwned = false;
let hideFeatures = false;
let showAllArtists = false;
let loaded = false;

const FOLLOWED_PREVIEW = 8;

const $ = selector => document.querySelector(selector);

function parseDate(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}

function ownership(release) {
  const count = owned[release.id];
  if (count === undefined) return null;
  if (!count) return 'none';
  return release.nb_tracks && count >= release.nb_tracks ? 'full' : 'partial';
}

function ownedChip(release) {
  const state = ownership(release);
  if (state === 'full') return '<span class="chip chip--ok">In library</span>';
  if (state === 'partial') return `<span class="chip chip--partial">${owned[release.id]}/${release.nb_tracks || '?'} tracks owned</span>`;
  return '';
}

// Feeds built before artist credits were tracked only know the followed artist.
function followedOf(release) {
  return release.followed || [{ id: release.artist_id, name: release.artist }];
}

function isMuted(release) {
  const muted = feed?.muted || {};
  return followedOf(release).every(artist => muted[artist.id] !== undefined);
}

function isVisible(release) {
  if (isMuted(release)) return false;
  if (hideFeatures && release.featured) return false;
  if (typeFilter === 'album' && release.record_type !== 'album') return false;
  if (typeFilter === 'short' && release.record_type === 'album') return false;
  return !(hideOwned && ownership(release) === 'full');
}

function groupLabel(iso, today) {
  return iso > today ? 'Upcoming' : monthFormat.format(parseDate(iso));
}

function releaseRow(release, today) {
  const type = TYPE_LABEL[release.record_type] || release.record_type;
  const upcoming = release.release_date > today;
  const tracks = release.nb_tracks > 1 ? `, ${release.nb_tracks} tracks` : '';
  return `
    <article class="result release" data-release-id="${escapeHtml(release.id)}">
      <div class="result-cover">${release.cover ? `<img src="${escapeHtml(release.cover)}" alt="" loading="lazy">` : ''}</div>
      <div>
        <p class="result-title">${escapeHtml(release.title)}</p>
        <p class="result-sub">${escapeHtml(release.artist)}${release.featured ? `<span class="release-with"> with ${escapeHtml(followedOf(release).map(a => a.name).join(', '))}</span>` : ''}</p>
        <p class="release-meta">${escapeHtml(type)}${tracks}, ${escapeHtml(dateFormat.format(parseDate(release.release_date)))}</p>
        <div class="chips">${ownedChip(release)}</div>
      </div>
      <div class="result-actions">
        ${upcoming ? '<span class="chip">Not out yet</span>' : `${playAlbumButton(release.id)}${downloadButton({ type: 'album', id: release.id })}`}
        <button type="button" class="btn btn--ghost btn--sm" data-open-release="${escapeHtml(release.id)}">Open</button>
      </div>
    </article>
  `;
}

function render() {
  const list = $('[data-release-list]');
  if (!list || !feed) return;

  const releases = (feed.releases || []).filter(isVisible);
  if (!releases.length) {
    list.innerHTML = `<p class="empty">${feed.releases?.length ? 'Nothing left with these filters.' : 'No releases from your favorite artists in this period.'}</p>`;
    return;
  }

  const today = new Date().toISOString().slice(0, 10);
  let html = '';
  let current = null;
  for (const release of releases) {
    const label = groupLabel(release.release_date, today);
    if (label !== current) {
      html += `<h3 class="release-group">${escapeHtml(label)}</h3>`;
      current = label;
    }
    html += releaseRow(release, today);
  }
  list.innerHTML = html;
}

function followedRow(artist, muted) {
  const count = artist.releases ? `${artist.releases} release${artist.releases > 1 ? 's' : ''}` : 'nothing recent';
  return `
    <div class="followed-row${muted ? ' is-muted' : ''}">
      <div>
        <a href="https://www.deezer.com/artist/${escapeHtml(artist.id)}" target="_blank" rel="noopener">${escapeHtml(artist.name)}</a>
        <span class="muted">${muted ? 'Muted' : count}</span>
      </div>
      <button type="button" class="btn btn--ghost btn--sm" data-mute-artist="${escapeHtml(artist.id)}" data-name="${escapeHtml(artist.name)}" data-muted="${muted}">${muted ? 'Unmute' : 'Mute'}</button>
    </div>
  `;
}

function renderFollowed() {
  const host = $('[data-followed-list]');
  if (!host || !feed) return;
  const muted = feed.muted || {};
  const artists = feed.followed_artists || [];
  if (!artists.length) {
    host.innerHTML = '<p class="feed-meta">Refresh the feed to see the artists it follows.</p>';
    return;
  }

  const active = artists.filter(a => muted[a.id] === undefined).sort((a, b) => b.releases - a.releases || a.name.localeCompare(b.name));
  const silenced = Object.entries(muted).map(([id, name]) => ({ id, name: artists.find(a => a.id === id)?.name || name }));
  const shown = showAllArtists ? active : active.slice(0, FOLLOWED_PREVIEW);

  host.innerHTML = `
    ${shown.map(a => followedRow(a, false)).join('')}
    ${active.length > FOLLOWED_PREVIEW
      ? `<button type="button" class="btn btn--ghost btn--sm followed-more" data-followed-toggle>${showAllArtists ? 'Show fewer' : `Show all ${active.length}`}</button>`
      : ''}
    ${silenced.length ? `<h3 class="followed-heading">Muted</h3>${silenced.map(a => followedRow(a, true)).join('')}` : ''}
  `;
}

async function setMuted(button) {
  const muted = button.dataset.muted !== 'true';
  button.disabled = true;
  const { data } = await fetchJSON('/api/releases/mute', {
    json: { artist_id: button.dataset.muteArtist, name: button.dataset.name, muted },
  });
  if (!data?.ok) {
    button.disabled = false;
    toast(data?.error || 'Could not change this artist', { tone: 'error' });
    return;
  }
  feed.muted = data.muted;
  toast(muted ? `${button.dataset.name} is muted in the feed` : `${button.dataset.name} is back in the feed`);
  renderFollowed();
  render();
}

function renderMeta(data) {
  const meta = $('[data-feed-meta]');
  const refresh = $('[data-action="refresh-releases"]');
  if (!meta) return;
  if (refresh) refresh.disabled = !data.connected;

  if (!data.connected) {
    meta.innerHTML = 'Connect your Deezer account to follow the releases of your favorite artists. <a href="/config" data-view-link="settings">Open Settings</a>';
  } else if (!data.updated_at) {
    meta.textContent = 'The feed has not been built yet. It starts on its own within a minute, or refresh it now.';
  } else {
    const minutes = Math.round((Date.now() / 1000 - data.updated_at) / 60);
    const when = minutes < 1 ? 'just now' : minutes < 90 ? `${minutes} min ago` : `${Math.round(minutes / 60)} h ago`;
    const hours = Number(data.refresh_hours);
    const schedule = !hours
      ? 'refreshed only when you ask'
      : hours % 24 === 0
        ? `refreshed every ${hours === 24 ? 'day' : hours === 168 ? 'week' : `${hours / 24} days`}`
        : `refreshed every ${hours} hours`;
    meta.textContent = `${data.artists} favorite artists, releases from the last ${data.window_days} days. Updated ${when}; ${schedule}.`;
  }
}

async function checkOwnership() {
  const releases = feed?.releases || [];
  for (let i = 0; i < releases.length; i += 100) {
    const batch = releases.slice(i, i + 100);
    const results = await libraryCheck(batch.map(r => ({ key: r.id, type: 'album', title: r.title, artist: r.artist })));
    for (const release of batch) owned[release.id] = results?.[release.id]?.owned_count ?? 0;
    render();
  }
}

async function loadFeed() {
  loaded = true;
  const { data } = await fetchJSON('/api/releases');
  if (!data?.ok) {
    $('[data-release-list]').innerHTML = '<p class="empty">The release feed could not be read.</p>';
    return;
  }
  feed = data;
  owned = {};
  renderMeta(data);
  if (!data.connected) {
    $('[data-release-list]').innerHTML = '<p class="empty">No Deezer account connected.</p>';
    return;
  }
  render();
  renderFollowed();
  checkOwnership();
}

export function initReleases() {
  onViewShown(name => {
    if (name === 'releases' && !loaded) loadFeed();
  });

  on(document, 'click', '[data-release-type]', (_, btn) => {
    typeFilter = btn.dataset.releaseType;
    btn.parentElement.querySelectorAll('[data-release-type]').forEach(b => b.setAttribute('aria-pressed', String(b === btn)));
    render();
  });

  document.querySelector('[data-release-hide-owned]')?.addEventListener('change', event => {
    hideOwned = event.target.checked;
    render();
  });

  document.querySelector('[data-release-hide-features]')?.addEventListener('change', event => {
    hideFeatures = event.target.checked;
    render();
  });

  on(document, 'click', '[data-mute-artist]', (_, btn) => setMuted(btn));
  on(document, 'click', '[data-followed-toggle]', () => {
    showAllArtists = !showAllArtists;
    renderFollowed();
  });

  on(document, 'click', '[data-open-release]', (_, btn) => openAlbum(btn.dataset.openRelease));

  on(document, 'click', '[data-action="refresh-releases"]', async (_, btn) => {
    btn.disabled = true;
    const result = await runServerTask('Release feed refresh', '/api/releases/refresh');
    btn.disabled = false;
    if (!result.error) loadFeed();
  });
}
