// Whose Navidrome and Deezer accounts Settings → Accounts shows: yours, or for
// an Admin another account's. The account routes take it as ?user=.

let current = '';

export const subject = () => current;

export function scoped(url) {
  return current ? `${url}${url.includes('?') ? '&' : '?'}user=${encodeURIComponent(current)}` : url;
}

export function setSubject(id) {
  current = id || '';
  document.dispatchEvent(new CustomEvent('d2n:subject'));
}

// Switches for picking several of `items` ({id, label}), those in `chosen` on.
export function checks(name, items, chosen, escape) {
  return items.map(item => `
    <label class="toggle"><span class="switch"><input type="checkbox" name="${name}" value="${escape(item.id)}"
      ${chosen.includes(item.id) ? 'checked' : ''}><span class="switch-slider"></span></span>${escape(item.label)}</label>`).join('');
}
