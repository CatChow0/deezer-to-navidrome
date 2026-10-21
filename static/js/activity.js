// Activity cell: every task started from this page shows up here with its
// progress and log, without blocking the rest of the interface.

import { escapeHtml, fetchJSON, streamTask, toast } from './core.js';

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
      <button type="button" class="icon-btn task-dismiss" aria-label="Dismiss">×</button>
    </div>
    <div class="task-stage">Starting</div>
    <div class="progress"><div class="progress-bar"></div></div>
    <details>
      <summary>Log</summary>
      <pre class="task-log"></pre>
    </details>
  `;
  return el;
}

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
  for (const el of elements) {
    el.querySelector('.task-dismiss').addEventListener('click', () => removeTask(elements));
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
    log(line, { replace = false } = {}) {
      if (!line) return;
      for (const node of logs) {
        node.textContent = replace ? line : `${node.textContent}${line}\n`;
        node.scrollTop = node.scrollHeight;
      }
    },
    dismiss() {
      removeTask(elements);
    },
    finish({ error = false, message } = {}) {
      elements.forEach(el => (el.dataset.state = error ? 'error' : 'done'));
      stages.forEach(node => (node.textContent = message || (error ? 'Failed' : 'Done')));
      if (!error) {
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
        if (payload.message) entry.ui.log(payload.message, { replace: entry.logMode === 'replace' });
        entry.ui.stage(payload.message || payload.stage);
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
        entry.ui.finish({ error: !!payload.error, message: payload.message });
        if (payload.error) toast(`${entry.summary.title} failed`, { tone: 'error' });
        each('onDone', payload);
        resolve({ error: !!payload.error });
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
