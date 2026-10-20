// Dashboard ⇄ Settings: one page, two views; the topbar switch slides between
// them and keeps the URL in sync (/ and /config) without reloading.

const TITLES = {
  dashboard: 'Deezer → Navidrome',
  releases: 'Releases · Deezer → Navidrome',
  settings: 'Settings · Deezer → Navidrome',
};

const listeners = new Set();

// listener(name) runs every time a view is shown, including the first one.
export function onViewShown(listener) {
  listeners.add(listener);
  if (current) listener(current);
}

// Hidden views wait on the side they will slide in from.
function placeViews(active) {
  const views = [...document.querySelectorAll('.view')];
  const index = views.findIndex(view => view.dataset.viewName === active);
  views.forEach((view, i) => {
    view.dataset.pos = i < index ? 'before' : i > index ? 'after' : 'current';
  });
}

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
  placeViews(name);

  const nav = document.querySelector('.view-switch');
  if (nav) nav.dataset.active = name;
  document.querySelectorAll('.view-switch [data-view-link]').forEach(link => {
    if (link.dataset.viewLink === name) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });

  current = name;
  document.title = TITLES[name] || document.title;
  listeners.forEach(listener => listener(name));
  if (push) history.pushState({ view: name }, '', urlFor(name));

  // Bring the top of the new view into sight if the page was scrolled down.
  const top = document.querySelector('.views').getBoundingClientRect().top + window.scrollY - 120;
  if (window.scrollY > top) window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
}

export function initViews() {
  const root = document.querySelector('.views');
  if (!root) return;
  current = root.dataset.view;
  placeViews(current);
  history.replaceState({ view: current }, '');

  document.addEventListener('click', event => {
    const link = event.target.closest('[data-view-link]');
    if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    showView(link.dataset.viewLink);
  });

  window.addEventListener('popstate', event => {
    const fromPath = location.pathname.startsWith('/config') ? 'settings' : location.pathname.startsWith('/releases') ? 'releases' : 'dashboard';
    const name = event.state?.view || fromPath;
    showView(name, { push: false });
  });
}
