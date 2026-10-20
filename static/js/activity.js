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
