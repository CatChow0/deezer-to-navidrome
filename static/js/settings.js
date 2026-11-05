// Settings view: mappings editor, saving without leaving the page, and the
// two-click confirmation on reset buttons.

import { armed, on, toast } from './core.js';

export function initSettings() {
  const form = document.getElementById('settings-form');
  if (!form) return;

  const mappings = document.getElementById('mappings');
  const template = document.getElementById('mapping-template');
  const saveBar = form.querySelector('[data-save-bar]');
  const showSaveBar = () => {
    saveBar.hidden = false;
  };

  form.addEventListener('input', showSaveBar);
  form.addEventListener('change', showSaveBar);

  on(form, 'click', '[data-action="add-mapping"]', () => {
    mappings.appendChild(template.content.cloneNode(true));
    mappings.lastElementChild.querySelector('input')?.focus();
    showSaveBar();
  });

  on(form, 'click', '[data-action="remove-mapping"]', (_, btn) => {
    btn.closest('.mapping-row')?.remove();
    showSaveBar();
  });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    button.textContent = 'Saving…';

    try {
      const resp = await fetch(form.action, { method: 'POST', body: new FormData(form) });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      toast('Settings saved', { tone: 'ok' });
      saveBar.hidden = true;
    } catch (err) {
      toast(`Settings were not saved: ${err.message}`, { tone: 'error' });
    } finally {
      button.disabled = false;
      button.textContent = 'Save settings';
    }
  });

  // Reset buttons still submit normally: the page reloads on Settings with the
  // result, and the background carries over thanks to the session.
  document.querySelectorAll('[data-confirm-form]').forEach(resetForm => {
    resetForm.addEventListener('submit', event => {
      if (!armed(resetForm.querySelector('button'), resetForm.dataset.confirmForm)) event.preventDefault();
    });
  });
}
