// Story recap: full-screen slides for a month or a year, moving on by themselves.
// Tap the right side to skip, the left to go back, hold to pause. Which slides
// appear is decided on the server, from what actually stood out in the period.

import { escapeHtml, fetchJSON } from './core.js';
import {
  pauseStoryAudio, playStoryTrack, previewAudioState, resumeStoryAudio, setPlayerHidden, setPreviewVolume, stopPreview, toggleMute,
} from './player.js';
import { art, count, duration, plural } from './stats.js';

const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const dayFormat = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'long' });
const HOLD_MS = 220;
const SWIPE_PX = 50;

const SECONDS = {
  intro: 6, opener: 7, genres: 8, artist_countdown: 11, top_artist: 9, loyalty: 8, track_countdown: 11, top_track: 9,
  obsession: 8, binge: 8, album_run: 8, new_artists: 9, then_now: 11, biggest_month: 7, clock: 8, personality: 9, time: 10,
};

// Background and ink, chosen to read clearly together.
const PALETTES = [
  ['#1b00ff', '#ffe14d'], ['#ff2e93', '#1a0033'], ['#00e0c6', '#08002e'], ['#ff6a13', '#14002b'],
  ['#ffe14d', '#2a0a7a'], ['#12002e', '#ff5cad'], ['#b6ff3c', '#12002e'], ['#6a00f4', '#fdfbff'],
];

let story = null;
let host = null;
let stage = null;
let slides = [];
let data = null;
let current = 0;
let loadToken = 0;
let elapsed = 0;
let lastFrame = 0;
let frame = 0;
let paused = false;
let held = false;
let holdTimer = 0;
let pointer = null;
let counters = [];

// ── Wording ──────────────────────────────────────────────────────────────────

function period() {
  const isYear = data.kind === 'year';
  const name = isYear ? data.label : data.label.split(' ')[0];
  const previous = data.previous && !data.so_far ? (isYear ? data.previous.label : data.previous.label.split(' ')[0]) : '';
  return { name, here: isYear ? 'this year' : 'this month', previous };
}

const playWord = n => (n === 1 ? 'play' : 'plays');
const day = iso => dayFormat.format(new Date(`${iso}T12:00:00`));
const hour = value => `${String(value).padStart(2, '0')}:00`;

// What a number in a top list means, always in words.
function change(row) {
  const { here, previous } = period();
  if (row.is_new && data.story.established) return `New ${here}`;
  if (!data.story.comparable) return '';
  if (row.previous_plays === null || row.previous_plays === undefined) return `None in ${previous}`;
  const delta = row.plays - row.previous_plays;
  if (delta === 0) return `Same as ${previous}`;
  return `${delta > 0 ? '+' : '-'}${plural(Math.abs(delta), 'play')} vs ${previous}`;
}

function relativeLight(r, g, b) {
  const channel = c => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function fromHsl(hue, saturation, lightness) {
  const part = n => {
    const k = (n + hue / 30) % 12;
    return lightness - saturation * Math.min(lightness, 1 - lightness) * Math.max(-1, Math.min(k - 3, 9 - k, 1));
  };
  return [part(0), part(8), part(4)];
}

// A cover's main color, pushed bright enough to carry a whole slide, and dark
// enough for white text. Near-greys stay grey instead of turning mustard.
function vivid(hex) {
  const value = parseInt(hex.slice(1), 16);
  const [r, g, b] = [(value >> 16) & 255, (value >> 8) & 255, value & 255].map(c => c / 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const delta = max - min;
  let hue = 0;
  if (delta) {
    if (max === r) hue = (((g - b) / delta + 6) % 6) * 60;
    else if (max === g) hue = ((b - r) / delta + 2) * 60;
    else hue = ((r - g) / delta + 4) * 60;
  }
  const saturation = delta < 0.12 ? 0.08 : 0.78;
  let lightness = Math.min(0.42, Math.max(0.26, (max + min) / 2));
  while (lightness > 0.1 && 1.05 / (relativeLight(...fromHsl(hue, saturation, lightness)) + 0.05) < 4.5) lightness -= 0.01;
  return `hsl(${Math.round(hue)} ${Math.round(saturation * 100)}% ${Math.round(lightness * 100)}%)`;
}

// ── Slides ───────────────────────────────────────────────────────────────────

function letters(text) {
  return [...text].map((char, i) => `<span class="st-letter" style="--i:${i}">${char === ' ' ? '&nbsp;' : escapeHtml(char)}</span>`).join('');
}

function countdownRows(rows, nameOf) {
  return rows.slice(1, 5).reverse().map((row, i) => {
    const rank = rows.indexOf(row) + 1;
    const note = change(row);
    return `<li class="st-count-row" style="--i:${i}">
      <span class="st-count-rank">${rank}</span>
      ${art(row.image, nameOf(row))}
      <span class="st-count-text">
        <strong data-fit>${escapeHtml(nameOf(row))}</strong>
        <span>${plural(row.plays, 'play')}${note ? `<em>${escapeHtml(note)}</em>` : ''}</span>
      </span>
    </li>`;
  }).join('');
}

const BUILDERS = {
  intro() {
    const { name, here } = period();
    const covers = [...data.top.albums, ...data.top.tracks].filter(item => item.image).slice(0, 12);
    const line = data.so_far ? `So far, anyway. ${name} isn't finished yet.`
      : data.partial ? 'From your very first recorded play.'
        : `Here's what you were really up to ${here === 'this year' ? 'all year' : `in ${name}`}.`;
    return `<div class="st-wall" aria-hidden="true">${covers.map((item, i) => `<span style="--i:${i}">${art(item.image, item.title)}</span>`).join('')}</div>
      <div class="st-center">
        <h2 class="st-slam" aria-label="${escapeHtml(data.label)}" data-fit>${letters(name)}</h2>
        ${data.kind === 'month' ? `<p class="st-big-note">${escapeHtml(data.label.split(' ')[1])}</p>` : ''}
        <p class="st-line st-rise" style="--i:8">${escapeHtml(line)}</p>
      </div>`;
  },

  opener() {
    const { opener } = data.story;
    return `<p class="st-kicker st-rise">${escapeHtml(period().name)} opened with</p>
      <div class="st-tilt">${art(opener.image, opener.title)}</div>
      <h2 class="st-title st-rise" style="--i:2" data-fit>${escapeHtml(opener.title)}</h2>
      <p class="st-line st-rise" style="--i:3">${escapeHtml(opener.artist)}</p>
      <p class="st-note st-rise" style="--i:4">${escapeHtml(day(opener.date))} at ${escapeHtml(opener.time)}</p>`;
  },

  genres() {
    const top = data.genres[0];
    const rows = data.genres.slice(0, 5);
    const note = data.coverage.genre_pct < 100 ? `Genres are known for ${data.coverage.genre_pct}% of your plays.` : '';
    return `<h2 class="st-title st-rise" data-fit>${escapeHtml(period().name)} sounded like ${escapeHtml(top.name)}</h2>
      <ol class="st-genre-stack">${rows.map((genre, i) => `<li style="--i:${i};--share:${Math.max(0.12, genre.share)}">
        <span class="st-genre-name" data-fit>${escapeHtml(genre.name)}</span>
        <span class="st-genre-time">${Math.round(genre.share * 100)}% of known genres, ${escapeHtml(duration(genre.seconds))}</span>
      </li>`).join('')}</ol>
      ${note ? `<p class="st-note">${escapeHtml(note)}</p>` : ''}`;
  },

  artist_countdown() {
    return `<h2 class="st-title st-rise">Your top ${Math.min(5, data.story.top_artists.length)} artists</h2>
      <ol class="st-count-list">${countdownRows(data.story.top_artists, row => row.name)}</ol>
      <p class="st-teaser st-rise" style="--i:7">And number one is…</p>`;
  },

  top_artist() {
    const artist = data.story.top_artists[0];
    const note = change(artist);
    return `<div class="st-bleed">${art(artist.image, artist.name)}</div>
      <div class="st-marquee" aria-hidden="true"><span>${escapeHtml(`${artist.name} `.repeat(6))}</span></div>
      <div class="st-bottom">
        <p class="st-kicker st-rise">Your number one artist</p>
        <h2 class="st-title st-title--huge st-rise" style="--i:1" data-fit>${escapeHtml(artist.name)}</h2>
        <p class="st-stat st-rise" style="--i:2"><span data-count="${artist.plays}">0</span> ${playWord(artist.plays)}</p>
        <p class="st-line st-rise" style="--i:3">About ${escapeHtml(duration(artist.seconds))} together${note ? `. ${escapeHtml(note)}` : ''}.</p>
      </div>`;
  },

  loyalty() {
    const { loyalty } = data.story;
    const cells = Math.max(2, Math.min(12, loyalty.one_in));
    const when = period().here === 'this year' ? 'this year' : `in ${period().name}`;
    const headline = loyalty.one_in < 2
      ? `${loyalty.artist.name} took over ${when}`
      : `1 in ${count(loyalty.one_in)} of your plays ${when} was ${loyalty.artist.name}`;
    return `<h2 class="st-title st-rise" data-fit>${escapeHtml(headline)}</h2>
      <div class="st-grid" style="--cells:${cells}" aria-hidden="true">${Array.from({ length: cells }, (_, i) => `<span class="${i === cells - 1 ? 'is-lit' : ''}" style="--i:${i}"></span>`).join('')}</div>
      <p class="st-line st-rise" style="--i:6">That's ${loyalty.percent}% of everything you played.</p>`;
  },

  track_countdown() {
    return `<h2 class="st-title st-rise">The songs on repeat</h2>
      <ol class="st-count-list st-count-list--tiles">${countdownRows(data.top.tracks, row => row.title)}</ol>
      <p class="st-teaser st-rise" style="--i:7">One song beat them all…</p>`;
  },

  top_track() {
    const track = data.top.tracks[0];
    const note = change(track);
    return `<p class="st-kicker st-rise">Your song of ${escapeHtml(period().name)}</p>
      <div class="st-record">${art(track.image, track.title)}</div>
      <h2 class="st-title st-rise" style="--i:2" data-fit>${escapeHtml(track.title)}</h2>
      <p class="st-line st-rise" style="--i:3">${escapeHtml(track.artist)}</p>
      <p class="st-stat st-rise" style="--i:4"><span data-count="${track.plays}">0</span> ${playWord(track.plays)}</p>
      ${note ? `<p class="st-note st-rise" style="--i:5">${escapeHtml(note)}</p>` : ''}`;
  },

  obsession() {
    const { obsession } = data.story;
    const quip = obsession.plays >= 25 ? 'Are you okay?' : obsession.plays >= 12 ? 'That song had you.' : 'It got stuck in your head.';
    return `<p class="st-kicker st-rise">On ${escapeHtml(day(obsession.date))} you played</p>
      <h2 class="st-title st-rise" style="--i:1" data-fit>${escapeHtml(obsession.title)}</h2>
      <p class="st-giant" style="--digits:${String(obsession.plays).length}"><span data-count="${obsession.plays}">0</span></p>
      <p class="st-stat st-rise" style="--i:3">times in one day</p>
      <p class="st-line st-rise" style="--i:5">${escapeHtml(quip)}</p>`;
  },

  binge() {
    const { binge } = data.story;
    const width = Math.min(100, (binge.seconds / (16 * 3600)) * 100);
    return `<p class="st-kicker st-rise">Your longest sitting</p>
      <p class="st-giant st-giant--time" data-count-time="${binge.seconds}">0 min</p>
      <div class="st-stretch" aria-hidden="true"><span style="--width:${Math.max(18, width)}%"></span></div>
      <p class="st-line st-rise" style="--i:4">${escapeHtml(day(binge.date))}: ${plural(binge.plays, 'play')} with barely a break${binge.top_artist ? `, mostly ${escapeHtml(binge.top_artist)}` : ''}.</p>`;
  },

  album_run() {
    const { album_run: run } = data.story;
    const dots = Math.min(run.of, 24);
    const lit = Math.round((run.tracks / run.of) * dots);
    return `<div class="st-tilt st-tilt--other">${art(run.image, run.title)}</div>
      <h2 class="st-title st-rise" style="--i:1" data-fit>${escapeHtml(run.title)}</h2>
      <p class="st-stat st-rise" style="--i:2">${plural(run.tracks, 'track')} in a row</p>
      <p class="st-note st-rise" style="--i:3">Out of the ${plural(run.of, 'track')} you've played from it.</p>
      <div class="st-ticks" aria-hidden="true">${Array.from({ length: dots }, (_, i) => `<span class="${i < lit ? 'is-lit' : ''}" style="--i:${i}"></span>`).join('')}</div>
      <p class="st-line st-rise" style="--i:6">In one sitting on ${escapeHtml(day(run.date))}. Respect.</p>`;
  },

  new_artists() {
    const list = data.new_artists;
    const shown = list.slice(0, 6);
    const lead = data.discovery;
    return `<h2 class="st-title st-rise" data-fit>${plural(list.length, 'artist')} you'd never played before</h2>
      <div class="st-faces">${shown.map((artist, i) => `<span class="st-face" style="--i:${i}">${art(artist.image, artist.name)}<em>${escapeHtml(artist.name)}</em></span>`).join('')}</div>
      ${lead && lead.plays >= 5 ? `<p class="st-line st-rise" style="--i:7">${escapeHtml(lead.name)} came out of nowhere: ${plural(lead.plays, 'play')}.</p>` : ''}`;
  },

  then_now() {
    const { movers, comeback, dropped } = data.story;
    const { name, previous } = period();
    const rows = [];
    if (movers?.rise) rows.push(['up', 'Climbing', movers.rise, `+${plural(movers.rise.delta, 'play')} vs ${previous}`]);
    if (movers?.fall) rows.push(['down', 'Cooling off', movers.fall, `-${plural(Math.abs(movers.fall.delta), 'play')} vs ${previous}`]);
    if (comeback) rows.push(['back', 'Back again', comeback, `${plural(comeback.plays, 'play')}, none in ${previous}`]);
    if (dropped) rows.push(['gone', 'Gone quiet', dropped, `${plural(dropped.previous_plays, 'play')} in ${previous}, none in ${name}`]);
    const marks = { up: '↑', down: '↓', back: '↻', gone: '×' };
    return `<h2 class="st-title st-rise">${escapeHtml(previous)} vs ${escapeHtml(name)}</h2>
      <ul class="st-moves">${rows.slice(0, 4).map(([kind, label, artist, note], i) => `<li class="st-move st-move--${kind}" style="--i:${i}">
        <span class="st-move-mark" aria-hidden="true">${marks[kind]}</span>
        ${art(artist.image, artist.name)}
        <span class="st-count-text"><small>${label}</small><strong data-fit>${escapeHtml(artist.name)}</strong><span>${escapeHtml(note)}</span></span>
      </li>`).join('')}</ul>`;
  },

  biggest_month() {
    const { biggest_month: biggest } = data.story;
    return `<p class="st-kicker st-rise">Your biggest month</p>
      <h2 class="st-giant st-giant--word st-slam" aria-label="${escapeHtml(biggest.label)}" data-fit>${letters(biggest.label.split(' ')[0])}</h2>
      <p class="st-stat st-rise" style="--i:6"><span data-count="${biggest.plays}">0</span> ${playWord(biggest.plays)}</p>`;
  },

  clock() {
    const { clock } = data.story;
    const max = Math.max(1, ...clock.hours);
    const bars = clock.hours.map((plays, h) => {
      const length = 18 + (plays / max) * 30;
      return `<g transform="rotate(${h * 15} 100 100)"><rect x="97.5" y="${50 - length}" width="5" height="${length}" rx="2.5" class="${h === clock.peak_hour ? 'is-lit' : ''}" style="--i:${h}"></rect></g>`;
    }).join('');
    const label = clock.peak_hour >= 22 || clock.peak_hour < 5 ? 'Night shift.' : clock.peak_hour < 11 ? 'Early start.' : clock.peak_hour < 18 ? 'Prime time.' : 'Evening ritual.';
    return `<h2 class="st-title st-rise">${hour(clock.peak_hour)} was your hour</h2>
      <svg class="st-clock" viewBox="0 0 200 200" role="img" aria-label="Plays by hour of the day">${bars}<text x="100" y="108" text-anchor="middle">24 h</text></svg>
      <p class="st-line st-rise" style="--i:6">${label} ${plural(clock.hours[clock.peak_hour], 'play')} started around then.</p>`;
  },

  personality() {
    const { personality } = data.story;
    return `<div class="st-center">
        <p class="st-kicker st-rise">${escapeHtml(period().name)} made you</p>
        <h2 class="st-stamp" data-fit>${escapeHtml(personality.name)}</h2>
        <p class="st-line st-rise" style="--i:6">${escapeHtml(personality.reason)}</p>
      </div>`;
  },

  time() {
    const { totals, previous, so_far: soFar } = data;
    const items = data.story.comparisons;
    const seconds = totals.seconds;
    let versus = '';
    if (previous && !soFar && data.story.comparable && previous.totals.seconds) {
      const percent = Math.round(((seconds - previous.totals.seconds) / previous.totals.seconds) * 100);
      versus = percent === 0 ? `Exactly as much as ${period().previous}.` : `${percent > 0 ? '+' : ''}${percent}% vs ${period().previous}.`;
    }
    return `<p class="st-kicker st-rise">Estimated listening time</p>
      <p class="st-giant st-giant--time" data-count-time="${seconds}">0 min</p>
      <p class="st-line st-rise" style="--i:3">${plural(totals.plays, 'play')} of music${versus ? `. ${escapeHtml(versus)}` : '.'}</p>
      <ul class="st-compare">${items.map((item, i) => `<li style="--i:${i + 4}">That's <strong>${count(item.value)}</strong> ${escapeHtml(item.unit)}</li>`).join('')}</ul>
      ${data.coverage.length_pct < 100 ? `<p class="st-note">Track lengths are known for ${data.coverage.length_pct}% of plays, so the real time is higher.</p>` : ''}`;
  },

  outro() {
    const { totals, top, story: info } = data;
    const artist = info.top_artists[0];
    const track = top.tracks[0];
    if (!totals.plays) {
      return `<div class="st-center"><h2 class="st-title">Nothing played in ${escapeHtml(period().name)}</h2>
        <div class="st-actions"><button type="button" class="btn" data-overlay-close>Close</button></div></div>`;
    }
    return `<h2 class="st-title st-rise">That was ${escapeHtml(data.label)}${data.so_far ? ', so far' : ''}</h2>
      <dl class="st-card">
        <div><dt>Listening time</dt><dd>${escapeHtml(duration(totals.seconds))}</dd></div>
        <div><dt>Plays</dt><dd>${count(totals.plays)}</dd></div>
        ${artist ? `<div><dt>Top artist</dt><dd data-fit>${escapeHtml(artist.name)}</dd></div>` : ''}
        ${track ? `<div><dt>Top track</dt><dd data-fit>${escapeHtml(track.title)}</dd></div>` : ''}
        <div class="st-card-wide"><dt>You were</dt><dd data-fit>${escapeHtml(info.personality.name)}</dd></div>
      </dl>
      <div class="st-actions st-rise" style="--i:6">
        <button type="button" class="btn" data-story-replay>Replay</button>
        <button type="button" class="btn btn--ghost" data-overlay-close>Close</button>
      </div>`;
  },
};

// ── Engine ───────────────────────────────────────────────────────────────────

function paletteFor(index, type) {
  let seed = 0;
  for (const char of data.key) seed = (seed * 31 + char.charCodeAt(0)) >>> 0;
  const [back, ink] = PALETTES[(seed + index) % PALETTES.length];
  if (type === 'top_artist') return ['#000000', '#ffffff'];  // white over the darkened photo
  const coloured = { top_track: data.top.tracks[0]?.color, obsession: data.story.obsession?.color }[type];
  if (coloured) return [vivid(coloured), '#ffffff'];
  return [back, ink];
}

// Long names shrink until they fit; nothing on a slide ever scrolls.
function fitText(root) {
  root.querySelectorAll('[data-fit]').forEach(el => {
    let size = parseFloat(getComputedStyle(el).fontSize);
    const floor = size * 0.35;
    // Tight line spacing makes letters reach a little past their box: that is fine.
    const tooBig = () => el.scrollHeight > el.clientHeight + size * 0.3 || el.scrollWidth > el.clientWidth + 1;
    while (size > floor && tooBig()) {
      size *= 0.93;
      el.style.fontSize = `${size}px`;
    }
    // Even at its smallest a very long word may not fit: only then may it break.
    if (tooBig()) el.style.overflowWrap = 'anywhere';
  });
}

function prepareCounters(root) {
  counters = [];
  root.querySelectorAll('[data-count]').forEach(el => {
    counters.push({ el, to: Number(el.dataset.count), format: count });
  });
  root.querySelectorAll('[data-count-time]').forEach(el => {
    counters.push({ el, to: Number(el.dataset.countTime), format: duration });
  });
  counters.forEach(counter => { counter.el.textContent = counter.format(reducedMotion.matches ? counter.to : 0); });
}

function updateCounters() {
  const share = Math.min(1, Math.max(0, (elapsed - 0.5) / 2));
  const eased = 1 - (1 - share) ** 3;
  counters.forEach(counter => {
    counter.el.textContent = counter.format(Math.round(counter.to * eased));
  });
}

function slideLength(index) {
  return SECONDS[slides[index]?.type] || 0;
}

function paintProgress() {
  const bars = host.querySelectorAll('[data-story-progress] span');
  const length = slideLength(current);
  bars.forEach((bar, i) => {
    let fill = 0;
    if (i < current) fill = 1;
    else if (i === current) fill = length && !reducedMotion.matches ? Math.min(1, elapsed / length) : 1;
    bar.style.setProperty('--fill', fill);
  });
}

function tick(now) {
  frame = requestAnimationFrame(tick);
  if (paused || !slides.length) {
    lastFrame = now;
    return;
  }
  elapsed += Math.min(0.25, (now - lastFrame) / 1000);
  lastFrame = now;
  if (!reducedMotion.matches) updateCounters();
  paintProgress();
  const length = slideLength(current);
  if (length && !reducedMotion.matches && elapsed >= length) show(current + 1);
}

function show(index) {
  if (!slides.length || index >= slides.length) return;
  current = Math.max(0, index);
  elapsed = 0;
  const slide = slides[current];
  const [back, ink] = paletteFor(current, slide.type);
  const root = host.querySelector('[data-story-slides]');
  root.innerHTML = `<article class="st-slide st-slide--${slide.type}" data-deco="${current % 4}" style="--bg:${back};--ink:${ink}">${BUILDERS[slide.type]()}</article>`;
  stage.style.setProperty('--ink', ink);
  prepareCounters(root);
  fitText(root);
  host.querySelector('[data-story-count]').textContent = `${current + 1} of ${slides.length}`;
  paintProgress();
  if (slide.track) playStoryTrack(slide.track);
}

function setPaused(value) {
  if (paused === value) return;
  paused = value;
  stage.classList.toggle('is-paused', value);
  host.querySelector('[data-story-paused]').hidden = !value;
  host.querySelector('[data-story-pause]').textContent = value ? 'Play' : 'Pause';
  if (value) pauseStoryAudio();
  else resumeStoryAudio();
}

function syncAudioControls() {
  const { volume, muted } = previewAudioState();
  host.querySelector('[data-story-volume]').value = String(Math.round(volume * 100));
  host.querySelector('[data-story-mute]').textContent = muted ? 'Unmute' : 'Mute';
}

function closed() {
  loadToken++;
  slides = [];
  cancelAnimationFrame(frame);
  clearTimeout(holdTimer);
  pointer = null;
  held = false;
  document.removeEventListener('keydown', onKey);
  document.removeEventListener('visibilitychange', onVisibility);
  stopPreview();
  setPlayerHidden(false);
  setPaused(false);
}

function onVisibility() {
  if (document.hidden) setPaused(true);
}

function onKey(event) {
  if (event.target.matches?.('input')) return;
  if (event.key === 'ArrowRight') {
    event.preventDefault();
    show(current + 1);
  } else if (event.key === 'ArrowLeft') {
    event.preventDefault();
    show(current - 1);
  } else if (event.key === ' ' && !event.target.closest?.('button')) {
    event.preventDefault();
    setPaused(!paused);
  }
}

function start() {
  stopPreview();
  setPlayerHidden(true);
  setPaused(false);
  host.querySelector('[data-story-progress]').innerHTML = slides.map(() => '<span></span>').join('');
  cancelAnimationFrame(frame);
  lastFrame = performance.now();
  frame = requestAnimationFrame(tick);
  show(0);
}

async function openRecap(kind, key) {
  const token = ++loadToken;
  slides = [];
  data = null;
  const root = host.querySelector('[data-story-slides]');
  host.querySelector('[data-story-progress]').innerHTML = '';
  host.querySelector('[data-story-count]').textContent = '';
  root.innerHTML = '<article class="st-slide" style="--bg:#12002e;--ink:#fdfbff"><div class="st-center"><p class="st-line">Loading your recap…</p></div></article>';
  stopPreview();
  setPlayerHidden(true);
  syncAudioControls();
  document.addEventListener('keydown', onKey);
  document.addEventListener('visibilitychange', onVisibility);
  story.open({ label: 'Recap', closeHandler: closed });

  const params = new URLSearchParams({ type: kind, key, tz });
  const { ok, data: answer } = await fetchJSON(`/api/stats/recap?${params}`);
  if (token !== loadToken) return;
  if (!ok) {
    root.innerHTML = `<article class="st-slide" style="--bg:#12002e;--ink:#fdfbff"><div class="st-center">
      <p class="st-line">${escapeHtml(answer?.error || 'This recap could not be loaded.')}</p>
      <div class="st-actions"><button type="button" class="btn" data-overlay-close>Close</button></div></div></article>`;
    return;
  }
  data = answer;
  slides = data.story.slides;
  start();
}

// ── Touch and mouse ──────────────────────────────────────────────────────────

function pointerDown(event) {
  if (event.target.closest('button, input, a')) return;
  // Keeps the release ours even when the finger slides off the stage.
  event.currentTarget.setPointerCapture?.(event.pointerId);
  pointer = { x: event.clientX, y: event.clientY };
  held = false;
  clearTimeout(holdTimer);
  if (paused) return; // already paused with the button: a tap just moves on
  holdTimer = setTimeout(() => {
    held = true;
    setPaused(true);
  }, HOLD_MS);
}

function pointerUp(event) {
  if (!pointer) return;
  clearTimeout(holdTimer);
  const dx = event.clientX - pointer.x;
  const dy = event.clientY - pointer.y;
  pointer = null;
  if (held) {
    held = false;
    setPaused(false);
    return;
  }
  if (Math.abs(dx) > SWIPE_PX && Math.abs(dx) > Math.abs(dy)) {
    show(current + (dx < 0 ? 1 : -1));
    return;
  }
  const box = stage.getBoundingClientRect();
  show(current + (event.clientX - box.left < box.width / 3 ? -1 : 1));
}

export function initStory(storyOverlay) {
  story = storyOverlay;
  host = storyOverlay.el;
  stage = host.querySelector('[data-story-root]');

  document.addEventListener('click', event => {
    const button = event.target.closest('[data-action="open-recap"]');
    if (button) openRecap(button.dataset.kind, button.dataset.key);
  });

  const area = host.querySelector('[data-story-slides]');
  area.addEventListener('pointerdown', pointerDown);
  area.addEventListener('pointerup', pointerUp);
  area.addEventListener('pointercancel', () => {
    clearTimeout(holdTimer);
    pointer = null;
    if (held) setPaused(false);
    held = false;
  });
  area.addEventListener('contextmenu', event => event.preventDefault());
  area.addEventListener('click', event => {
    if (event.target.closest('[data-story-replay]')) start();
  });

  host.querySelector('[data-story-prev]').addEventListener('click', () => show(current - 1));
  host.querySelector('[data-story-next]').addEventListener('click', () => show(current + 1));
  host.querySelector('[data-story-pause]').addEventListener('click', () => setPaused(!paused));
  host.querySelector('[data-story-mute]').addEventListener('click', () => {
    toggleMute();
    syncAudioControls();
  });
  host.querySelector('[data-story-volume]').addEventListener('input', event => {
    setPreviewVolume(Number(event.target.value) / 100);
    syncAudioControls();
  });

  window.addEventListener('resize', () => {
    if (!slides.length) return;
    const root = host.querySelector('[data-story-slides]');
    root.querySelectorAll('[data-fit]').forEach(el => {
      el.style.fontSize = '';
      el.style.overflowWrap = '';
    });
    fitText(root);
  });

  // A cover that fails to load leaves the initials showing.
  host.addEventListener('error', event => {
    if (event.target.matches?.('[data-stats-img]')) event.target.remove();
  }, true);
}
