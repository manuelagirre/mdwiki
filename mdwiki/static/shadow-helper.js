// Shared helper every widget uses for encapsulation: attaches a Shadow DOM
// to the widget's host element, loads that widget's own CSS into the shadow
// root, and hands the caller an empty container to render into.
//
// Usage, from a widget's own widget.js:
//
//   import { mountWidget } from '/_assets/shadow-helper.js';
//   document.querySelectorAll('[data-widget="my-widget"]').forEach((host) => {
//     mountWidget(host, (container) => {
//       container.innerHTML = `<p>hi, param = ${host.getAttribute('param')}</p>`;
//     });
//   });

export function mountWidget(host, buildFn) {
  const name = host.dataset.widget;
  const shadow = host.attachShadow({mode: 'open'});

  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = `/_widgets/${name}/widget.css`;
  shadow.appendChild(link);

  const container = document.createElement('div');
  shadow.appendChild(container);

  buildFn(container, host);
  return {shadow, container};
}
