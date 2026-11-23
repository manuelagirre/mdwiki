// Standard widget: a "previous page" link - next-button's counterpart.
// Its target is resolved by core from the page ordering manifest
// (_order.yml) and passed in as the `href`/`label` params; this widget
// does no ordering logic itself.
//
// Usually auto-injected via a hook row in mdwiki.yml, alongside
// next-button (`prev-button, bottom, lessons/*`), but also usable directly:
// {{ widget: prev-button href="/lessons/intro" label="Introduction" }}

import {mountWidget} from '/_assets/shadow-helper.js';

document.querySelectorAll('[data-widget="prev-button"]').forEach((host) => {
  mountWidget(host, (container) => {
    const href = host.getAttribute('href');
    if (!href) return; // first page in the sequence: render nothing
    const link = document.createElement('a');
    link.className = 'prev-button';
    link.setAttribute('href', href);
    // textContent, never innerHTML - the label is a page title.
    link.textContent = `← ${host.getAttribute('label') || 'Previous'}`;
    container.appendChild(link);
  });
});
