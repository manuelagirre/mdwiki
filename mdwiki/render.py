"""Core rendering: URL path -> resolved `.md` file (generic path-mirroring,
`dir/index.md` folds to `/dir/`) -> HTML, with frontmatter overrides and
widget injection (macro + hook mechanisms) spliced in. No DB, no
business-logic coupling - the only inputs are a content root directory, a
site config, and an optional widgets directory.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from urllib.parse import quote

import markdown
import yaml

from .config import SiteConfig
from .link_rewrite import InternalLinkExtension
from .mermaid import MermaidExtension
from .ordering import Page, adjacent, has_pages, ordered_entries, selector_matches, walk
from .paths import is_hidden
from .widgets import widget_markup

# `extra` bundles attr_list/def_list/fenced_code/footnotes/md_in_html/tables -
# md_in_html is what widget host markup (raw <div> blocks) depends on.
# InternalLinkExtension rewrites `.md`-suffixed relative links (the
# GitHub-native convention wiki authors write) to the extension-less URLs
# mdwiki actually serves - see link_rewrite.py. MermaidExtension must run
# before "codehilite" claims ```mermaid fences as syntax-highlighted code -
# see mermaid.py.
MD_EXTENSIONS = [
    "extra",
    "admonition",
    "sane_lists",
    "codehilite",
    "toc",
    InternalLinkExtension(),
    MermaidExtension(),
]
MD_EXTENSION_CONFIGS = {
    "codehilite": {"guess_lang": False},
    # A "#" link after each heading (shown on hover, see app.css) so readers
    # can copy a link straight to a section.
    "toc": {"permalink": "#", "permalink_title": "Link to this section"},
}

# Opening `---` line, then everything up to the first closing `---` line.
# The body may be empty (`---\n---`) and the closing fence may end the file.
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)^---[ \t]*(?:\n|\Z)", re.DOTALL | re.MULTILINE)
WIDGET_MACRO_RE = re.compile(r'\{\{\s*widget:\s*([A-Za-z0-9_-]+)((?:\s+[A-Za-z0-9_-]+="[^"]*")*)\s*\}\}')
_WIDGET_MACRO_RE = WIDGET_MACRO_RE  # internal alias, kept for brevity below
_ATTR_RE = re.compile(r'([A-Za-z0-9_-]+)="([^"]*)"')

# Python-Markdown uses \x02/\x03 (STX/ETX) internally for its own HTML
# stashing and strips them from the final output - a placeholder built from
# those would silently vanish. Plain alnum text survives untouched instead.
_PLACEHOLDER = "MDWIKIWIDGETPLACEHOLDER{idx}ENDMDWIKIWIDGETPLACEHOLDER"
_PLACEHOLDER_RE = re.compile(r"MDWIKIWIDGETPLACEHOLDER(\d+)ENDMDWIKIWIDGETPLACEHOLDER")


class PageNotFound(Exception):
    """Raised both for missing files and for any path-traversal attempt - the
    caller always turns this into a plain 404, never a 400 that would hint
    which case it was."""


def _load_frontmatter(text: str) -> tuple[dict, str, list[str]]:
    """(usable frontmatter, body, problems). Never raises: a typo in page
    metadata shouldn't take the whole page down with a 500. Malformed YAML
    or a field of the wrong shape is dropped (the body still renders) and
    described in `problems`, which `mdwiki validate` reports."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text, []
    body = text[m.end():]
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError as exc:
        detail = str(exc).splitlines()[0]
        return {}, body, [f"frontmatter is not valid YAML ({detail}); ignored"]
    if data is None:
        return {}, body, []
    if not isinstance(data, dict):
        return {}, body, [f"frontmatter must be a mapping, got {type(data).__name__}; ignored"]

    problems: list[str] = []
    widgets = data.get("widgets")
    if widgets is not None:
        exclude = widgets.get("exclude") if isinstance(widgets, dict) else None
        if not isinstance(widgets, dict) or not isinstance(exclude, (list, type(None))):
            problems.append("frontmatter `widgets` must look like `widgets: {exclude: [name, ...]}`; ignored")
            del data["widgets"]
    back_link = data.get("back_link")
    if back_link and not isinstance(back_link, dict):
        problems.append("frontmatter `back_link` must be a mapping with `href` (and optional `label`); ignored")
        del data["back_link"]
    return data, body, problems


def frontmatter_problems(text: str) -> list[str]:
    return _load_frontmatter(text)[2]


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    data, body, _ = _load_frontmatter(text)
    return data, body


def _first_h1(toc_tokens: list[dict]) -> str | None:
    """Plain text of the document's first `<h1>`, from the `toc`
    extension's tokens - i.e. what the markdown parser actually treated as
    a heading, so `# comment` lines inside code blocks don't count, setext
    `Title\n=====` headings do, and inline markup (`code`, **bold**,
    links) is reduced to its text."""
    for token in toc_tokens:
        if token["level"] == 1:
            return html.unescape(token["name"]).strip() or None
        found = _first_h1(token["children"])
        if found:
            return found
    return None


def _page_title(frontmatter: dict, body: str, relpath: str, toc_tokens: list[dict] | None = None) -> str:
    """frontmatter `title`, else the first H1, else the humanized filename.
    Pass `toc_tokens` from a conversion you already ran to avoid parsing
    the body a second time."""
    if "title" in frontmatter:
        return str(frontmatter["title"])
    if toc_tokens is None:
        md = markdown.Markdown(extensions=["extra", "toc"])
        md.convert(body)
        toc_tokens = md.toc_tokens
    h1 = _first_h1(toc_tokens)
    if h1:
        return h1
    stem = Path(relpath).stem if Path(relpath).name != "index.md" else Path(relpath).parent.name
    return _humanize(stem)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _humanize(name: str) -> str:
    return name.replace("-", " ").replace("_", " ").title()


@dataclass(frozen=True)
class _MacroRef:
    name: str
    attrs: dict[str, str]
    source: str  # the macro exactly as written, restored where it's literal


def _extract_macros(body: str) -> tuple[str, list[_MacroRef]]:
    refs: list[_MacroRef] = []

    def _sub(m: re.Match) -> str:
        attrs = dict(_ATTR_RE.findall(m.group(2) or ""))
        refs.append(_MacroRef(name=m.group(1), attrs=attrs, source=m.group(0)))
        return _PLACEHOLDER.format(idx=len(refs) - 1)

    return _WIDGET_MACRO_RE.sub(_sub, body), refs


# Regions of rendered HTML whose text is shown literally: inline/fenced code
# and mermaid diagram source. A macro that lands in one is an *example* of
# the syntax (`{{ widget: x }}` in backticks, a ```markdown block), so it is
# put back as written instead of expanded into a live widget.
_LITERAL_REGION_RE = re.compile(r'<code\b[^>]*>.*?</code>|<pre class="mermaid">.*?</pre>', re.DOTALL)


def _restore_literal_macros(html_text: str, refs: list[_MacroRef]) -> str:
    def _restore(m: re.Match) -> str:
        return _PLACEHOLDER_RE.sub(lambda p: escape(refs[int(p.group(1))].source, quote=False), m.group(0))

    return _LITERAL_REGION_RE.sub(_restore, html_text)


# Never served raw by `WikiRenderer.resolve_file`: markdown source (served
# rendered, via resolve_url), per-directory ordering manifests, and anything
# under a dot-path (e.g. `.wiki-manifest.json`, `.git/`).
_RAW_EXCLUDED_SUFFIXES = (".md",)
_RAW_EXCLUDED_NAMES = ("_order.yml",)


def _raw_excluded(parts) -> bool:
    name = parts[-1].lower()
    return (
        is_hidden(parts)
        or name in _RAW_EXCLUDED_NAMES
        or name.endswith(_RAW_EXCLUDED_SUFFIXES)
    )


def _unsafe_segment(part: str) -> bool:
    """Segments some filesystems reinterpret: backslash separators, drive /
    stream colons (`x::$DATA`), and trailing dots or spaces that Windows
    strips (`secret.md.` opens `secret.md`)."""
    return "\\" in part or ":" in part or part != part.rstrip(". ")


def relpath_to_url(relpath: str) -> str:
    """Content file's path relative to root -> the URL that serves it. `.md`
    pages lose their extension (and `index.md` folds to its directory); any
    other file is served raw at its literal path."""
    if not relpath.endswith(".md"):
        return "/" + relpath
    if relpath == "index.md":
        return "/"
    if relpath.endswith("/index.md"):
        return "/" + relpath[: -len("index.md")]
    return "/" + relpath[: -len(".md")]


@dataclass
class RenderedPage:
    title: str
    content_html: str
    back_link: dict[str, str] | None
    has_mermaid: bool = False
    macro_widgets: list[str] = field(default_factory=list)
    """Names of the `{{ widget: ... }}` macros actually expanded on this page
    (not ones shown literally inside code), in order of appearance."""


class WikiRenderer:
    def __init__(self, root: Path, config: SiteConfig, widgets_dir: Path | None):
        self.root = root.resolve()
        self.config = config
        self.widgets_dir = widgets_dir
        # relpath -> (mtime_ns, size, title). Working out a title means a
        # full markdown parse, and listings, next-button labels and search
        # need the titles of many pages per request; the cache is keyed on
        # the file's stat so an edit on disk is picked up immediately.
        self._titles: dict[str, tuple[int, int, str]] = {}

    def _safe_join(self, relpath: str) -> Path:
        # A NUL byte makes the OS path calls below raise ValueError (a 500)
        # instead of simply missing - treat it as the 404 it should be.
        if "\x00" in relpath:
            raise PageNotFound(f"embedded NUL: {relpath!r}")
        candidate = self.root.joinpath(*relpath.split("/")).resolve()
        if not candidate.is_relative_to(self.root):
            raise PageNotFound(f"escapes root: {relpath!r}")
        return candidate

    def resolve_url(self, url_path: str) -> str:
        """URL path (no leading slash; '' for root) -> the `.md` file
        relpath serving it. Tries `<path>.md` first, then `<path>/index.md`
        (dir folding); 404s if neither exists. At root, tries
        `config.index_page` (if set) before falling back to plain
        `index.md` - see SiteConfig.index_page."""
        url_path = url_path.strip("/")
        if is_hidden(url_path):
            # Dot-paths (`.github/`, `.private.md`) are never part of the
            # site - not served raw, listed, ordered or searched, and not
            # rendered either.
            raise PageNotFound(url_path)
        if url_path:
            candidates = [f"{url_path}.md", f"{url_path}/index.md"]
        else:
            candidates = [self.config.index_page] if self.config.index_page else []
            candidates.append("index.md")
        for relpath in candidates:
            path = self._safe_join(relpath)
            if path.is_file():
                return relpath
        raise PageNotFound(url_path)

    def resolve_file(self, url_path: str) -> str:
        """URL path -> relpath of a content-root file served raw, as authored
        (author-written `.html` pages, images, css, ...). Only consulted after
        `resolve_url` misses, so a `.md` page always wins its URL. Excluded
        files and anything escaping root raise `PageNotFound`, same 404 as a
        missing page."""
        relpath = url_path.strip("/")
        if not relpath or any(_unsafe_segment(part) for part in relpath.split("/")):
            raise PageNotFound(url_path)
        path = self._safe_join(relpath)
        if not path.is_file():
            raise PageNotFound(url_path)
        # Check exclusions against both the requested path and the file it
        # actually resolves to, so a symlink (`notes.txt -> secret.md`) can't
        # expose an excluded file under an innocent-looking name.
        if _raw_excluded(relpath.split("/")) or _raw_excluded(path.relative_to(self.root).parts):
            raise PageNotFound(url_path)
        # The site's own mdwiki.yml is configuration, not content, even when
        # it sits inside the content root.
        if self.config.source is not None and path == self.config.source:
            raise PageNotFound(url_path)
        return relpath

    def file_path(self, relpath: str) -> Path:
        return self._safe_join(relpath)

    def page_exists(self, url_path: str) -> bool:
        try:
            self.resolve_url(url_path)
            return True
        except PageNotFound:
            return False

    def listing_dir(self, url_path: str) -> str | None:
        """The directory relpath ('' for the root) to show a generated
        listing for at `url_path`, or None. Only consulted once no page
        (`<path>.md`, `<path>/index.md`, the `index:` override) matched, so
        an authored index always wins. The root always gets one (even an
        empty wiki shouldn't greet you with a 404); other directories only
        when they hold pages - an `images/` folder still 404s."""
        rel = url_path.strip("/")
        if not rel:
            return ""
        if is_hidden(rel) or any(_unsafe_segment(part) for part in rel.split("/")):
            return None
        path = self._safe_join(rel)
        if path.is_dir() and has_pages(path):
            return rel
        return None

    def render_listing(self, dir_relpath: str) -> RenderedPage:
        """A generated index for a directory without its own `index.md`:
        its pages and page-holding subdirectories, in `_order.yml` order,
        each linked by title. Links are relative to the listing's
        canonical URL (`/dir/`)."""
        dir_path = self._safe_join(dir_relpath) if dir_relpath else self.root
        prefix = f"{dir_relpath}/" if dir_relpath else ""
        title = _humanize(Path(dir_relpath).name) if dir_relpath else self.config.title

        items: list[str] = []
        for name in ordered_entries(dir_path):
            child = dir_path / name
            if child.is_dir():
                index = f"{prefix}{name}/index.md"
                label = self._title_for(index) if (child / "index.md").is_file() else _humanize(name)
                href, css = quote(name) + "/", "mdwiki-listing-dir"
            else:
                label = self._title_for(prefix + name)
                href, css = quote(name[: -len(".md")]), "mdwiki-listing-page"
            items.append(f'<li class="{css}"><a href="{escape(href)}">{escape(label, quote=False)}</a></li>')

        body = "\n".join(items) if items else "<li><em>No pages yet.</em></li>"
        content_html = (
            f'<h1 id="{escape(_slug(title))}">{escape(title, quote=False)}</h1>\n'
            f'<ul class="mdwiki-listing">\n{body}\n</ul>'
        )
        return RenderedPage(title=title, content_html=content_html, back_link=None)

    def _read(self, relpath: str) -> tuple[dict, str]:
        path = self._safe_join(relpath)
        if not path.is_file():
            raise PageNotFound(relpath)
        # utf-8-sig: drop a leading BOM (as some Windows editors write) so
        # the frontmatter fence is still at the very start of the text.
        return _parse_frontmatter(path.read_text(encoding="utf-8-sig"))

    def page_source(self, relpath: str) -> tuple[str, str]:
        """(title, markdown body without frontmatter) of a `.md` page."""
        frontmatter, body = self._read(relpath)
        return self._title_for(relpath, frontmatter, body), body

    def _title_for(self, relpath: str, frontmatter: dict | None = None, body: str | None = None) -> str:
        stat = self._safe_join(relpath).stat()
        cached = self._titles.get(relpath)
        if cached and cached[:2] == (stat.st_mtime_ns, stat.st_size):
            return cached[2]
        if body is None:
            frontmatter, body = self._read(relpath)
        title = _page_title(frontmatter or {}, body, relpath)
        self._titles[relpath] = (stat.st_mtime_ns, stat.st_size, title)
        return title

    def _pages_in_order(self) -> list[Page]:
        """The global page order. Walked fresh on every call, so the live
        server always reflects the files on disk; a renderer working on a
        fixed snapshot (validate) can override this to walk once."""
        return walk(self.root)

    def _hook_attrs(self, hook_name: str, selector: str, relpath: str) -> dict[str, str] | None:
        """Params to pass a hook-injected widget. `next-button` needs
        core-computed "what page is next" from the ordering manifest; other
        hook widgets get no extra params beyond what mdwiki.yml declares
        (none, currently - extend here as new hook widgets need params)."""
        if hook_name == "next-button":
            target = adjacent(self.root, relpath, selector, direction=1, pages=self._pages_in_order())
            if target is None:
                return None  # nothing to render - last page in the sequence
            return {"href": relpath_to_url(target.relpath), "label": self._title_for(target.relpath)}
        return {}

    def render_url(self, url_path: str) -> RenderedPage:
        relpath = self.resolve_url(url_path)
        return self.render_relpath(relpath)

    def render_relpath(self, relpath: str) -> RenderedPage:
        frontmatter, body = self._read(relpath)

        excluded = {str(name) for name in (frontmatter.get("widgets") or {}).get("exclude") or []}

        body_with_placeholders, macro_refs = _extract_macros(body)
        # A fresh Markdown() instance per call, not the markdown.markdown()
        # convenience function - MermaidExtension stashes a flag on the
        # instance (has this page got a diagram?) that we need to read back
        # after conversion; markdown.markdown() discards its instance
        # internally, and a shared/reused instance isn't safe across
        # FastAPI's threadpooled sync request handlers.
        md = markdown.Markdown(extensions=MD_EXTENSIONS, extension_configs=MD_EXTENSION_CONFIGS)
        content_html = md.convert(body_with_placeholders)
        has_mermaid = md.mdwiki_has_mermaid
        title = _page_title(frontmatter, body, relpath, md.toc_tokens)

        content_html = _restore_literal_macros(content_html, macro_refs)
        live_widgets: list[str] = []

        def _fill(m: re.Match) -> str:
            ref = macro_refs[int(m.group(1))]
            live_widgets.append(ref.name)
            return widget_markup(ref.name, ref.attrs, self.widgets_dir)

        content_html = _PLACEHOLDER_RE.sub(_fill, content_html)

        top_parts: list[str] = []
        bottom_parts: list[str] = []
        for hook in self.config.widget_hooks:
            if hook.name in excluded:
                continue
            if not selector_matches(relpath, hook.selector):
                continue
            attrs = self._hook_attrs(hook.name, hook.selector, relpath)
            if attrs is None:
                continue
            markup = widget_markup(hook.name, attrs, self.widgets_dir)
            if hook.anchor in ("top", "both"):
                top_parts.append(markup)
            if hook.anchor in ("bottom", "both"):
                bottom_parts.append(markup)

        full_html = "\n".join(top_parts) + content_html + "\n".join(bottom_parts)

        back_link = None
        if "back_link" in frontmatter and frontmatter["back_link"]:
            bl = frontmatter["back_link"]
            back_link = {"href": bl.get("href", ""), "label": bl.get("label", "Back")}

        return RenderedPage(
            title=title,
            content_html=full_html,
            back_link=back_link,
            has_mermaid=has_mermaid,
            macro_widgets=live_widgets,
        )
