// Shared helpers: escaping, JSON fetch, task streams, toasts, delegation.

export function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

// Returns { ok, status, data } and never throws; network errors come back as ok: false.
export async function fetchJSON(url, options = {}) {
  const opts = { ...options };
  if (opts.json !== undefined) {
    opts.method = opts.method || 'POST';
    opts.headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    opts.body = JSON.stringify(opts.json);
    delete opts.json;
  }
  try {
    const resp = await fetch(url, opts);
    let data = null;
    try {
      data = await resp.json();
    } catch (_) {
      data = null;
    }
    return { ok: resp.ok, status: resp.status, data };
  } catch (err) {
    return { ok: false, status: 0, data: { error: `Network error: ${err.message || err}` } };
  }
}

// Follows a server task over SSE. Handlers: onStatus(payload), onRow(row),
// onEvent(payload) for anything else, onDone(payload), onError().
export function streamTask(taskId, handlers = {}) {
  const source = new EventSource(`/tasks/${taskId}/stream`);
  let finished = false;

  source.onmessage = event => {
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch (_) {
      return;
    }

    if (payload.type === 'row_update' && payload.row) {
      handlers.onRow?.(payload.row);
      return;
    }

    if (payload.type === 'status') {
      handlers.onStatus?.(payload);
    } else {
      handlers.onEvent?.(payload);
    }

    if (payload.done) {
      finished = true;
      source.close();
      handlers.onDone?.(payload);
    }
  };

  source.onerror = () => {
    source.close();
    if (!finished) handlers.onError?.();
  };

  return source;
}

const TOAST_TONES = { info: '', ok: 'dot--ok', error: 'dot--miss' };

export function toast(message, { tone = 'info', timeout = 4500 } = {}) {
  let host = document.querySelector('.toasts');
  if (!host) {
    host = document.createElement('div');
    host.className = 'toasts';
    host.setAttribute('role', 'status');
    host.setAttribute('aria-live', 'polite');
    document.body.appendChild(host);
  }

  const el = document.createElement('div');
  el.className = 'toast';
  el.innerHTML = `<span class="dot ${TOAST_TONES[tone] || ''}"></span><span class="toast-msg">${escapeHtml(message)}</span>`;
  host.appendChild(el);

  setTimeout(() => {
    el.classList.add('is-leaving');
    setTimeout(() => el.remove(), 320);
  }, timeout);
}

// Delegated listener: on(document, 'click', '[data-action="x"]', (event, el) => …)
export function on(root, type, selector, handler) {
  root.addEventListener(type, event => {
    const el = event.target.closest(selector);
    if (el && root.contains(el)) handler(event, el);
  });
}

// Destructive buttons need a second click within a few seconds.
export function armed(button, label = 'Click again to confirm') {
  if (button.dataset.armed === 'true') {
    button.dataset.armed = 'false';
    button.textContent = button.dataset.label;
    return true;
  }
  button.dataset.label = button.textContent;
  button.dataset.armed = 'true';
  button.textContent = label;
  setTimeout(() => {
    if (button.dataset.armed === 'true') {
      button.dataset.armed = 'false';
      button.textContent = button.dataset.label;
    }
  }, 4000);
  return false;
}

export function showFlashMessages() {
  const node = document.getElementById('flash-messages');
  if (!node) return;
  try {
    for (const message of JSON.parse(node.textContent || '[]')) toast(message);
  } catch (_) {}
}
