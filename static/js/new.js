// New: the notes of each version, one tab each, on the latest when opened.
// Opening it counts as read: the dot on the button goes, and stays gone.

import { fetchJSON, on } from './core.js';

export function initNew(modal) {
  const tabs = [...modal.el.querySelectorAll('[data-new-tab]')];
  const article = modal.el.querySelector('[data-new-article]');

  function showVersion(version, { focus = false } = {}) {
    tabs.forEach(tab => {
      const active = tab.dataset.newTab === version;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      if (active) {
        if (focus) tab.focus();
        tab.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      }
    });
    modal.el.querySelectorAll('[data-new-panel]').forEach(panel => {
      panel.hidden = panel.dataset.newPanel !== version;
    });
    article.scrollTop = 0;
  }

  function open() {
    showVersion(tabs[0].dataset.newTab);
    modal.open({ label: "What's new" });
    const dot = document.querySelector('.new-dot');
    if (!dot) return;
    dot.remove();
    document.querySelector('[data-action="new"]').setAttribute('aria-label', "What's new");
    fetchJSON('/api/whats-new/seen', { json: {} });
  }

  on(modal.el, 'click', '[data-new-tab]', (_, tab) => showVersion(tab.dataset.newTab));
  on(modal.el, 'keydown', '[data-new-tab]', (event, tab) => {
    const horizontal = getComputedStyle(tab.parentElement).flexDirection === 'row';
    const next = horizontal ? 'ArrowRight' : 'ArrowDown';
    const previous = horizontal ? 'ArrowLeft' : 'ArrowUp';
    let index = tabs.indexOf(tab);
    if (event.key === next) index += 1;
    else if (event.key === previous) index -= 1;
    else if (event.key === 'Home') index = 0;
    else if (event.key === 'End') index = tabs.length - 1;
    else return;
    event.preventDefault();
    showVersion(tabs[(index + tabs.length) % tabs.length].dataset.newTab, { focus: true });
  });
  // The repair runs in Activity: close the panel so it can be followed.
  on(modal.el, 'click', '[data-action="repair-downloads"]', () => modal.close());
  on(document, 'click', '[data-action="new"]', open);
}
