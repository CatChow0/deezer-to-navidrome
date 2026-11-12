// From Deezer: the profile's Deezer account in three tabs. Your playlists
// (Loved tracks, those it made, its favorites), the mixes Deezer makes for it
// to follow, and the playlists it recommends. All then live on the Dashboard.

import { escapeHtml, fetchJSON, on, toast } from './core.js';

let modal = null;
let changed = false;
let found = null;
let tab = 'yours';

const TABS = [['yours', 'Your playlists'], ['mixes', 'Mixes'], ['recommended', 'Recommended']];

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
        ${[playlist.subtitle, playlist.tracks != null ? `${playlist.tracks} track${playlist.tracks === 1 ? '' : 's'}` : '']
          .filter(Boolean).map(text => `<span class="muted">${escapeHtml(text)}</span>`).join('')}
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

function renderTab() {
  modal.el.querySelectorAll('[data-pick-tab]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.pickTab === tab)));
  const body = modal.el.querySelector('[data-mix-picker-body]');
  let html = '';
  if (tab === 'yours') {
    for (const [group, playlists] of groupBy(found.yours || [])) html += section(group, playlists.map(playlistRow).join(''));
    html ||= `<p class="empty">${escapeHtml(found.yours_error ? `Deezer did not give this account's playlists: ${found.yours_error}` : 'This Deezer account has no playlists yet.')}</p>`;
  } else if (tab === 'mixes') {
    // Made-for-you mixes (Deezer's daily mixes) first, then the Flow moods.
    const mixes = [...found.mixes].sort((a, b) => (a.kind === 'stl' ? 0 : 1) - (b.kind === 'stl' ? 0 : 1));
    for (const [group, items] of groupBy(mixes)) html += section(group, items.map(mixRow).join(''));
    html ||= '<p class="empty">Deezer has no mixes for this account yet.</p>';
  } else {
    for (const [group, playlists] of groupBy(found.playlists)) html += section(group, playlists.map(playlistRow).join(''));
    html ||= '<p class="empty">Deezer recommends no playlist for this account right now.</p>';
  }
  body.innerHTML = html;
}

async function openPicker(startTab) {
  changed = false;
  tab = startTab || 'yours';
  modal.open({
    closeHandler: () => {
      if (changed) location.reload();
    },
  });
  const tabs = modal.el.querySelector('[data-pick-tabs]');
  tabs.innerHTML = TABS.map(([key, label]) => `<button type="button" data-pick-tab="${key}" aria-pressed="${key === tab}">${label}</button>`).join('');
  const body = modal.el.querySelector('[data-mix-picker-body]');
  body.innerHTML = '<p class="empty">Asking Deezer for this account\'s playlists and mixes…</p>';

  const { data } = await fetchJSON('/api/deezer/mixes');
  if (!data?.ok) {
    found = null;
    body.innerHTML = `
      <div class="empty">
        <p>${escapeHtml(data?.error || 'Deezer did not answer.')}</p>
        <button type="button" class="btn btn--ghost btn--sm" data-view-link="settings" data-overlay-close>Open Settings</button>
      </div>`;
    return;
  }
  found = data;
  renderTab();
}

export function initMixes(modalApi) {
  modal = modalApi;
  on(document, 'click', '[data-action="choose-mixes"]', (_, button) => openPicker(button.dataset.tab));
  on(modal.el, 'click', '[data-pick-tab]', (_, button) => {
    tab = button.dataset.pickTab;
    if (found) renderTab();
  });

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
      // Shown as added in every tab it is in (a favorite can also be recommended).
      for (const list of [found?.yours, found?.playlists]) (list || []).forEach(p => { if (p.id === btn.dataset.addPlaylist) p.followed = true; });
    } else {
      toast('Could not add this playlist', { tone: 'error' });
      btn.disabled = false;
      btn.textContent = 'Add';
    }
  });
}
