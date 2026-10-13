# Serve Author HTML And Static Files

**Status:** Proposed
**Created:** 2026-10-13
**Story:** none (project has no story-number convention; branch `serve-plain-html`)
**Waiting on:** user — review changes (step 9); also decide whether to reinstall system mdwiki copy

## Workflow Status

| # | Step | Actor | Status | Date | Note |
|---|---|---|---|---|---|
| 1 | Investigate codebase | agent | done | 2026-10-13 | `wiki-investigate`: Page Routing, Page Shell & Asset Serving, Site Validation, Internal Link Rewriting. User picked: wrap HTML in shell, URL `/foo.html` only, any static file passthrough. |
| 2 | Design solution, write into backlog item | agent | done | 2026-10-13 | Solution Design below. |
| 3 | Report open questions | agent | done | 2026-10-13 | None open; design defaults (full-doc body extraction, no widgets/markdown on HTML pages, `.md`/dotfiles/`_order.yml` never raw) flagged for review in step 4. |
| 4 | Design review | user | done | 2026-10-13 | User correction: HTML served in full as authored, NOT wrapped in page shell. Design revised to raw passthrough for all files. |
| 5 | Design approved | agent | done | 2026-10-13 | Approved with step-4 correction applied. |
| 6 | Implement + deploy | agent | done | 2026-10-13 | `4ace731`: render.py `resolve_file`/`file_path`/`relpath_to_url`, server.py `_page` fallback, validate.py HTML sweep + raw targets, README, link_rewrite docstring. No deploy process (library). System `/usr/local/lib/python3.11/dist-packages/mdwiki` is non-editable copy, NOT updated — needs user OK. |
| 7 | Automated tests | agent | done | 2026-10-13 | `ba63926`: tests/test_static_files.py, 8 tests. Full suite 36 passed (pytest from scratch `--target` dir; repo has no pytest installed). |
| 8 | E2E tests (if applicable) | agent | done | 2026-10-13 | No e2e tooling in repo. Live smoke: `python -m mdwiki serve` on scratch site, curl: `/r/page.html` 200 text/html byte-identical, `/r/a.svg` 200 image/svg+xml, `/index.md` 404, missing 404. No records created. |
| 9 | Review the changes | user | pending | | |
| 10 | Address requested changes | agent | pending | | |
| 11 | Roll out into wiki, retire the backlog item | agent | pending | | |
| 12 | Publish external doc | agent | pending | | |

## Goal

Author drops hand-written `foo.html` next to `foo.md` in content root; mdwiki serves it at `/foo.html` in full, exactly as authored (own `<head>`, styles, scripts — no mdwiki nav/theme). Same raw passthrough for any other static file under content root (images, css, js, pdf), so HTML pages and markdown pages can reference sibling assets. Today `resolve_url` builds only `.md` candidates: `/foo.html` and `/pic.png` 404 even when file exists.

## Scope

In:
- `GET /<path>` for any existing, non-excluded content-root file (incl. `.html`): raw `FileResponse`, content-type from extension. `.html` served as full authored document.
- `mdwiki validate`: links to `.html`/static files count as resolving; `.html` pages' own `<a href>`s and `#fragment`s checked like `.md` pages.
- README "Routing" + "Cross-links" sections, `link_rewrite.py` docstring (says "no static passthrough").
- Tests.

Out:
- Extension-less `/foo` serving `foo.html` (user chose `/foo.html` only).
- Wrapping `.html` in `page.html` shell; markdown processing, widget macros/hooks, mermaid on `.html` — served byte-for-byte.
- `.html` pages in `_order.yml` / `next-button` sequencing (`ordering.py` stays `.md`-only).
- Raw serving of `.md` source (`/foo.md` stays 404, Page Routing UC7 unchanged), dotfiles, `_order.yml`.
- Reserved `/_assets`, `/_widgets` prefix shadowing (Page Routing fragility point, unchanged).

## Domains

- [Python Server](../domains/Python-Server.md) — routing, rendering, validation all change here.
- [Browser Client](../domains/Browser-Client.md) — no code change; `.html` pages bypass `page.html` entirely.

## Features

- [Page Routing](../features/Page-Routing.md) — new fallback after `.md` candidates: content-root file resolution.
- [Page Shell & Asset Serving](../features/Page-Shell-and-Asset-Serving.md) — `_page` route falls back to raw `FileResponse` when no `.md` page resolves.
- [Site Validation](../features/Site-Validation.md) — link resolution accepts files; sweep includes `.html` pages.
- [Internal Link Rewriting](../features/Internal-Link-Rewriting.md) — no code change; its non-`.md` passthrough now lands on a served URL (closes its UC4 dead-link outcome for existing files).

## Use Cases

- Page Routing **UC8: Non-md File Path -> 404 Not Found** — changes: for an existing file, now served (below); 404 only when file missing or excluded.
- Page Routing **UC10: Content File Path -> Raw File Served (new)** — `GET /foo.html` or `/img/a.png`, file exists, no `.md` match: bytes as authored, content-type guessed (`text/html` for `.html`).
- Page Routing **UC11: Excluded File Path -> 404 Not Found (new)** — `.md`, dotfile/dot-dir, `_order.yml`: still plain 404.
- Internal Link Rewriting **UC4: Non-Markdown Href -> Unchanged -> Dead Link** — href still unchanged; resolves when target file exists.
- Site Validation **UC4: Internal Link -> Dangling Path or Missing Anchor Issue** — `.html`/static targets resolve; `#frag` on `.html` target checked against `id=`s in its raw source.
- Site Validation **UC6: HTML Page Link -> Dangling Path or Missing Anchor Issue (new)** — links inside `.html` pages checked.

## Code Elements

| Code Element | File | Change needed |
|---|---|---|
| `WikiRenderer.resolve_url` | mdwiki/render.py | Unchanged (still `.md` only, raises `PageNotFound`). |
| `WikiRenderer.resolve_file` (new) | mdwiki/render.py | URL path -> content-root relpath of existing non-excluded file via `_safe_join`; `PageNotFound` otherwise. |
| `WikiRenderer.page_exists` | mdwiki/render.py | Unchanged; validate uses new `resolve_file` alongside. |
| `relpath_to_url` | mdwiki/render.py | Non-`.md` relpath -> `/` + relpath (extension kept). |
| `_page` | mdwiki/server.py | Try `.md` page; on `PageNotFound` try `resolve_file` -> `FileResponse`. Miss -> existing 404 handler. |
| `_check_links`, `_all_md_files` | mdwiki/validate.py | Sweep `.md` + `.html`; target resolves if `page_exists` or `resolve_file` hits; `.html` hrefs/ids read from raw file text. Raw static targets: existence only, no anchor check. |
| module docstring | mdwiki/link_rewrite.py | Drop "no static passthrough" claim. |
| "Routing", "Cross-links" sections | README.md | Document HTML + static serving, exclusions, precedence. |
| tests | tests/test_static_files.py (new) | UC10-UC11, precedence, traversal, validate cases. |

## Solution Design

1. **Resolution order** in `server._page` (catch-all, after `/_assets`, `/_widgets`):
   1. Existing `.md` resolution (`<path>.md`, `<path>/index.md`) — unchanged, so no current URL changes meaning. `foo.html.md` (odd but legal) still wins at `/foo.html`.
   2. `resolve_file(url_path)`: `_safe_join(url_path)` (same traversal guard), must be `is_file()`.
   3. Neither -> `PageNotFound` -> existing plain `Not found` 404 (traversal and missing still indistinguishable).
2. **Exclusions** in `resolve_file` -> `PageNotFound`: suffix `.md`; any path segment starting `.` (covers `.wiki-manifest.json`, `.git/`); basename `_order.yml`. Hardcoded, not config; README lists it.
3. **Raw files, `.html` included**: `FileResponse(path)` — Starlette guesses content-type via `mimetypes` (`text/html` for `.html`). Served byte-for-byte: no shell, no markdown, no widgets, no mermaid, no link rewriting. Author owns whole document. No cache headers (matches `/_assets`).
4. **Validate**: sweep `*.md` + `*.html`/`*.htm` (dot-paths excluded). `.md` pages rendered as today; `.html` pages scanned as raw text with existing `_HREF_RE`/`_ID_RE`. Page URL from `relpath_to_url` (non-`.md` -> `/` + relpath, extension kept). Link target OK if `page_exists` or `resolve_file` hits; `#frag` checked only when target is `.md` or `.html` page.

Contracts respected:
- Page Shell & Asset Serving Shared Contract (Jinja keys) untouched — raw files never reach `page.html`.
- Internal Link Rewriting -> Page Routing `data-model sharing` (extension-less URL shape): untouched; `.html`/asset links pass through unchanged and now resolve at literal path.

Fragility points closed:
- Page Routing: "Only `.md` candidates built ... No passthrough for other files" — closed.
- Internal Link Rewriting: "Non-`.md` targets pass through ... route 404s" — closed for existing files.
- Not closed: reserved-prefix shadowing, direct `.md` URL 404 (kept deliberately).
