// Activity cell: every task started from this page shows up here with its
// progress and log, without blocking the rest of the interface.

import { escapeHtml, fetchJSON, streamTask, toast } from './core.js';

const AUTO_REMOVE_MS = 6000;

function list() {
  return document.getElementById('activity-list');
}

function refreshEmptyState() {
  const empty = document.getElementById('activity-empty');
  const host = list();
  if (empty && host) empty.hidden = host.children.length > 0;
}

function removeTask(el) {
  el.classList.add('is-leaving');
  setTimeout(() => {
    el.remove();
    refreshEmptyState();
  }, 320);
}

// Returns a handle to drive one task row.
export function startTask(title) {
  const host = list();
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

  const stageEl = el.querySelector('.task-stage');
  const barEl = el.querySelector('.progress-bar');
  const logEl = el.querySelector('.task-log');
  el.querySelector('.task-dismiss').addEventListener('click', () => removeTask(el));

  if (host) {
    host.prepend(el);
    refreshEmptyState();
  }

  return {
    el,
    stage(text) {
      if (text) stageEl.textContent = text;
    },
    progress(value) {
      if (typeof value === 'number') barEl.style.width = `${Math.max(0, Math.min(100, value))}%`;
    },
    log(line, { replace = false } = {}) {
      if (!line) return;
      logEl.textContent = replace ? line : `${logEl.textContent}${line}\n`;
      logEl.scrollTop = logEl.scrollHeight;
    },
    finish({ error = false, message } = {}) {
      el.dataset.state = error ? 'error' : 'done';
      stageEl.textContent = message || (error ? 'Failed' : 'Done');
      if (!error) {
        barEl.style.width = '100%';
        setTimeout(() => removeTask(el), AUTO_REMOVE_MS);
      }
    },
  };
}

// Starts a server task (POST returning { task_id }) and mirrors its stream
// into the Activity cell. Resolves with { error } once the task is done.
export async function runServerTask(title, url, { json, logMode = 'append', onStatus, onRow, onEvent } = {}) {
  const task = startTask(title);
  const { ok, data } = await fetchJSON(url, json !== undefined ? { json } : { method: 'POST' });

  if (!ok || !data?.task_id) {
    const message = data?.error || 'The server did not start the task';
    task.log(message);
    task.finish({ error: true, message });
    toast(`${title}: ${message}`, { tone: 'error' });
    return { error: true };
  }

  return new Promise(resolve => {
    streamTask(data.task_id, {
      onStatus(payload) {
        if (payload.message) task.log(payload.message, { replace: logMode === 'replace' });
        task.stage(payload.message || payload.stage);
        task.progress(payload.progress);
        onStatus?.(payload);
      },
      onRow,
      onEvent,
      onDone(payload) {
        task.finish({ error: !!payload.error });
        if (payload.error) toast(`${title} failed`, { tone: 'error' });
        resolve({ error: !!payload.error });
      },
      onError() {
        task.log('Lost connection to the task stream.');
        task.finish({ error: true, message: 'Connection lost' });
        resolve({ error: true });
      },
    });
  });
}
