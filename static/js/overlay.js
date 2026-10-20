// Drawer and modal behaviour: open/close, Escape, focus return, and making
// the page behind inert while an overlay is up.

const openStack = [];

function syncInert() {
  const app = document.querySelector('.app');
  if (app) app.inert = openStack.length > 0;
  document.documentElement.style.overflow = openStack.length ? 'hidden' : '';
}

export function overlay(id) {
  const el = document.getElementById(id);
  const panel = el.querySelector('.overlay-panel');
  const content = el.querySelector('[data-overlay-content]');
  let returnFocus = null;
  let onClose = null;

  const api = {
    el,
    content,
    isOpen: () => el.classList.contains('is-open'),
    open({ html, label, closeHandler } = {}) {
      if (html !== undefined) content.innerHTML = html;
      if (label) panel.setAttribute('aria-label', label);
      onClose = closeHandler || null;
      if (!api.isOpen()) {
        returnFocus = document.activeElement;
        el.classList.add('is-open');
        el.setAttribute('aria-hidden', 'false');
        openStack.push(api);
        syncInert();
      }
      content.scrollTop = 0;
      panel.focus({ preventScroll: true });
    },
    close() {
      if (!api.isOpen()) return;
      el.classList.remove('is-open');
      el.setAttribute('aria-hidden', 'true');
      const index = openStack.indexOf(api);
      if (index >= 0) openStack.splice(index, 1);
      syncInert();
      const handler = onClose;
      onClose = null;
      handler?.();
      returnFocus?.focus?.({ preventScroll: true });
    },
  };

  el.addEventListener('click', event => {
    if (event.target.closest('[data-overlay-close]')) api.close();
  });

  return api;
}

document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && openStack.length) {
    event.preventDefault();
    openStack[openStack.length - 1].close();
  }
});
