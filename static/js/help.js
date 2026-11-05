// Help: the documentation of the app. A table of contents, one article at a
// time, and a search across all of them, with live checks of the setup in
// Getting started.

import { escapeHtml, fetchJSON, on } from './core.js';
import { planBadge } from './account.js';

const fold = text => text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();

async function checkAccount(root) {
  const step = root.querySelector('[data-help-account]');
  const line = step.querySelector('[data-help-account-status]');
  const dot = step.querySelector('.dot');
  const { ok, data } = await fetchJSON('/api/deezer/account');
  const connected = ok && data?.connected;
  dot.className = `dot ${connected ? 'dot--ok' : 'dot--miss'}`;
  line.classList.toggle('help-live--warn', !connected);
  if (connected) {
    line.innerHTML = `Connected as <b>${escapeHtml(data.name)}</b> ${planBadge(data)}`;
  } else {
    line.textContent = data?.error ? `Not connected: ${data.error}` : 'Not connected yet.';
  }
}

export function initHelp(modal) {
  const root = modal.el;
  const article = root.querySelector('[data-doc-article]');
  const search = root.querySelector('[data-doc-search]');
  const none = root.querySelector('[data-doc-none]');
  const status = root.querySelector('[data-doc-status]');
  const select = root.querySelector('[data-doc-select]');
  const links = [...root.querySelectorAll('.doc-toc [data-doc-go]')];
  const sections = [...root.querySelectorAll('[data-doc-section]')];
  // Every section is made of blocks: the search shows or hides whole blocks,
  // so an answer always keeps its heading.
  const blocks = sections.flatMap(section => [...section.querySelectorAll('.doc-block')].map(block => ({
    section: section.dataset.docSection,
    el: block,
    text: fold(block.textContent),
  })));
  let current = sections[0].dataset.docSection;

  function showSection(name) {
    current = name;
    sections.forEach(section => {
      section.hidden = section.dataset.docSection !== name;
    });
    blocks.forEach(block => {
      block.el.hidden = false;
    });
    links.forEach(link => {
      link.classList.remove('is-dim');
      link.querySelector('.doc-count')?.remove();
      if (link.dataset.docGo === name) link.setAttribute('aria-current', 'true');
      else link.removeAttribute('aria-current');
    });
    select.value = name;
    none.hidden = true;
    status.textContent = '';
    article.scrollTop = 0;
  }

  function goTo(name) {
    search.value = '';
    showSection(name);
  }

  function runSearch() {
    const words = fold(search.value).split(/\s+/).filter(Boolean);
    if (!words.length) {
      showSection(current);
      return;
    }
    const found = new Map();
    blocks.forEach(block => {
      const match = words.every(word => block.text.includes(word));
      block.el.hidden = !match;
      if (match) found.set(block.section, (found.get(block.section) || 0) + 1);
    });
    sections.forEach(section => {
      section.hidden = !found.has(section.dataset.docSection);
    });
    links.forEach(link => {
      const count = found.get(link.dataset.docGo) || 0;
      link.removeAttribute('aria-current');
      link.classList.toggle('is-dim', !count);
      link.querySelector('.doc-count')?.remove();
      if (count) link.insertAdjacentHTML('beforeend', `<span class="doc-count">${count}</span>`);
    });
    const total = [...found.values()].reduce((sum, count) => sum + count, 0);
    none.hidden = total > 0;
    if (!total) none.querySelector('[data-doc-word]').textContent = search.value.trim();
    status.textContent = total ? `${total} ${total === 1 ? 'answer' : 'answers'}` : '';
    article.scrollTop = 0;
  }

  search.addEventListener('input', runSearch);
  search.addEventListener('keydown', event => {
    // Escape empties the search first; pressed again it closes the panel.
    if (event.key === 'Escape' && search.value) {
      event.preventDefault();
      event.stopPropagation();
      search.value = '';
      runSearch();
    }
  });
  select.addEventListener('change', () => goTo(select.value));
  on(root, 'click', '[data-doc-go]', (event, link) => {
    event.preventDefault();
    goTo(link.dataset.docGo);
  });
  // The view switch happens behind the panel: close it first.
  on(root, 'click', '[data-help-settings]', () => modal.close());
  // The repair runs in Activity: close the panel so it can be followed.
  on(root, 'click', '[data-action="repair-downloads"]', () => modal.close());
  on(document, 'click', '[data-action="help"]', () => {
    modal.open({ label: 'Help' });
    checkAccount(root);
    search.focus();
  });

  showSection(current);
}
