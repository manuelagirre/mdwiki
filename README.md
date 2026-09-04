# mdwiki

Point it at a directory of markdown files and a port, get a served wiki.
No database, no business-logic coupling. Install as a CLI or as a Python
module.

```bash
pip install -e .          # from this directory, until it's published
mdwiki serve --dir ./example --config ./example/mdwiki.yml --port 8000
```

Then open `http://localhost:8000/`. The `./example` directory in this repo
is a small worked example - browse its files alongside this guide.

Programmatic usage, instead of the CLI:

```python
from mdwiki import serve
serve(dir="./wiki", port=8000, config="./mdwiki.yml")
```

This launches its own ASGI process on its own port - there is no
in-process/ASGI-mount API. Run it as its own process alongside whatever
host app you're integrating it with.

## Routing

Any `.md` file under the content root is served 1:1 by its relative path:
`lessons/loops.md` → `/lessons/loops`. A directory's own `dir/index.md`
folds to `/dir/`. There is no fixed URL scheme to configure - whatever
files exist define the URLs that exist.

Path-traversal attempts and missing pages both 404 identically (never a
400 that would hint which case it was).

### Cross-links between pages

Write plain relative markdown links to sibling `.md` files - the same
convention GitHub renders correctly when browsing the raw files:

```markdown
See [the loops lesson](../lessons/loops.md#exercises) for more.
```

At render time, mdwiki rewrites `.md`/`.../index.md` link targets to the
extension-less URLs it actually serves (`../lessons/loops#exercises` above)
- so the same source is correct both on GitHub and through `mdwiki serve`.
Only `<a href>` targets are rewritten; external URLs (any `scheme://`),
`mailto:`/`tel:` links, and pure `#fragment` links pass through untouched.
Image `src` and other non-`.md` targets are never touched either - mdwiki
has no static passthrough for the content root, so a relative link to
something other than a `.md` file isn't served by mdwiki regardless.

## Site config (`mdwiki.yml`)

```yaml
title: My Wiki
index: Project-Overview.md   # optional - serve this file at `/` instead of requiring index.md
nav:
  - label: Home
    href: /
  - label: Lessons
    href: /lessons/
theme: ./my-theme        # optional - a directory with its own page.html/app.css
backend_base: "http://localhost:8001"   # optional, see "Backend calls" below
widgets:                  # optional - auto-injected ("hook") widgets
  - name: next-button
    anchor: bottom        # top | bottom | both
    selector: "lessons/*"
```

`nav`/`title`/`theme`/`backend_base`/`index` are all optional; an absent
`mdwiki.yml` just gets you the default theme with no nav links, and `/`
requires a literal `index.md` at the content root.

**`index`** lets a content root without an `index.md` still serve something
at `/` - useful when the homepage has a more descriptive name (e.g. a
generated `Project-Overview.md`). Tried before the plain `index.md` fallback;
if the named file is missing, resolution falls back to `index.md` exactly as
if `index` had never been set.

**A note on `top`/`bottom`/`both`:** these are anchors *inside the content
region* - immediately before/after the rendered markdown, not the page shell
as a whole. There's no anchor (yet) for a persistent header/nav-bar region
outside the content area; nothing in this package's own reference case
needed one. If you need that, it's a genuinely new anchor to add, not a
variant of `top`.

**`selector`** is a glob matched against the page's resolved relative path
(e.g. `lessons/lesson-1.md`, `lessons/lesson-1/index.md`). `*` matches
within one path segment only (it does not cross `/`) - same semantics as
`pathlib.PurePath.match()`. So `lessons/*` matches `lessons/lesson-1.md`
but not `lessons/lesson-1/exercises/ex-1.md`.

## Frontmatter

Optional YAML frontmatter at the top of any `.md` file:

```yaml
---
title: Lesson 3 - Loops
back_link:
  href: ../lesson-2
  label: Back to Lesson 2
widgets:
  exclude: [next-button]   # opt this page out of a matching hook widget
---
```

- `title` (optional): overrides the page's `<title>`/heading. Default falls
  back to the file's own `# H1`, then the filename, humanized.
- `back_link` (optional `href` + `label`): rendered as a plain `<a>` in the
  page shell. This is core-rendered, not a widget - static markup from data
  you supplied, no JS/data-fetch involved.
- `widgets.exclude` (optional list of names): skips specific hook-injected
  widgets on this page, even though their `selector` would otherwise match.

## Page ordering (`_order.yml`)

Drives "what page comes next" for the standard `next-button` widget (and
anything else that needs sequencing). One `_order.yml` per directory,
optional - sibling to the `.md` files it orders:

```yaml
# lessons/_order.yml
- intro.md
- variables.md
- loops.md
- exercises
- wrap-up.md
```

- No `_order.yml` in a directory → plain alphabetical order. The common
  case (filenames that already sort correctly) needs zero setup.
- Files/dirs on disk but missing from the manifest are appended after the
  explicit entries, alphabetically among themselves - never excluded from
  the sequence.
- A directory with its own `index.md` is visited as a leaf when the walk
  enters it (folds to `dir/`, matching the routing rule above); the walk
  then continues into the rest of that directory's own children, so nested
  pages (e.g. an `exercises/` subfolder) stay reachable. `index.md` itself
  is never listed in its own directory's `_order.yml`.
- The whole tree is walked as **one global depth-first order**. `next()`/
  `prev()` = the adjacent entry in that global order, filtered down to
  whichever `selector` the requesting widget/hook cares about. This is what
  lets, say, a `next-lesson` hook (`selector: lessons/*/index.md`) skip
  straight from one lesson to the next while a separate `next-exercise`
  hook (`selector: lessons/*/exercises/*`) sequences exercises across
  lesson boundaries - same global walk, two different filters.
- A stale manifest entry (references something no longer on disk) is
  skipped at resolve time, not a hard failure.

Edit `_order.yml` without hand-touching the YAML:

```bash
mdwiki order insert-after  lessons lesson-2.md lesson-2b.md
mdwiki order insert-before lessons wrap-up.md   new-exercise.md
mdwiki order append        lessons wrap-up.md
mdwiki order remove        lessons wrap-up.md
```

### `mdwiki validate`

A pre-flight check, separate from the graceful runtime fallbacks above
(stale entries are skipped, unresolved widgets substitute `toast` - a bad
reference never breaks a live page). Run it before publishing:

```bash
mdwiki validate --dir ./wiki --config ./mdwiki.yml
```

Reports, in one sweep: every `_order.yml` entry that doesn't resolve on
disk; every file/dir present but unlisted in its directory's manifest (a
heads-up, not an error - it'll append alphabetically until positioned);
every `{{ widget: name }}` macro and hook `name` that doesn't resolve under
`./widgets/` or the standard set; every internal `<a href>` (post-rewrite,
see "Cross-links between pages") that doesn't resolve to a real page; every
`#fragment` link whose target page has no matching `id=`. The link/anchor
checks render every page through the same `WikiRenderer` the live server
uses, so they can't drift from what actually 404s at runtime.

## Writing a widget

A widget is a directory, `./widgets/<name>/`, containing `widget.js` and
`widget.css`. No manifest file - the directory name is the widget's name.

Two ways a widget ends up on a page:

- **Content-authored (macro):** the page author writes
  `{{ widget: my-widget param="value" }}` inline in the markdown, anywhere
  in the prose.
- **Auto-injected (hook):** a row in `mdwiki.yml`'s `widgets:` list, matched
  against every page whose resolved path matches `selector`. The page
  author does nothing; a page can still opt out via frontmatter
  (`widgets: exclude: [...]`).

Either way, params become plain HTML attributes on a Shadow-DOM host
element; your widget's JS reads them with `getAttribute()`:

```js
// widgets/my-widget/widget.js
import {mountWidget} from '/_assets/shadow-helper.js';

document.querySelectorAll('[data-widget="my-widget"]').forEach((host) => {
  mountWidget(host, (container) => {
    const value = host.getAttribute('param') || '';
    container.innerHTML = `<p>hi, param = ${value}</p>`;
  });
});
```

`mountWidget` (shipped with core, at `/_assets/shadow-helper.js`) attaches
a Shadow DOM to the host, loads your widget's own `widget.css` into that
shadow root, and hands you an empty container to render into - real
CSS/DOM isolation, no global class-name collisions with the page's theme
or other widgets.

Your JS is always loaded as `<script type="module">`. A given module URL
is fetched and evaluated exactly once per page per the HTML spec, no
matter how many times it's referenced - so multiple occurrences of the
same widget on one page are safe by construction; you never need to guard
your own init code against double-firing.

Point `mdwiki serve` at your widgets directory with `--widgets <path>` (or
`widgets_dir:` in `mdwiki.yml`). An unresolved widget name never fails the
page - it substitutes the built-in `toast` widget, styled as an error, in
its place.

## Standard widgets

Two widgets ship with mdwiki itself - nothing to author or install, usable
immediately by name via either mechanism above:

- **`toast`** - a colored panel with bold title + text. Params: `title`
  (optional), `text`, `style` (`info` | `warning` | `error`, default
  `info`). Also the built-in not-found fallback (rendered with
  `style="error"`).
- **`next-button`** - a "next page" link. Its `href`/`label` are normally
  computed by core from `_order.yml` when used as a hook; usable directly
  too (`{{ widget: next-button href="/lessons/loops" label="Next Lesson" }}`).

A host can shadow either by providing its own `./widgets/toast/` or
`./widgets/next-button/` - your own copy is checked before the standard one.

## Backend calls

If your widgets need to call back to a host app's API (not just the wiki
server itself), set `backend_base` in `mdwiki.yml`. Core exposes it to
every page as `window.MDWIKI_BACKEND_BASE`:

```js
const base = window.MDWIKI_BACKEND_BASE || '';
const res = await fetch(`${base}/api/whatever`);
```

Convention: an absolute `http(s)://` URL means "call the backend"; a
relative URL means "call the wiki server itself."

**CORS.** Since the wiki and your backend are separate processes/ports,
a widget's `fetch()` to `backend_base` needs the backend to send CORS
headers for the wiki's origin, or the browser blocks it regardless of how
correct the URL is. With FastAPI:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000"],  # the wiki's origin
    allow_methods=["*"],
    allow_headers=["*"],
)
```

If you skip this, widget fetches will fail silently in the browser console
with an opaque CORS error, not an obviously-wiki-related one - worth
checking first if a widget "does nothing" after wiring it up.

## Worked example

See `./example/` in this repo: a tiny site with a homepage using the
`toast` macro, a `lessons/` section with three pages sequenced by
`_order.yml`, and a `next-button` hook auto-injected at the bottom of every
lesson page except the last. Run it with the quickstart command at the top
of this guide.
