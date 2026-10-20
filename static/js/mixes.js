// Mix picker: follow the mixes Deezer makes for you, or add the playlists it
// recommends. Followed mixes then live on the Dashboard like playlists.

import { escapeHtml, fetchJSON, on, toast } from './core.js';

let modal = null;
let changed = false;

function groupBy(items) {
  const groups = new Map();
  for (const item of items) {
    if (!groups.has(item.group)) groups.set(item.group, []);
    groups.get(item.group).push(item);
  }
  return groups;
}

function mixRow(mix) {
  return `
    <div class="pick-row">
      <div>
        <strong>${escapeHtml(mix.title)}</strong>
        ${mix.subtitle && mix.subtitle !== mix.title ? `<span class="muted">${escapeHtml(mix.subtitle)}</span>` : ''}
      </div>
      ${mix.followed
        ? '<button type="button" class="btn btn--ghost btn--sm" disabled>Following</button>'
        : `<button type="button" class="btn btn--ghost btn--sm" data-follow-mix data-kind="${escapeHtml(mix.kind)}" data-source-id="${escapeHtml(mix.source_id)}" data-title="${escapeHtml(mix.title)}">Follow</button>`}
    </div>
  `;
}

function playlistRow(playlist) {
  return `
    <div class="pick-row">
      <img src="${escapeHtml(playlist.picture)}" alt="" loading="lazy">
      <div>
        <strong>${escapeHtml(playlist.title)}</strong>
        ${playlist.subtitle ? `<span class="muted">${escapeHtml(playlist.subtitle)}</span>` : ''}
      </div>
      ${playlist.followed
        ? '<button type="button" class="btn btn--ghost btn--sm" disabled>Added</button>'
        : `<button type="button" class="btn btn--ghost btn--sm" data-add-playlist="${escapeHtml(playlist.id)}">Add</button>`}
    </div>
  `;
}

function section(title, rows) {
  return `<section class="pick-group"><h3 class="section-title">${escapeHtml(title)}</h3><div class="pick-list">${rows}</div></section>`;
}

async function openPicker() {
  changed = false;
  modal.open({
    closeHandler: () => {
      if (changed) location.reload();
    },
  });
  const body = modal.el.querySelector('[data-mix-picker-body]');
  body.innerHTML = '<p class="empty">Asking Deezer what it made for you…</p>';

  const { data } = await fetchJSON('/api/deezer/mixes');
  if (!data?.ok) {
    body.innerHTML = `
      <div class="empty">
        <p>${escapeHtml(data?.error || 'Deezer did not answer.')}</p>
        <button type="button" class="btn btn--ghost btn--sm" data-view-link="settings" data-overlay-close>Open Settings</button>
      </div>`;
    return;
  }

  let html = '';
  // Made-for-you mixes (Deezer's daily mixes) first, then the Flow moods.
  const mixes = [...data.mixes].sort((a, b) => (a.kind === 'stl' ? 0 : 1) - (b.kind === 'stl' ? 0 : 1));
  for (const [group, items] of groupBy(mixes)) html += section(group, items.map(mixRow).join(''));
  for (const [group, playlists] of groupBy(data.playlists)) html += section(group, playlists.map(playlistRow).join(''));
  body.innerHTML = html || '<p class="empty">Deezer has no mixes for this account yet.</p>';
}

export function initMixes(modalApi) {
  modal = modalApi;
  on(document, 'click', '[data-action="choose-mixes"]', () => openPicker());

  on(modal.el, 'click', '[data-follow-mix]', async (_, btn) => {
    btn.disabled = true;
    btn.textContent = 'Following…';
    const { data } = await fetchJSON('/api/deezer/mixes/follow', {
      json: { kind: btn.dataset.kind, source_id: btn.dataset.sourceId, title: btn.dataset.title },
    });
    if (data?.ok) {
      changed = true;
      btn.textContent = 'Following';
      btn.className = 'btn btn--ghost btn--sm';
    } else {
      toast(data?.error || 'Could not follow this mix', { tone: 'error' });
      btn.disabled = false;
      btn.textContent = 'Follow';
    }
  });

  on(modal.el, 'click', '[data-add-playlist]', async (_, btn) => {
    btn.disabled = true;
    btn.textContent = 'Adding…';
    const body = new URLSearchParams({ playlist_input: btn.dataset.addPlaylist });
    const resp = await fetch('/playlist/add', { method: 'POST', body }).catch(() => null);
    if (resp?.ok) {
      changed = true;
      btn.textContent = 'Added';
    } else {
      toast('Could not add this playlist', { tone: 'error' });
      btn.disabled = false;
      btn.textContent = 'Add';
    }
  });
}
