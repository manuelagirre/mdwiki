// Standard widget: a colored panel with bold title + text, three stylings.
// Params: title (optional), text, style ("info" | "warning" | "error",
// default "info"). Also the built-in not-found fallback (rendered with
// style="error"), but directly usable by authors like any other widget:
// {{ widget: toast title="Note" text="..." style="info" }}

import {mountWidget} from '/_assets/shadow-helper.js';

const STYLES = ['info', 'warning', 'error'];

document.querySelectorAll('[data-widget="toast"]').forEach((host) => {
  mountWidget(host, (container) => {
    const title = host.getAttribute('title') || '';
    const text = host.getAttribute('text') || '';
    const requested = host.getAttribute('style');
    const style = STYLES.includes(requested) ? requested : 'info';

    // Built with textContent, never innerHTML: params arrive HTML-decoded
    // by getAttribute(), so interpolating them into markup would re-parse
    // author text (a `<T>` in a title, say) as HTML.
    const panel = document.createElement('div');
    panel.className = `toast toast-${style}`;
    if (title) {
      const strong = document.createElement('strong');
      strong.className = 'toast-title';
      strong.textContent = title;
      panel.appendChild(strong);
    }
    const span = document.createElement('span');
    span.className = 'toast-text';
    span.textContent = text;
    panel.appendChild(span);
    container.appendChild(panel);
  });
});
