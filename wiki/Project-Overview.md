# mdwiki — Project Overview

Python package + CLI. Point at directory of markdown files, get served wiki. No DB, no business-logic coupling. Own ASGI process (FastAPI + uvicorn), own port. Widgets = ES modules mounted in Shadow DOM.

## Domains

| Domain | Runtime | Page |
|---|---|---|
| Python Server | Python 3.11+, FastAPI under uvicorn, `mdwiki` CLI | [Python Server](domains/Python-Server.md) |
| Browser Client | Browser: Jinja-rendered page shell, ES modules, Shadow DOM, mermaid.js CDN | [Browser Client](domains/Browser-Client.md) |

Support, not domains: `example/` (worked example site, used by tests), `tests/` (pytest, Python only), `README.md`.

## Terminology

- **Project** — everything in repo.
- **Domain** — large piece reflecting one side of project; own runtime, language, deployment story.
- **Feature** — piece of logic doing exactly one thing; may span domains; contains many Code Elements.
- **Code Element** — file, method within class, or config object (whole file or single element).
- **Feature entry point** — where feature execution starts: user action, API/HTTP route, CLI command, event. Grounded in concrete route/handler/trigger.
- **Feature output** — end result: HTTP response, file written, DOM rendered, stdout message. Grounded in concrete write/call/response.
- **Use-case** — exact flow from one entry point to one output. Only real paths. Documented with mermaid `sequenceDiagram`, marked Covered (named test) or Uncovered.
- **Feature category** — project-wide logical grouping of features.
- **Feature dependency** — directed typed link between two features: `data-model sharing` (same data shape, neither calls other), `parent-child` (extension point vs implementation), `runtime call` (in-process invocation).
- **Shared contract** — exact field/config key/template var/selector/URL that lets one feature's Code Elements interoperate across domain boundary. Fails silently on drift.
- **Fragility point** — plausible upgrade direction grounded in code: hardcoded constant, unread config key, single-case switch, missing fallback. Never roadmap wish.
- **Fragility note** — how quietly feature fails if broken, who notices first. Sound feature gets one line saying so.

## Categories

| Category | Features |
|---|---|
| Request Serving | [Page Routing](features/Page-Routing.md), [Page Shell & Asset Serving](features/Page-Shell-and-Asset-Serving.md) |
| Content Rendering | [Markdown Rendering](features/Markdown-Rendering.md), [Internal Link Rewriting](features/Internal-Link-Rewriting.md), [Mermaid Diagram Rendering](features/Mermaid-Diagram-Rendering.md) |
| Widget System | [Widget Injection](features/Widget-Injection.md), [Standard Widgets](features/Standard-Widgets.md) |
| Site Management | [Page Ordering](features/Page-Ordering.md), [Site Validation](features/Site-Validation.md), [Site Configuration Loading](features/Site-Configuration-Loading.md) |

Full list: [Feature Index](Feature-Index.md).

## Status quo

- Request: `GET /<path>` resolves to `<path>.md` or `<path>/index.md` under content root. No `.md` match: existing content-root file served raw at literal path (author `.html` in full, no page shell; images, css). `.md` sources, `_order.yml`, dot-paths never served raw.
- Render: frontmatter, Python-Markdown with fixed extensions, `.md` link rewrite, mermaid fences, widget macros + config hooks, wrapped in theme `page.html`.
- Assets: `/_assets/*` (theme dir then `mdwiki/static/`), `/_widgets/<name>/*` (host widgets dir then standard set).
- Authoring tools: `mdwiki validate`, `mdwiki order`.

## Python Server

FastAPI app from `server.create_app`; CLI `mdwiki` in `cli.py`. Details: [Python Server](domains/Python-Server.md).

Run:

```bash
pip install -e .
mdwiki serve --dir ./example --config ./example/mdwiki.yml --port 8000
pytest
```

## Browser Client

Shell `theme/page.html` + `theme/app.css`, `static/shadow-helper.js`, standard widgets `widgets/{toast,next-button}/`. Details: [Browser Client](domains/Browser-Client.md).

Run: served by Python Server; open `http://localhost:8000/`.
