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

    if (!href) {
      container.innerHTML = '<p class="next-button-empty">No next page.</p>';
      return;
    }
    container.innerHTML = `<a class="next-button" href="${href}">${label} &rarr;</a>`;
  });
});
