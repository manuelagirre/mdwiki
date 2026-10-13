# Feature Index

| Feature | Category | Domain(s) | What it does |
|---|---|---|---|
| [Page Routing](features/Page-Routing.md) | Request Serving | Python Server | URL path to `.md` relpath; `<path>.md` then `<path>/index.md`; root via `index:` override then `index.md`; traversal and missing both plain 404. |
| [Page Shell & Asset Serving](features/Page-Shell-and-Asset-Serving.md) | Request Serving | Python Server, Browser Client | `mdwiki serve` launch, FastAPI app, `page.html` Jinja shell (nav, back link, content), `/_assets` theme/static files. |
| [Markdown Rendering](features/Markdown-Rendering.md) | Content Rendering | Python Server | Frontmatter parse, title pick, Python-Markdown convert with fixed extension set, `RenderedPage` build. |
| [Internal Link Rewriting](features/Internal-Link-Rewriting.md) | Content Rendering | Python Server | Rewrite `<a href>` `X.md`/`dir/index.md` to extension-less served URLs. |
| [Mermaid Diagram Rendering](features/Mermaid-Diagram-Rendering.md) | Content Rendering | Python Server, Browser Client | ```` ```mermaid ```` fence to `<pre class="mermaid">`; page loads pinned mermaid.js only when needed. |
| [Widget Injection](features/Widget-Injection.md) | Widget System | Python Server, Browser Client | Macro and hook widget placement, widget resolution, `toast` fallback, Shadow-DOM mount via `mountWidget`. |
| [Standard Widgets](features/Standard-Widgets.md) | Widget System | Python Server, Browser Client | Built-in `toast` and `next-button` widgets. |
| [Page Ordering](features/Page-Ordering.md) | Site Management | Python Server | `_order.yml` per dir, global DFS page order, next-page lookup, `mdwiki order` edits. |
| [Site Validation](features/Site-Validation.md) | Site Management | Python Server | `mdwiki validate`: order manifests, widget refs, dangling links, broken anchors. |
| [Site Configuration Loading](features/Site-Configuration-Loading.md) | Site Management | Python Server | Load `mdwiki.yml` into `SiteConfig` (title, nav, theme, backend_base, widget hooks, index). |
