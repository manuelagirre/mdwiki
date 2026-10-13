# Serve Author HTML And Static Files

**Status:** Proposed
**Created:** 2026-10-13
**Story:** none (project has no story-number convention; branch `serve-plain-html`)
**Waiting on:** user — design review (step 4)

## Workflow Status

| # | Step | Actor | Status | Date | Note |
|---|---|---|---|---|---|
| 1 | Investigate codebase | agent | done | 2026-10-13 | `wiki-investigate`: Page Routing, Page Shell & Asset Serving, Site Validation, Internal Link Rewriting. User picked: wrap HTML in shell, URL `/foo.html` only, any static file passthrough. |
| 2 | Design solution, write into backlog item | agent | done | 2026-10-13 | Solution Design below. |
| 3 | Report open questions | agent | done | 2026-10-13 | None open; design defaults (full-doc body extraction, no widgets/markdown on HTML pages, `.md`/dotfiles/`_order.yml` never raw) flagged for review in step 4. |
| 4 | Design review | user | pending | | |
| 5 | Design approved | agent | pending | | |
| 6 | Implement + deploy | agent | pending | | |
| 7 | Automated tests | agent | pending | | |
| 8 | E2E tests (if applicable) | agent | pending | | |
| 9 | Review the changes | user | pending | | |
| 10 | Address requested changes | agent | pending | | |
| 11 | Roll out into wiki, retire the backlog item | agent | pending | | |
| 12 | Publish external doc | agent | pending | | |

## Goal

Author drops hand-written `foo.html` next to `foo.md` in content root; mdwiki serves it at `/foo.html` inside site page shell (nav, theme). Also serve any other static file under content root raw (images, css, js, pdf) — so HTML pages and markdown pages can reference sibling assets. Today `resolve_url` builds only `.md` candidates: `/foo.html` and `/pic.png` 404 even when file exists.

## Scope

In:
- `GET /<path>.html` for existing content-root `.html` file: body wrapped in theme `page.html` (nav, back link none, title).
- `GET /<path>` for any other existing content-root file: raw `FileResponse`, content-type from extension.
- `mdwiki validate`: links to `.html`/static files count as resolving; `.html` pages' own `<a href>`s and `#fragment`s checked like `.md` pages.
- README "Routing" + "Cross-links" sections, `link_rewrite.py` docstring (says "no static passthrough").
- Tests.

Out:
- Extension-less `/foo` serving `foo.html` (user chose `/foo.html` only).
- Markdown processing, widget macros, widget hooks, mermaid on `.html` pages — HTML served as authored.
- `.html` pages in `_order.yml` / `next-button` sequencing (`ordering.py` stays `.md`-only).
- Raw serving of `.md` source (`/foo.md` stays 404, Page Routing UC7 unchanged), dotfiles, `_order.yml`.
- Reserved `/_assets`, `/_widgets` prefix shadowing (Page Routing fragility point, unchanged).

## Domains

- [Python Server](../domains/Python-Server.md) — routing, rendering, validation all change here.
- [Browser Client](../domains/Browser-Client.md) — no code change; `page.html` reused as-is for HTML pages (same context keys).

## Features

- [Page Routing](../features/Page-Routing.md) — new fallback after `.md` candidates: content-root file resolution.
- [Page Shell & Asset Serving](../features/Page-Shell-and-Asset-Serving.md) — `_page` route branches: shell-wrapped HTML response vs raw `FileResponse`.
- [Markdown Rendering](../features/Markdown-Rendering.md) — sibling path producing `RenderedPage` from `.html` (no markdown convert).
- [Site Validation](../features/Site-Validation.md) — link resolution accepts files; sweep includes `.html` pages.
- [Internal Link Rewriting](../features/Internal-Link-Rewriting.md) — no code change; its non-`.md` passthrough now lands on a served URL (closes its UC4 dead-link outcome for existing files).

## Use Cases

- Page Routing **UC8: Non-md File Path -> 404 Not Found** — changes: for an existing file, now served (below); 404 only when file missing or excluded.
- Page Routing **UC10: HTML File Path -> Shell-Wrapped HTML Rendered (new)** — `GET /foo.html`, `foo.html` exists, no `foo.html.md`: body in `page.html`.
- Page Routing **UC11: Static File Path -> Raw File Served (new)** — `GET /img/a.png`: bytes with guessed content-type.
- Page Routing **UC12: Excluded File Path -> 404 Not Found (new)** — `.md`, dotfile/dot-dir, `_order.yml`: still plain 404.
- Internal Link Rewriting **UC4: Non-Markdown Href -> Unchanged -> Dead Link** — href still unchanged; resolves when target file exists.
- Site Validation **UC4: Internal Link -> Dangling Path or Missing Anchor Issue** — `.html`/static targets resolve; `#frag` on `.html` target checked against its `id=`s.
- Site Validation **UC6: HTML Page Link -> Dangling Path or Missing Anchor Issue (new)** — links inside `.html` pages checked.

## Code Elements

| Code Element | File | Change needed |
|---|---|---|
| `WikiRenderer.resolve_url` | mdwiki/render.py | Unchanged (still `.md` only, raises `PageNotFound`). |
| `WikiRenderer.resolve_file` (new) | mdwiki/render.py | URL path -> content-root relpath of existing non-excluded file via `_safe_join`; `PageNotFound` otherwise. |
| `WikiRenderer.render_html_relpath` (new) | mdwiki/render.py | Read `.html`; full document -> `<body>` inner + `<title>`; fragment -> as-is; title fallback first `<h1>` text, then `_page_title` filename rule. Returns `RenderedPage(has_mermaid=False, back_link=None)`. |
| `WikiRenderer.page_exists` | mdwiki/render.py | Unchanged; validate uses new `resolve_file` alongside. |
| `relpath_to_url` | mdwiki/render.py | Non-`.md` relpath -> `/` + relpath (extension kept). |
| `_page` / `_render_response` | mdwiki/server.py | Try `.md` page; on `PageNotFound` try `resolve_file`: `.html`/`.htm` -> shell via `render_html_relpath`; else `FileResponse`. Miss -> existing 404 handler. |
| `_check_links`, `_all_md_files` | mdwiki/validate.py | Sweep `.md` + `.html`; target resolves if `page_exists` or `resolve_file` hits; anchor ids from rendered `.html` too. Raw static targets: existence only, no anchor check. |
| module docstring | mdwiki/link_rewrite.py | Drop "no static passthrough" claim. |
| "Routing", "Cross-links" sections | README.md | Document HTML + static serving, exclusions, precedence. |
| tests | tests/test_render.py (or new tests/test_static.py) | UC10-UC12, precedence, traversal, validate cases. |

## Solution Design

1. **Resolution order** in `server._page` (catch-all, after `/_assets`, `/_widgets`):
   1. Existing `.md` resolution (`<path>.md`, `<path>/index.md`) — unchanged, so no current URL changes meaning.
   2. `resolve_file(url_path)`: `_safe_join(url_path)` (same traversal guard, same plain 404), must be `is_file()`.
   3. Neither -> `PageNotFound` -> existing plain `Not found` 404 (traversal and missing still indistinguishable).
2. **Exclusions** in `resolve_file` -> `PageNotFound`: suffix `.md`; any path segment starting `.` (covers `.wiki-manifest.json`, `.git/`); basename `_order.yml`. Hardcoded tuple, not config (YAGNI); README lists it.
3. **HTML in shell**: suffix `.html`/`.htm` (case-insensitive) -> `render_html_relpath` -> same `templates.TemplateResponse("page.html", ...)` context as `.md` (`content` = HTML, `has_mermaid=False`, `back_link=None`). Full-document detection: regex on `<body[^>]*>(.*)</body>` (DOTALL, case-insensitive); `<title>` regex for title. No HTML parser dependency. Author content trusted same as markdown (`content|safe` already).
4. **Raw files**: `FileResponse(path)` — Starlette guesses content-type via `mimetypes`. No caching headers (matches `/_assets`).
5. **No widgets/markdown/mermaid** on HTML pages: hooks not applied even if `selector` matches `*.html` — `WidgetHook` selectors today target `.md` relpaths; keeps HTML "as authored".
6. **Validate**: `_all_md_files` generalized to sweep `*.md` + `*.html`/`*.htm` (excluding dot-paths); per page URL from `relpath_to_url`; `urljoin` relative resolution already correct for `/foo.html` base. Link target OK if `page_exists(target)` or `resolve_file(target)` succeeds.

Contracts respected:
- Page Shell & Asset Serving Shared Contract: Jinja keys `site_title`, `title`, `content`, `back_link`, `nav`, `backend_base`, `has_mermaid`, `request_path` — all supplied, no new key; theme overrides keep working.
- Internal Link Rewriting -> Page Routing `data-model sharing` (extension-less URL shape): untouched; `.html` links pass through unchanged and now resolve at literal path.
- Precedence: `.md` resolution always first, so `foo.html.md` (odd but legal) still wins at `/foo.html`.

Fragility points closed:
- Page Routing: "Only `.md` candidates built ... No passthrough for other files" — closed.
- Internal Link Rewriting: "Non-`.md` targets pass through ... route 404s" — closed for existing files.
- Not closed: reserved-prefix shadowing, direct `.md` URL 404 (kept deliberately).
