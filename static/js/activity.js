// Activity cell: every task started from this page shows up here with its
// progress and log, without blocking the rest of the interface.

import { armed, escapeHtml, fetchJSON, streamTask, toast } from './core.js';

const AUTO_REMOVE_MS = 6000;

// Each view has its own Activity cell; every task is mirrored in all of them.
function hosts() {
  return [...document.querySelectorAll('.activity-list')];
}

function refreshEmptyStates() {
  for (const host of hosts()) {
    const empty = host.parentElement.querySelector('.activity-empty');
    if (empty) empty.hidden = host.children.length > 0;
  }
}

function removeTask(elements) {
  for (const el of elements) el.classList.add('is-leaving');
  setTimeout(() => {
    for (const el of elements) el.remove();
    refreshEmptyStates();
  }, 320);
}

function taskElement(title) {
  const el = document.createElement('article');
  el.className = 'task';
  el.dataset.state = 'running';
  el.innerHTML = `
    <div class="task-top">
      <span class="task-title">${escapeHtml(title)}</span>
      <button type="button" class="btn btn--ghost btn--sm task-cancel" hidden>Cancel</button>
      <button type="button" class="icon-btn task-dismiss" aria-label="Hide" title="Hide: it keeps running" hidden>×</button>
    </div>
    <div class="task-stage">Starting</div>
    <div class="progress"><div class="progress-bar"></div></div>
    <div class="task-meta" aria-live="off"></div>
    <details>
      <summary>Log</summary>
      <pre class="task-log"></pre>
    </details>
  `;
  return el;
}

// "3m 12s", "1h 04m", "45s"
export function formatDuration(seconds) {
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return `${total}s`;
  if (total < 3600) return `${Math.floor(total / 60)}m ${String(total % 60).padStart(2, '0')}s`;
  return `${Math.floor(total / 3600)}h ${String(Math.floor(total / 60) % 60).padStart(2, '0')}m`;
}

function clockStamp(seconds) {
  const total = Math.max(0, Math.round(seconds));
  const minutes = String(Math.floor(total / 60)).padStart(2, '0');
  return `${minutes}:${String(total % 60).padStart(2, '0')}`;
}

function formatRate(perSecond) {
  if (perSecond >= 1) return `${perSecond.toFixed(1)}/s`;
  return `${(perSecond * 60).toFixed(1)}/min`;
}

const COUNT = /(?:^|\s)(\d+)\s*\/\s*(\d+)\b/;
const RATE_WINDOW_SECONDS = 60;
const RATE_MIN_SECONDS = 3;
const HIDE_AFTER_MS = 1500;

// Speed over the last minute rather than since the start: a task often begins with
// slow searches, and the estimate should follow what it does now.
function progressTracker() {
  let samples = [];
  let total = null;
  return {
    add(time, message, percent) {
      const match = COUNT.exec(message || '');
      if (match && Number(match[1]) <= Number(match[2])) {
        const seen = Number(match[2]);
        if (seen !== total) samples = [];
        total = seen;
        samples.push({ time, value: Number(match[1]), counted: true });
      } else if (total === null && typeof percent === 'number') {
        samples.push({ time, value: percent, counted: false });
      }
      const oldest = time - RATE_WINDOW_SECONDS;
      while (samples.length > 2 && samples[1].time <= oldest) samples.shift();
    },
    // { rate (per second, of items), left (seconds) } when it can be told
    estimate() {
      if (samples.length < 2) return {};
      const first = samples[0];
      const last = samples[samples.length - 1];
      const seconds = last.time - first.time;
      const gained = last.value - first.value;
      if (seconds < RATE_MIN_SECONDS || gained <= 0) return {};
      const speed = gained / seconds;
      const remaining = (last.counted ? total : 100) - last.value;
      return { rate: last.counted ? speed : null, left: remaining / speed };
    },
  };
}

const runningClocks = new Set();
setInterval(() => runningClocks.forEach(tick => tick()), 1000);

// Returns a handle to drive one task row (in every Activity cell).
export function startTask(title) {
  const elements = hosts().map(host => {
    const el = taskElement(title);
    host.prepend(el);
    return el;
  });
  refreshEmptyStates();

  const all = selector => elements.map(el => el.querySelector(selector));
  const stages = all('.task-stage');
  const bars = all('.progress-bar');
  const logs = all('.task-log');
  const metas = all('.task-meta');
  const cancels = all('.task-cancel');
  const hides = all('.task-dismiss');
  const tracker = progressTracker();

  const localStart = Date.now() / 1000;
  let createdAt = null;
  let skew = 0;
  let finished = false;
  let taskId = null;
  let running = true;

  const elapsed = () => Date.now() / 1000 + skew - (createdAt ?? localStart);
  const draw = () => {
    if (finished) return;
    const { rate, left } = tracker.estimate();
    const parts = [formatDuration(elapsed())];
    if (rate) parts.push(formatRate(rate));
    if (left !== undefined && left > 0) parts.push(left < 60 ? 'under a minute left' : `about ${formatDuration(left)} left`);
    metas.forEach(node => (node.textContent = parts.join(' · ')));
  };
  runningClocks.add(draw);
  draw();
  // The × only appears once the task turns out not to be stoppable: until the page
  // knows, it must not offer to "close" something that would simply keep running.
  const showHide = setTimeout(() => {
    if (!taskId) hides.forEach(node => (node.hidden = false));
  }, HIDE_AFTER_MS);

  for (const button of hides) {
    button.addEventListener('click', () => {
      if (running) toast(`${title} keeps running. It shows again if you reload the page.`);
      removeTask(elements);
    });
  }
  for (const button of cancels) {
    button.addEventListener('click', async () => {
      if (!armed(button, 'Stop it?')) return;
      cancels.forEach(node => (node.disabled = true));
      const { ok, data } = await fetchJSON(`/api/tasks/${taskId}/cancel`, { method: 'POST' });
      if (!ok) {
        cancels.forEach(node => (node.disabled = false));
        toast(data?.error || 'This task could not be stopped', { tone: 'error' });
      }
    });
  }

  return {
    stage(text) {
      if (text) stages.forEach(node => (node.textContent = text));
    },
    progress(value) {
      if (typeof value !== 'number') return;
      const width = `${Math.max(0, Math.min(100, value))}%`;
      bars.forEach(node => (node.style.width = width));
    },
    // What the server says about the task, with each event.
    update(payload) {
      if (payload.created_at) createdAt = payload.created_at;
      if (payload.server_now) skew = payload.server_now - Date.now() / 1000;
      if (payload.message || typeof payload.progress === 'number') {
        tracker.add(payload.timestamp ?? Date.now() / 1000, payload.message, payload.progress);
      }
      draw();
    },
    // The line for the log: when it happened, and how fast it is going.
    logLine(payload) {
      const at = payload.timestamp && createdAt ? `[${clockStamp(payload.timestamp - createdAt)}] ` : '';
      const { rate } = tracker.estimate();
      return `${at}${payload.message}${rate && COUNT.test(payload.message) ? ` (${formatRate(rate)})` : ''}`;
    },
    cancellable(id) {
      taskId = id;
      clearTimeout(showHide);
      if (finished || !running) return;
      cancels.forEach(node => (node.hidden = false));
      hides.forEach(node => (node.hidden = true));
    },
    stopping() {
      elements.forEach(el => (el.dataset.state = 'stopping'));
      stages.forEach(node => (node.textContent = 'Stopping: finishing what is in progress'));
      cancels.forEach(node => (node.disabled = true));
    },
    log(line, { replace = false } = {}) {
      if (!line) return;
      for (const node of logs) {
        node.textContent = replace ? line : `${node.textContent}${line}\n`;
        node.scrollTop = node.scrollHeight;
      }
    },
    dismiss() {
      runningClocks.delete(draw);
      removeTask(elements);
    },
    finish({ error = false, cancelled = false, message, finishedAt } = {}) {
      const took = (finishedAt && createdAt ? finishedAt - createdAt : elapsed());
      running = false;
      finished = true;
      runningClocks.delete(draw);
      elements.forEach(el => (el.dataset.state = error ? 'error' : cancelled ? 'cancelled' : 'done'));
      stages.forEach(node => {
        node.textContent = message || (error ? 'Failed' : cancelled ? 'Cancelled' : 'Done');
        node.title = node.textContent;
      });
      metas.forEach(node => (node.textContent = `${cancelled ? 'Stopped after' : 'Took'} ${formatDuration(took)}`));
      cancels.forEach(node => (node.hidden = true));
      hides.forEach(node => {
        node.hidden = false;
        node.title = 'Dismiss';
        node.setAttribute('aria-label', 'Dismiss');
      });
      if (!error && !cancelled) {
        bars.forEach(node => (node.style.width = '100%'));
        setTimeout(() => removeTask(elements), AUTO_REMOVE_MS);
      }
    },
  };
}

// ── Following server tasks ───────────────────────────────────────────────────
// Every task the server runs (started here, in another tab, or by the
// scheduler) is followed once; its row updates are broadcast to listeners.

const SYNC_INTERVAL_MS = 5000;
const followed = new Map();
const rowListeners = new Set();

// listener({ task, row }) for every row update of any followed task.
export function onTaskRow(listener) {
  rowListeners.add(listener);
}

function follow(summary, ui, handlers = {}) {
  let entry = followed.get(summary.id);
  if (entry) {
    entry.handlers.push(handlers);
    if (handlers.logMode) entry.logMode = handlers.logMode;
    return entry.promise;
  }

  entry = { summary, ui: ui || startTask(summary.title), handlers: [handlers], logMode: handlers.logMode || 'append' };
  followed.set(summary.id, entry);
  const each = (name, ...args) => entry.handlers.forEach(h => h[name]?.(...args));

  entry.promise = new Promise(resolve => {
    streamTask(summary.id, {
      onStatus(payload) {
        entry.ui.update(payload);
        if (payload.cancellable) entry.ui.cancellable(summary.id);
        if (payload.message) entry.ui.log(entry.ui.logLine(payload), { replace: entry.logMode === 'replace' });
        if (payload.stage === 'stopping') {
          entry.ui.stopping();
        } else {
          entry.ui.stage(payload.message || payload.stage);
        }
        entry.ui.progress(payload.progress);
        each('onStatus', payload);
      },
      onRow(row) {
        rowListeners.forEach(listener => listener({ task: entry.summary, row }));
        each('onRow', row);
      },
      onEvent(payload) {
        each('onEvent', payload);
      },
      onDone(payload) {
        entry.ui.finish({ error: !!payload.error, cancelled: !!payload.cancelled, message: payload.message, finishedAt: payload.finished_at });
        if (payload.error) toast(`${entry.summary.title} failed`, { tone: 'error' });
        if (payload.cancelled) toast(`${entry.summary.title} cancelled`);
        each('onDone', payload);
        resolve({ error: !!payload.error, cancelled: !!payload.cancelled });
      },
      onError() {
        entry.ui.log('Lost connection to the task stream.');
        entry.ui.finish({ error: true, message: 'Connection lost' });
        each('onError');
        resolve({ error: true });
      },
    });
  });
  return entry.promise;
}

// Starts a server task (POST returning { task_id }) and follows it.
// Resolves with { error } once the task is done.
export async function runServerTask(title, url, { json, playlistId = null, ...handlers } = {}) {
  const ui = startTask(title);
  const { ok, data } = await fetchJSON(url, json !== undefined ? { json } : { method: 'POST' });

  if (!ok || !data?.task_id) {
    const message = data?.error || 'The server did not start the task';
    ui.log(message);
    ui.finish({ error: true, message });
    toast(`${title}: ${message}`, { tone: 'error' });
    return { error: true };
  }

  const existing = followed.get(data.task_id);
  if (existing) {
    // The periodic sync saw this task first: drop the duplicate row.
    ui.dismiss();
    return follow(existing.summary, null, handlers);
  }
  return follow({ id: data.task_id, title, playlist_id: playlistId }, ui, handlers);
}

// Follows a task the server already started (its Activity row appears at
// once instead of at the next sync). Handlers: onStatus, onRow, onDone, onError.
export function watchTask(id, title, handlers = {}, { playlistId = null } = {}) {
  const existing = followed.get(id);
  return follow(existing ? existing.summary : { id, title, playlist_id: playlistId }, null, handlers);
}

// Picks up running tasks this page did not start.
async function syncTasks() {
  const { ok, data } = await fetchJSON('/api/tasks');
  if (!ok || !data?.tasks) return;
  for (const task of data.tasks) {
    if (!task.done && !followed.has(task.id)) follow(task, null);
  }
}

export function initActivity() {
  syncTasks();
  setInterval(() => {
    if (!document.hidden) syncTasks();
  }, SYNC_INTERVAL_MS);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) syncTasks();
  });
}
