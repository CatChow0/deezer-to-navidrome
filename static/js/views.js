// Dashboard ⇄ Settings: one page, two views; the topbar switch slides between
// them and keeps the URL in sync (/ and /config) without reloading.

const TITLES = {
  dashboard: 'Deezer → Navidrome',
  settings: 'Settings · Deezer → Navidrome',
};

let current = null;

function urlFor(name) {
  return document.querySelector(`.view-switch [data-view-link="${name}"]`)?.getAttribute('href') || '/';
}

export function showView(name, { push = true } = {}) {
  const target = document.querySelector(`.view[data-view-name="${name}"]`);
  if (!target || name === current) return;

  document.querySelectorAll('.view').forEach(view => {
    const active = view === target;
    view.classList.toggle('is-active', active);
    view.inert = !active;
  });

  const nav = document.querySelector('.view-switch');
  if (nav) nav.dataset.active = name;
  document.querySelectorAll('.view-switch [data-view-link]').forEach(link => {
    if (link.dataset.viewLink === name) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });

  current = name;
  document.title = TITLES[name] || document.title;
  if (push) history.pushState({ view: name }, '', urlFor(name));

  // Bring the top of the new view into sight if the page was scrolled down.
  const top = document.querySelector('.views').getBoundingClientRect().top + window.scrollY - 120;
  if (window.scrollY > top) window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
}

export function initViews() {
  const root = document.querySelector('.views');
  if (!root) return;
  current = root.dataset.view;
  history.replaceState({ view: current }, '');

  document.addEventListener('click', event => {
    const link = event.target.closest('[data-view-link]');
    if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    showView(link.dataset.viewLink);
  });

  window.addEventListener('popstate', event => {
    const name = event.state?.view || (location.pathname.startsWith('/config') ? 'settings' : 'dashboard');
    showView(name, { push: false });
  });
}
