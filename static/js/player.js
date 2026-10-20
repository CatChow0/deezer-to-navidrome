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
  volume: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9h4l5-4v14l-5-4H4z" fill="currentColor"/><path d="M16 8.5a5 5 0 0 1 0 7M18.5 6a8.5 8.5 0 0 1 0 12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  muted: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9h4l5-4v14l-5-4H4z" fill="currentColor"/><path d="M16.5 9.5l5 5M21.5 9.5l-5 5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
};

const audio = new Audio();
audio.preload = 'auto';
// Deezer's preview CDN allows cross-origin reads, which Web Audio needs.
audio.crossOrigin = 'anonymous';

// ── Volume and loudness levelling ─────────────────────────────────────────────
// Deezer measures each track's loudness ("gain", in dB, 0 when unknown).
// Previews are brought towards TARGET_DB, within CUT_DB / BOOST_DB, and a
// limiter catches the peaks a boost could push into clipping.
const TARGET_DB = -12;
const CUT_DB = -12;
const BOOST_DB = 6;
const PREFS_KEY = 'd2n-player';

const prefs = { volume: 0.8, muted: false, level: true };
try {
  Object.assign(prefs, JSON.parse(localStorage.getItem(PREFS_KEY) || '{}'));
} catch (_) {}

function savePrefs() {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch (_) {}
}

let audioCtx = null;
let gainNode = null;

// Built on the first play (browsers only allow audio contexts after a click).
function ensureAudioGraph() {
  if (audioCtx) {
    if (audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
    return;
  }
  try {
    audioCtx = new AudioContext();
    const source = audioCtx.createMediaElementSource(audio);
    gainNode = audioCtx.createGain();
    const limiter = audioCtx.createDynamicsCompressor();
    limiter.threshold.value = -1.5;
    limiter.knee.value = 0;
    limiter.ratio.value = 20;
    limiter.attack.value = 0.003;
    limiter.release.value = 0.15;
    source.connect(gainNode).connect(limiter).connect(audioCtx.destination);
  } catch (_) {
    audioCtx = null;
    gainNode = null;
  }
}

function levelFactor() {
  const gain = Number(current?.gain);
  if (!prefs.level || !gain) return 1;
  const db = Math.max(CUT_DB, Math.min(BOOST_DB, TARGET_DB - gain));
  return 10 ** (db / 20);
}

function applyVolume() {
  // Squared so the slider feels even to the ear.
  const level = prefs.muted ? 0 : prefs.volume ** 2;
  if (gainNode) {
    audio.volume = 1;
    gainNode.gain.value = level * levelFactor();
  } else {
    // Without Web Audio, the element can only turn the sound down.
    audio.volume = Math.min(1, level * Math.min(1, levelFactor()));
  }
}

async function startPlayback() {
  ensureAudioGraph();
  applyVolume();
  await audio.play();
}

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
      await startPlayback();
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
    startPlayback().catch(() => {});
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

function syncVolumeControls() {
  const button = $('[data-player-volume]');
  const silent = prefs.muted || prefs.volume === 0;
  button.innerHTML = silent ? ICONS.muted : ICONS.volume;
  button.setAttribute('aria-label', silent ? 'Volume (muted)' : `Volume ${Math.round(prefs.volume * 100)}%`);
  $('[data-player-volume-range]').value = String(Math.round(prefs.volume * 100));
  $('[data-player-mute]').textContent = prefs.muted ? 'Unmute' : 'Mute';
  $('[data-player-level]').checked = prefs.level;
}

function initVolume() {
  const popover = $('[data-player-volume-popover]');
  const toggle = $('[data-player-volume]');

  toggle.addEventListener('click', event => {
    event.stopPropagation();
    popover.hidden = !popover.hidden;
    toggle.setAttribute('aria-expanded', String(!popover.hidden));
  });
  document.addEventListener('click', event => {
    if (!popover.hidden && !popover.contains(event.target)) {
      popover.hidden = true;
      toggle.setAttribute('aria-expanded', 'false');
    }
  });
  popover.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      event.stopPropagation();
      popover.hidden = true;
      toggle.focus();
    }
  });

  $('[data-player-volume-range]').addEventListener('input', event => {
    prefs.volume = Number(event.target.value) / 100;
    prefs.muted = false;
    applyVolume();
    syncVolumeControls();
    savePrefs();
  });
  $('[data-player-mute]').addEventListener('click', () => {
    prefs.muted = !prefs.muted;
    applyVolume();
    syncVolumeControls();
    savePrefs();
  });
  $('[data-player-level]').addEventListener('change', event => {
    prefs.level = event.target.checked;
    applyVolume();
    savePrefs();
  });

  syncVolumeControls();
  applyVolume();
}

export function initPlayer() {
  el = document.getElementById('player');
  if (!el) return;
  initVolume();

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
