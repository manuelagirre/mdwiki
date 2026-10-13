# Browser Client

Code that runs in reader's browser. Jinja page shell (rendered server-side, executed client-side), theme CSS, ES-module widget runtime with Shadow DOM, mermaid.js from CDN. No bundler, no `package.json`, no browser tests.

## File tree

```
mdwiki/
  theme/
    page.html          Jinja shell: nav, back link, content, backend_base, mermaid loader
    app.css            layout, typography, admonitions, .mdwiki-widget, pre.mermaid, pasted Pygments .codehilite
  static/
    shadow-helper.js   mountWidget(host, buildFn)
  widgets/
    toast/
      widget.js
      widget.css
    next-button/
      widget.js
      widget.css
```

## How to run

Served by Python Server: `/_assets/<file>` (theme dir then `static/`), `/_widgets/<name>/<file>`. Open `http://localhost:8000/` after `mdwiki serve`.

## Features touching this domain

| Feature | Category | Role here |
|---|---|---|
| [Page Shell & Asset Serving](../features/Page-Shell-and-Asset-Serving.md) | Request Serving | `page.html`, `app.css`, `window.MDWIKI_BACKEND_BASE`. |
| [Mermaid Diagram Rendering](../features/Mermaid-Diagram-Rendering.md) | Content Rendering | Inline module script loading `mermaid@11.17.2`. |
| [Widget Injection](../features/Widget-Injection.md) | Widget System | `shadow-helper.js` `mountWidget`. |
| [Standard Widgets](../features/Standard-Widgets.md) | Widget System | `toast` and `next-button` JS/CSS. |
