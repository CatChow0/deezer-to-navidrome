import { armed, on, showFlashMessages } from './core.js';
import { initBackground } from './background.js';
import { initVersion } from './version.js';
import { initLibrary } from './library.js';

initBackground();
initVersion();
showFlashMessages();
initLibrary();

const mappings = document.getElementById('mappings');
const template = document.getElementById('mapping-template');

on(document, 'click', '[data-action="add-mapping"]', () => {
  mappings.appendChild(template.content.cloneNode(true));
  mappings.lastElementChild.querySelector('input')?.focus();
});

on(document, 'click', '[data-action="remove-mapping"]', (_, btn) => {
  btn.closest('.mapping-row')?.remove();
});

// Every danger zone button asks for a second click before submitting.
document.querySelectorAll('[data-confirm-form]').forEach(form => {
  form.addEventListener('submit', event => {
    if (!armed(form.querySelector('button'), form.dataset.confirmForm)) event.preventDefault();
  });
});
