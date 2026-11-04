// Story recap: full-screen slides for a month or a year, with previews of what
// each slide is about. Slides advance when you ask; nothing moves on its own.

import { escapeHtml, fetchJSON, on } from './core.js';
import { playPreview, previewAudioState, setPlayerHidden, setPreviewVolume, stopPreview, toggleMute } from './player.js';
import { art, count, duration, plural } from './stats.js';

const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const dateFormat = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'long' });

let story = null;
let host = null;
let slides = [];
let currentSlide = 0;
let loadToken = 0;
let touchStart = null;

function firstPlayable(tracks) {
  return tracks.find(track => track.deezer_track_id)?.deezer_track_id || '';
}

function trackOfArtist(data, name) {
  const needle = name.toLocaleLowerCase();
  const match = data.top.tracks.find(track => track.deezer_track_id && track.artist.toLocaleLowerCase().includes(needle));
  return match?.deezer_track_id || '';
}

function diffBadge(row, data) {
  if (!data.has_previous) return '';
  if (row.is_new) return '<span class="st-diff st-diff--new">New</span>';
  if (row.previous_plays === null || row.previous_plays === undefined) return '<span class="st-diff">Back</span>';
  const delta = row.plays - row.previous_plays;
  if (delta === 0) return '<span class="st-diff">Same</span>';
  return `<span class="st-diff">${delta > 0 ? '+' : '-'}${count(Math.abs(delta))}</span>`;
}

function podium(rows, data) {
  // Second, first, third: the winner stands in the middle.
  const order = [rows[1], rows[0], rows[2]].filter(Boolean);
  const places = rows.length > 1 ? [2, 1, 3] : [1];
  return `<div class="st-podium">${order.map((row, i) => {
    const name = row.name || row.title;
    return `<div class="st-podium-item" data-place="${places[i]}">
      <span class="st-podium-place">${places[i]}</span>
      ${art(row.image, name)}
      <strong>${escapeHtml(name)}</strong>
      ${row.artist ? `<span class="st-row-sub">${escapeHtml(row.artist)}</span>` : ''}
      <span class="st-row-sub">${plural(row.plays, 'play')} ${diffBadge(row, data)}</span>
    </div>`;
  }).join('')}</div>`;
}

function restOfRanking(rows, data) {
  const rest = rows.slice(3);
  if (!rest.length) return '';
  return `<ol class="st-story-list" start="4">${rest.map(row => `<li>
    <span class="st-row-name-text">${escapeHtml(row.name || row.title)}</span>
    <span class="st-row-value">${count(row.plays)} ${diffBadge(row, data)}</span>
  </li>`).join('')}</ol>`;
}

function buildSlides(data) {
  const { top, totals, habits, genres } = data;
  const fallback = firstPlayable(top.tracks);
  const built = [];
  const intro = data.so_far ? 'So far.' : data.partial ? 'From your first recorded play.' : 'Here is how it sounded.';
  built.push({
    track: fallback,
    html: `<h2 class="st-story-huge">${escapeHtml(data.label)}</h2><p class="st-story-lead">${escapeHtml(intro)}</p>`,
  });

  if (genres.length) {
    const max = genres[0].plays || 1;
    built.push({
      track: fallback,
      html: `<h2 class="st-story-title">You kept coming back to ${escapeHtml(genres[0].name)}</h2>
        <ol class="st-story-bars">${genres.slice(0, 5).map(genre => `<li>
          <span>${escapeHtml(genre.name)}</span><span class="st-story-value">${duration(genre.seconds)}</span>
          <span class="st-bar" style="width:${Math.max(2, (genre.plays / max) * 100)}%"></span>
        </li>`).join('')}</ol>
        ${data.coverage.genre_pct < 100 ? `<p class="st-story-note">Genres are known for ${data.coverage.genre_pct}% of these plays.</p>` : ''}`,
    });
  }

  if (top.artists.length) {
    built.push({
      track: trackOfArtist(data, top.artists[0].name) || fallback,
      html: `<h2 class="st-story-title">Your top artists</h2>${podium(top.artists, data)}${restOfRanking(top.artists, data)}`,
    });
  }

  if (top.tracks.length) {
    built.push({
      track: top.tracks[0].deezer_track_id || fallback,
      html: `<h2 class="st-story-title">Your top tracks</h2>${podium(top.tracks, data)}${restOfRanking(top.tracks, data)}`,
    });
  }

  if (data.new_artists.length) {
    const shown = data.new_artists.slice(0, 3);
    built.push({
      track: trackOfArtist(data, shown[0].name) || fallback,
      html: `<h2 class="st-story-title">${plural(data.new_artists.length, 'new artist')}</h2>
        <p class="st-story-lead">Never played before this period.</p>
        <div class="st-story-new">${shown.map(artist => `<div>${art(artist.image, artist.name)}<strong>${escapeHtml(artist.name)}</strong><span class="st-row-sub">${plural(artist.plays, 'play')}</span></div>`).join('')}</div>`,
    });
  }

  if (data.discovery) {
    built.push({
      track: trackOfArtist(data, data.discovery.name) || fallback,
      html: `<div class="st-story-discovery">${art(data.discovery.image, data.discovery.name)}</div>
        <h2 class="st-story-title">Your discovery: ${escapeHtml(data.discovery.name)}</h2>
        <p class="st-story-lead">New to you, and already ${plural(data.discovery.plays, 'play')}.</p>`,
    });
  }

  if (totals.plays) {
    let peak = { day: 0, hour: 0, plays: 0 };
    habits.heatmap.forEach((hours, day) => hours.forEach((plays, hour) => {
      if (plays > peak.plays) peak = { day, hour, plays };
    }));
    const busiest = habits.busiest_day.date
      ? dateFormat.format(new Date(`${habits.busiest_day.date}T12:00:00`))
      : '';
    built.push({
      track: fallback,
      html: `<h2 class="st-story-title">${DAYS[peak.day]}s around ${String(peak.hour).padStart(2, '0')}:00 were your time</h2>
        <dl class="st-story-facts">
          ${busiest ? `<div><dt>Busiest day</dt><dd>${escapeHtml(busiest)}</dd><dd class="st-row-sub">${plural(habits.busiest_day.plays, 'play')}</dd></div>` : ''}
          ${habits.longest_streak.days > 1 ? `<div><dt>Longest streak</dt><dd>${count(habits.longest_streak.days)} days</dd><dd class="st-row-sub">in a row</dd></div>` : ''}
        </dl>`,
    });
  }

  const previous = data.previous;
  if (previous && previous.totals.plays) {
    const max = Math.max(totals.seconds, previous.totals.seconds, 1);
    const change = previous.totals.seconds ? Math.round(((totals.seconds - previous.totals.seconds) / previous.totals.seconds) * 100) : 0;
    const direction = change === 0 ? `the same as ${previous.label}` : `${Math.abs(change)}% ${change > 0 ? 'more' : 'less'} than ${previous.label}`;
    built.push({
      track: fallback,
      html: `<h2 class="st-story-huge st-story-huge--time">${escapeHtml(duration(totals.seconds))}</h2>
        <p class="st-story-lead">Estimated listening, ${escapeHtml(direction)}.</p>
        <ol class="st-story-bars">
          <li><span>${escapeHtml(data.label)}</span><span class="st-story-value">${duration(totals.seconds)}</span><span class="st-bar" style="width:${Math.max(2, (totals.seconds / max) * 100)}%"></span></li>
          <li><span>${escapeHtml(previous.label)}</span><span class="st-story-value">${duration(previous.totals.seconds)}</span><span class="st-bar st-bar--dim" style="width:${Math.max(2, (previous.totals.seconds / max) * 100)}%"></span></li>
        </ol>`,
    });
  }

  built.push({
    track: fallback,
    html: `<h2 class="st-story-title">That was ${escapeHtml(data.label)}</h2>
      <p class="st-story-lead">${plural(totals.plays, 'play')}, ${plural(totals.artists, 'artist')} and about ${duration(totals.seconds)}.</p>
      <button type="button" class="btn" data-overlay-close>Close</button>`,
  });
  return built;
}

function show(index) {
  if (!slides.length) return;
  if (index >= slides.length) {
    story.close();
    return;
  }
  currentSlide = Math.max(0, index);
  const stage = host.querySelector('[data-story-stage]');
  stage.innerHTML = `<div class="st-slide">${slides[currentSlide].html}</div>`;
  stage.scrollTop = 0;
  host.querySelectorAll('[data-story-progress] span').forEach((bar, i) => {
    bar.classList.toggle('is-seen', i <= currentSlide);
  });
  host.querySelector('[data-story-prev]').disabled = currentSlide === 0;
  const counter = host.querySelector('[data-story-count]');
  counter.textContent = `${currentSlide + 1} of ${slides.length}`;
  if (slides[currentSlide].track) playPreview(slides[currentSlide].track);
}

function syncAudioControls() {
  const { volume, muted } = previewAudioState();
  host.querySelector('[data-story-volume]').value = String(Math.round(volume * 100));
  host.querySelector('[data-story-mute]').textContent = muted ? 'Unmute' : 'Mute';
}

function closed() {
  loadToken++;
  slides = [];
  document.removeEventListener('keydown', onKey);
  stopPreview();
  setPlayerHidden(false);
}

function onKey(event) {
  if (event.target.matches?.('input')) return;
  if (event.key === 'ArrowRight' || event.key === ' ') {
    if (event.target.closest?.('button') && event.key === ' ') return;
    event.preventDefault();
    show(currentSlide + 1);
  } else if (event.key === 'ArrowLeft') {
    event.preventDefault();
    show(currentSlide - 1);
  }
}

async function openRecap(kind, key) {
  const token = ++loadToken;
  slides = [];
  host.querySelector('[data-story-progress]').innerHTML = '';
  host.querySelector('[data-story-count]').textContent = '';
  host.querySelector('[data-story-stage]').innerHTML = '<div class="st-slide"><p class="st-story-lead">Loading your recap…</p></div>';
  stopPreview();
  setPlayerHidden(true);
  syncAudioControls();
  document.removeEventListener('keydown', onKey);
  document.addEventListener('keydown', onKey);
  story.open({ label: 'Recap', closeHandler: closed });

  const params = new URLSearchParams({ type: kind, key, tz });
  const { ok, data } = await fetchJSON(`/api/stats/recap?${params}`);
  if (token !== loadToken) return;
  if (!ok) {
    host.querySelector('[data-story-stage]').innerHTML = `<div class="st-slide"><p class="st-story-lead">${escapeHtml(data?.error || 'This recap could not be loaded.')}</p><button type="button" class="btn" data-overlay-close>Close</button></div>`;
    return;
  }
  slides = buildSlides(data);
  host.querySelector('[data-story-progress]').innerHTML = slides.map(() => '<span></span>').join('');
  show(0);
}

export function initStory(storyOverlay) {
  story = storyOverlay;
  host = storyOverlay.el;

  on(document, 'click', '[data-action="open-recap"]', (_, button) => openRecap(button.dataset.kind, button.dataset.key));

  host.querySelector('[data-story-prev]').addEventListener('click', () => show(currentSlide - 1));
  host.querySelector('[data-story-next]').addEventListener('click', () => show(currentSlide + 1));
  host.querySelector('[data-story-mute]').addEventListener('click', () => {
    toggleMute();
    syncAudioControls();
  });
  host.querySelector('[data-story-volume]').addEventListener('input', event => {
    setPreviewVolume(Number(event.target.value) / 100);
    syncAudioControls();
  });

  // A cover that fails to load leaves the initials showing.
  host.addEventListener('error', event => {
    if (event.target.matches?.('[data-stats-img]')) event.target.remove();
  }, true);

  // Swipe sideways to move; up and down stay free for scrolling a long slide.
  const stage = host.querySelector('[data-story-stage]');
  stage.addEventListener('touchstart', event => {
    const touch = event.changedTouches[0];
    touchStart = { x: touch.screenX, y: touch.screenY };
  }, { passive: true });
  stage.addEventListener('touchend', event => {
    if (!touchStart) return;
    const touch = event.changedTouches[0];
    const dx = touch.screenX - touchStart.x;
    const dy = touch.screenY - touchStart.y;
    touchStart = null;
    if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) show(currentSlide + (dx < 0 ? 1 : -1));
  }, { passive: true });
}
