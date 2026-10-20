// Preview player: 30-second Deezer previews with a queue, plus the official
// Deezer widget for full-length listening (it uses the browser's own Deezer
// login, so what plays in full depends on that account).
//
// Any [data-play-track="<id>"] button plays that track; the other play buttons
// in the same [data-play-queue] container become the queue. A
// [data-play-album="<id>"] button queues a whole album.

import { escapeHtml, fetchJSON, on, toast } from './core.js';

const ICONS = {
  play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l11-6.5z" fill="currentColor"/></svg>',
  pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" fill="currentColor"/></svg>',
  prev: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 6h2v12H7zM20 6v12l-9-6z" fill="currentColor"/></svg>',
  next: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6h2v12h-2zM4 6l9 6-9 6z" fill="currentColor"/></svg>',
};

const audio = new Audio();
audio.preload = 'auto';

let queue = [];
let index = -1;
let current = null;
let loadToken = 0;
let el = null;

export function playButton(trackId, label = 'Play preview') {
  return `<button type="button" class="icon-btn play-btn" data-play-track="${escapeHtml(trackId)}" aria-label="${escapeHtml(label)}" title="Play a 30-second preview">${ICONS.play}</button>`;
}

export function playAlbumButton(albumId, label = 'Play previews of this release') {
  return `<button type="button" class="icon-btn play-btn" data-play-album="${escapeHtml(albumId)}" aria-label="${escapeHtml(label)}" title="Play 30-second previews">${ICONS.play}</button>`;
}

function formatTime(seconds) {
  if (!Number.isFinite(seconds)) return '0:00';
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

const $ = selector => el.querySelector(selector);

// Play buttons of the current track show a pause icon while it plays.
function syncButtons() {
  const playing = current && !audio.paused;
  document.querySelectorAll('[data-play-track]').forEach(btn => {
    const active = playing && btn.dataset.playTrack === current.id;
    btn.classList.toggle('is-playing', !!active);
    btn.innerHTML = active ? ICONS.pause : ICONS.play;
  });
  $('[data-player-toggle]').innerHTML = audio.paused ? ICONS.play : ICONS.pause;
  $('[data-player-toggle]').setAttribute('aria-label', audio.paused ? 'Play' : 'Pause');
  $('[data-player-prev]').disabled = index <= 0;
  $('[data-player-next]').disabled = index >= queue.length - 1;
}

function show() {
  el.hidden = false;
  document.body.classList.add('has-player');
}

function hide() {
  audio.pause();
  closeWidget();
  el.hidden = true;
  document.body.classList.remove('has-player');
  current = null;
  syncButtons();
}

function updateMediaSession() {
  if (!('mediaSession' in navigator) || !current) return;
  navigator.mediaSession.metadata = new MediaMetadata({
    title: current.title,
    artist: current.artist,
    album: current.album,
    artwork: current.cover ? [{ src: current.cover, sizes: '250x250', type: 'image/jpeg' }] : [],
  });
}

async function load(position) {
  if (position < 0 || position >= queue.length) return;
  index = position;
  const token = ++loadToken;
  const trackId = queue[position];

  show();
  $('[data-player-title]').textContent = 'Loading…';
  $('[data-player-artist]').textContent = '';

  const { data } = await fetchJSON(`/api/preview/${encodeURIComponent(trackId)}`);
  if (token !== loadToken) return;

  if (!data?.ok || !data.preview) {
    toast(data?.error || 'Deezer has no preview for this track', { tone: 'error' });
    if (position < queue.length - 1) load(position + 1);
    else hide();
    return;
  }

  current = data;
  $('[data-player-title]').textContent = data.title;
  $('[data-player-artist]').textContent = data.artist;
  const cover = $('[data-player-cover]');
  cover.src = data.cover || '';
  cover.style.visibility = data.cover ? 'visible' : 'hidden';
  audio.src = data.preview;
  if (!$('[data-player-widget]').hidden) {
    // The full player is open: it follows the queue and the preview stays silent.
    openWidget();
  } else {
    try {
      await audio.play();
    } catch (_) {
      // Autoplay can be refused until the page got a click; the toggle still works.
    }
  }
  updateMediaSession();
  syncButtons();
}

function playFrom(button) {
  const container = button.closest('[data-play-queue]');
  const buttons = container ? [...container.querySelectorAll('[data-play-track]')] : [button];
  const ids = buttons.filter(b => b.offsetParent !== null || b === button).map(b => b.dataset.playTrack);
  const trackId = button.dataset.playTrack;

  if (current?.id === trackId) {
    togglePlay();
    return;
  }
  queue = ids;
  load(Math.max(0, ids.indexOf(trackId)));
}

async function playAlbum(albumId) {
  const { data } = await fetchJSON(`/search/album/${encodeURIComponent(albumId)}`);
  const tracks = data?.album?.tracks || [];
  if (!tracks.length) {
    toast(data?.error || 'Could not read this release from Deezer', { tone: 'error' });
    return;
  }
  queue = tracks.map(t => String(t.track_id));
  load(0);
}

function togglePlay() {
  if (!current) return;
  if (audio.paused) {
    closeWidget();
    audio.play().catch(() => {});
  } else {
    audio.pause();
  }
}

function openWidget() {
  if (!current) return;
  audio.pause();
  const widget = $('[data-player-widget]');
  widget.hidden = false;
  widget.innerHTML = `
    <iframe title="Deezer player" src="https://widget.deezer.com/widget/dark/track/${encodeURIComponent(current.id)}?tracklist=false"
      allow="encrypted-media; clipboard-write" loading="lazy"></iframe>
    <p>Full-length playback is Deezer's own player: it plays in full when you are logged in to deezer.com in this browser.
      <a href="${escapeHtml(current.link)}" target="_blank" rel="noopener">Open on Deezer</a></p>
  `;
  $('[data-player-full]').textContent = 'Hide full player';
}

function closeWidget() {
  const widget = el && $('[data-player-widget]');
  if (!widget || widget.hidden) return;
  widget.hidden = true;
  widget.innerHTML = '';
  $('[data-player-full]').textContent = 'Listen in full';
}

export function initPlayer() {
  el = document.getElementById('player');
  if (!el) return;

  $('[data-player-prev]').innerHTML = ICONS.prev;
  $('[data-player-next]').innerHTML = ICONS.next;

  on(document, 'click', '[data-play-track]', (event, btn) => {
    event.stopPropagation();
    playFrom(btn);
  });
  on(document, 'click', '[data-play-album]', (event, btn) => {
    event.stopPropagation();
    playAlbum(btn.dataset.playAlbum);
  });

  $('[data-player-toggle]').addEventListener('click', togglePlay);
  $('[data-player-prev]').addEventListener('click', () => load(index - 1));
  $('[data-player-next]').addEventListener('click', () => load(index + 1));
  $('[data-player-close]').addEventListener('click', hide);
  $('[data-player-full]').addEventListener('click', () => ($('[data-player-widget]').hidden ? openWidget() : closeWidget()));

  const bar = $('[data-player-bar]');
  const time = $('[data-player-time]');
  audio.addEventListener('timeupdate', () => {
    bar.style.width = `${audio.duration ? (audio.currentTime / audio.duration) * 100 : 0}%`;
    time.textContent = `${formatTime(audio.currentTime)} / ${formatTime(audio.duration)}`;
  });
  audio.addEventListener('play', syncButtons);
  audio.addEventListener('pause', syncButtons);
  audio.addEventListener('ended', () => {
    if (index < queue.length - 1) load(index + 1);
    else syncButtons();
  });

  // Seek by clicking the progress bar.
  $('[data-player-seek]').addEventListener('click', event => {
    if (!audio.duration) return;
    const rect = event.currentTarget.getBoundingClientRect();
    audio.currentTime = ((event.clientX - rect.left) / rect.width) * audio.duration;
  });

  if ('mediaSession' in navigator) {
    navigator.mediaSession.setActionHandler('play', togglePlay);
    navigator.mediaSession.setActionHandler('pause', togglePlay);
    navigator.mediaSession.setActionHandler('previoustrack', () => load(index - 1));
    navigator.mediaSession.setActionHandler('nexttrack', () => load(index + 1));
  }
}
