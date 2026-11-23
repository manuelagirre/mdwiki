// Standard widget: a "next page" link/button. Its target is resolved by
// core from the page ordering manifest (_order.yml) and passed in as the
// `href`/`label` params - this widget itself does no ordering logic, it
// just renders whatever core handed it.
//
// Usually auto-injected via a hook row in mdwiki.yml (e.g.
// `next-button, bottom, lessons/*`), but also usable directly:
// {{ widget: next-button href="/lessons/loops" label="Next Lesson" }}

import {mountWidget} from '/_assets/shadow-helper.js';

document.querySelectorAll('[data-widget="next-button"]').forEach((host) => {
  mountWidget(host, (container) => {
    const href = host.getAttribute('href');
    const label = host.getAttribute('label') || 'Next';

    // textContent, never innerHTML: the label is usually the next page's
    // title, and getAttribute() hands it back HTML-decoded - a title like
    // `Generics <T>` must show as text, not be parsed as a tag.
    if (!href) {
      const empty = document.createElement('p');
      empty.className = 'next-button-empty';
      empty.textContent = 'No next page.';
      container.appendChild(empty);
      return;
    }
    const link = document.createElement('a');
    link.className = 'next-button';
    link.setAttribute('href', href);
    link.textContent = `${label} \u2192`;
    container.appendChild(link);
  });
});
