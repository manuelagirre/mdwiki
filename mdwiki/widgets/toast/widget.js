// Standard widget: a colored panel with bold title + text, three stylings.
// Params: title (optional), text, style ("info" | "warning" | "error",
// default "info"). Also the built-in not-found fallback (rendered with
// style="error"), but directly usable by authors like any other widget:
// {{ widget: toast title="Note" text="..." style="info" }}

import {mountWidget} from '/_assets/shadow-helper.js';

document.querySelectorAll('[data-widget="toast"]').forEach((host) => {
  mountWidget(host, (container) => {
    const title = host.getAttribute('title') || '';
    const text = host.getAttribute('text') || '';
    const style = host.getAttribute('style') || 'info';

    container.innerHTML = `
      <div class="toast toast-${style}">
        ${title ? `<strong class="toast-title">${title}</strong>` : ''}
        <span class="toast-text">${text}</span>
      </div>
    `;
  });
});
