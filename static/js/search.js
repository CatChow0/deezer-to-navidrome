// Deezer search: results list, library ownership chips, and album/artist
// details opened in the drawer.

import { escapeHtml, fetchJSON, on } from './core.js';
import { downloadButton } from './downloads.js';

let drawer = null;
let currentType = 'track';
let currentResults = [];

const ownedChip = (label = 'In library', title = 'Already in your library') =>
  `<span class="chip chip--ok" title="${escapeHtml(title)}">${escapeHtml(label)}</span>`;

function countChip(owned, total, unit) {
  if (!owned) return '';
  const full = total > 0 && owned >= total;
  const label = total > 0 ? `${owned}/${total} ${unit} owned` : `${owned} ${unit} owned`;
  return `<span class="chip ${full ? 'chip--ok' : 'chip--partial'}">${escapeHtml(label)}</span>`;
}

function formatDuration(seconds) {
  if (!seconds) return '';
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

function coverImg(src, alt, className = '') {
  return src
    ? `<img class="${className}" src="${escapeHtml(src)}" alt="" loading="lazy">`
    : `<div class="${className} placeholder" aria-hidden="true"></div>`;
}

// ── Library ownership ─────────────────────────────────────────────────────────

async function libraryCheck(type, ids, artist, totalAlbums = '') {
  const params = new URLSearchParams({ type, ids, artist });
  if (totalAlbums) params.set('total_albums', totalAlbums);
  const { data } = await fetchJSON(`/search/library-check?${params}`);
  return data?.ok ? data.results || {} : null;
}

async function updateResultBadges() {
  if (!currentResults.length) return;
  const type = currentType;
  const artistName = currentResults[0]?.artist || '';

  // Tracks and albums are looked up by title, artists by Deezer ID.
  const keyOf = item => (type === 'artist' ? item.id : item.title || '');
  const ids = currentResults.map(keyOf).join(',');
  if (!ids) return;

  const totalAlbums = type === 'artist'
    ? currentResults.map(r => `${r.id}:${r.nb_album || 0}`).join('|')
    : '';

  const results = await libraryCheck(type, ids, artistName, totalAlbums);
  if (!results || type !== currentType) return;

  for (const item of currentResults) {
    const info = results[keyOf(item)];
    const slot = document.getElementById(`result-${type}-${item.id}-chips`);
    if (!info || !slot) continue;

    if (type === 'track') {
      if (info.owned) slot.innerHTML = ownedChip();
    } else if (type === 'album') {
      slot.innerHTML = countChip(info.owned_count || 0, item.track_count || 0, 'tracks');
    } else {
      slot.innerHTML = countChip(info.albums_owned || 0, info.total_albums || 0, 'albums');
    }
  }
}

async function markOwnedTracks(tracks, artistName, root) {
  const titles = tracks.map(t => t.title || '').join(',');
  if (!titles) return;
  const results = await libraryCheck('track', titles, artistName);
  if (!results) return;

  let owned = 0;
  for (const track of tracks) {
    if (!results[track.title || '']?.owned) continue;
    owned++;
    const slot = root.querySelector(`[data-owned-slot="${CSS.escape(String(track.track_id))}"]`);
    if (slot) slot.innerHTML = ownedChip();
  }

  const summary = root.querySelector('[data-owned-summary]');
  if (summary) summary.innerHTML = countChip(owned, tracks.length, 'tracks');
}

async function markOwnedAlbums(albums, artistName, root) {
  const titles = albums.map(a => a.title || '').join(',');
  if (!titles) return;
  const results = await libraryCheck('album', titles, artistName);
  if (!results) return;

  for (const album of albums) {
    const info = results[album.title || ''];
    const slot = root.querySelector(`[data-album-chip="${CSS.escape(String(album.id))}"]`);
    if (info && slot) slot.innerHTML = countChip(info.owned_count || 0, album.track_count || 0, 'tracks');
  }
}

// ── Results list ──────────────────────────────────────────────────────────────

function renderResult(item) {
  const type = item.type || 'track';
  const expandable = type === 'album' || type === 'artist';
  const id = `result-${type}-${item.id}`;

  return `
    <article class="result result--${escapeHtml(type)}" id="${escapeHtml(id)}">
      <div class="result-cover">${item.cover ? `<img src="${escapeHtml(item.cover)}" alt="" loading="lazy">` : ''}</div>
      <div>
        <p class="result-title">${escapeHtml(item.title)}</p>
        <p class="result-sub">${escapeHtml((item.subtitle || '').replaceAll(' • ', ', '))}</p>
        <div class="chips" id="${escapeHtml(id)}-chips"></div>
      </div>
      <div class="result-actions">
        ${type !== 'album' ? downloadButton({ type: item.download_type || type, id: item.download_id || item.id }) : ''}
        ${expandable ? `<button type="button" class="btn btn--ghost btn--sm" data-action="open-result" data-type="${escapeHtml(type)}" data-id="${escapeHtml(item.id)}">Open</button>` : ''}
      </div>
    </article>
  `;
}

async function runSearch(query) {
  const status = document.getElementById('search-status');
  const list = document.getElementById('search-results');
  status.textContent = 'Searching Deezer…';
  list.innerHTML = '';
  currentResults = [];

  const type = currentType;
  const { data } = await fetchJSON(`/search?q=${encodeURIComponent(query)}&type=${encodeURIComponent(type)}`);
  if (type !== currentType) return;

  if (!data?.ok) {
    status.textContent = data?.error || 'Search failed. Check that the server can reach Deezer.';
    return;
  }

  currentResults = data.results || [];
  const noun = { track: 'track', album: 'album', artist: 'artist' }[type];
  status.textContent = currentResults.length
    ? `${currentResults.length} ${noun}${currentResults.length > 1 ? 's' : ''} for “${query}”`
    : `No ${noun} found for “${query}”`;
  list.innerHTML = currentResults.map(renderResult).join('');
  await updateResultBadges();
}

// ── Album and artist in the drawer ────────────────────────────────────────────

function trackTable(tracks) {
  return `
    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr><th class="num">#</th><th>Title</th><th>Artist</th><th class="num">Time</th><th class="actions"><span class="sr-only">Actions</span></th></tr>
        </thead>
        <tbody>
          ${tracks.map(track => `
            <tr>
              <td class="num">${escapeHtml(track.position)}</td>
              <td>${escapeHtml(track.title)}</td>
              <td class="muted">${escapeHtml(track.artist || '')}</td>
              <td class="num">${formatDuration(track.duration)}</td>
              <td class="actions">
                <span class="chips owned-slot" data-owned-slot="${escapeHtml(track.track_id)}"></span>
                ${downloadButton({ type: 'track', id: track.track_id })}
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function albumMinutes(tracks) {
  const total = tracks.reduce((sum, t) => sum + (t.duration || 0), 0);
  return total ? `, ${Math.round(total / 60)} min` : '';
}

function loadingDetail(kind) {
  return `<div class="detail-head"><div class="detail-cover"></div><div><p class="detail-kind">${kind}</p><p class="detail-title">Loading…</p></div></div>`;
}

async function openAlbum(albumId) {
  drawer.open({ html: loadingDetail('Album'), label: 'Album' });
  const { data } = await fetchJSON(`/search/album/${encodeURIComponent(albumId)}`);
  if (!data?.ok) {
    drawer.content.innerHTML = `<p class="empty">${escapeHtml(data?.error || 'Could not load this album from Deezer.')}</p>`;
    return;
  }

  const album = data.album;
  const tracks = Array.isArray(album.tracks) ? album.tracks : [];
  drawer.content.innerHTML = `
    <header class="detail-head">
      ${coverImg(album.cover, album.title, 'detail-cover')}
      <div>
        <p class="detail-kind">Album</p>
        <h2 class="detail-title">${escapeHtml(album.title)}</h2>
        <p class="detail-sub">${escapeHtml(album.artist)}, ${tracks.length} tracks${albumMinutes(tracks)}</p>
        <div class="chips detail-chips" data-owned-summary></div>
        <div class="detail-actions">
          ${downloadButton({ type: 'album', id: album.id, label: 'Download album', small: false }).replace('btn btn--ghost', 'btn')}
        </div>
      </div>
    </header>
    <section class="detail-section">${trackTable(tracks)}</section>
  `;
  await markOwnedTracks(tracks, album.artist || '', drawer.content);
}

async function openArtist(artistId) {
  drawer.open({ html: loadingDetail('Artist'), label: 'Artist' });
  const { data } = await fetchJSON(`/search/artist/${encodeURIComponent(artistId)}`);
  if (!data?.ok) {
    drawer.content.innerHTML = `<p class="empty">${escapeHtml(data?.error || 'Could not load this artist from Deezer.')}</p>`;
    return;
  }

  const artist = data.artist;
  const albums = Array.isArray(artist.albums) ? artist.albums : [];
  drawer.content.innerHTML = `
    <header class="detail-head">
      ${coverImg(artist.picture, artist.name, 'detail-cover detail-cover--round')}
      <div>
        <p class="detail-kind">Artist</p>
        <h2 class="detail-title">${escapeHtml(artist.name)}</h2>
        <p class="detail-sub">${escapeHtml(artist.nb_album || albums.length)} releases on Deezer</p>
        <div class="chips detail-chips" data-artist-summary></div>
        <div class="detail-actions">
          ${downloadButton({ type: 'artist', id: artist.id, label: 'Download discography', small: false }).replace('btn btn--ghost', 'btn')}
        </div>
      </div>
    </header>
    <section class="detail-section">
      <h3 class="section-title">Releases</h3>
      <div class="album-list">
        ${albums.map(album => `
          <article class="album-row" data-album-id="${escapeHtml(album.id)}">
            <button type="button" class="album-toggle" data-action="toggle-album" data-album-id="${escapeHtml(album.id)}" aria-expanded="false">
              ${coverImg(album.cover, album.title)}
              <span>
                <strong>${escapeHtml(album.title)}</strong>
                <span class="muted">${escapeHtml([album.record_type, (album.release_date || '').slice(0, 4)].filter(Boolean).join(', '))}</span>
              </span>
              <span class="chips" data-album-chip="${escapeHtml(album.id)}"></span>
            </button>
            <div class="album-inline" hidden></div>
          </article>
        `).join('')}
      </div>
    </section>
  `;

  const totalAlbums = `${artist.id}:${artist.nb_album || 0}`;
  libraryCheck('artist', artist.id, artist.name || '', totalAlbums).then(results => {
    const info = results?.[artist.id];
    const slot = drawer.content.querySelector('[data-artist-summary]');
    if (info && slot) slot.innerHTML = countChip(info.albums_owned || 0, info.total_albums || 0, 'albums');
  });
  await markOwnedAlbums(albums, artist.name || '', drawer.content);
}

async function toggleArtistAlbum(button) {
  const row = button.closest('.album-row');
  const panel = row.querySelector('.album-inline');
  const isOpen = !panel.hidden;

  drawer.content.querySelectorAll('.album-row.is-open').forEach(other => {
    other.classList.remove('is-open');
    other.querySelector('.album-toggle').setAttribute('aria-expanded', 'false');
    other.querySelector('.album-inline').hidden = true;
  });
  if (isOpen) return;

  row.classList.add('is-open');
  button.setAttribute('aria-expanded', 'true');
  panel.hidden = false;

  if (panel.dataset.loaded) return;
  panel.innerHTML = '<p class="muted">Loading tracks…</p>';

  const { data } = await fetchJSON(`/search/album/${encodeURIComponent(button.dataset.albumId)}`);
  if (!data?.ok) {
    panel.innerHTML = `<p class="muted">${escapeHtml(data?.error || 'Could not load this album.')}</p>`;
    return;
  }

  const album = data.album;
  const tracks = Array.isArray(album.tracks) ? album.tracks : [];
  panel.dataset.loaded = 'true';
  panel.innerHTML = `
    <div class="album-inline-head">
      <span>${tracks.length} tracks${albumMinutes(tracks)}</span>
      ${downloadButton({ type: 'album', id: album.id, label: 'Download album' })}
    </div>
    ${trackTable(tracks)}
  `;
  await markOwnedTracks(tracks, album.artist || '', panel);
}

// ── Wiring ────────────────────────────────────────────────────────────────────

export function initSearch(drawerApi) {
  drawer = drawerApi;
  const form = document.getElementById('search-form');
  if (!form) return;

  form.addEventListener('submit', event => {
    event.preventDefault();
    const query = form.elements.q.value.trim();
    if (query) runSearch(query);
  });

  on(form, 'click', '[data-search-type]', (_, btn) => {
    currentType = btn.dataset.searchType;
    form.querySelectorAll('[data-search-type]').forEach(b => b.setAttribute('aria-pressed', String(b === btn)));
    const query = form.elements.q.value.trim();
    if (query) runSearch(query);
  });

  on(document, 'click', '[data-action="open-result"]', (_, btn) => {
    if (btn.dataset.type === 'album') openAlbum(btn.dataset.id);
    else if (btn.dataset.type === 'artist') openArtist(btn.dataset.id);
  });

  on(document, 'click', '[data-action="toggle-album"]', (_, btn) => toggleArtistAlbum(btn));
}
