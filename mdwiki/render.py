"""Core rendering: URL path -> resolved `.md` file (generic path-mirroring,
`dir/index.md` folds to `/dir/`) -> HTML, with frontmatter overrides and
widget injection (macro + hook mechanisms) spliced in. No DB, no
business-logic coupling - the only inputs are a content root directory, a
site config, and an optional widgets directory.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import markdown
import yaml

from .config import SiteConfig
from .link_rewrite import InternalLinkExtension
from .mermaid import MermaidExtension
from .ordering import adjacent
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
    "toc": {"permalink": False},
}

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?\n)---\n", re.DOTALL)
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
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


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    data = yaml.safe_load(m.group(1)) or {}
    if not isinstance(data, dict):
        data = {}
    return data, text[m.end():]


def _page_title(frontmatter: dict, body: str, relpath: str) -> str:
    if "title" in frontmatter:
        return str(frontmatter["title"])
    h1 = _H1_RE.search(body)
    if h1:
        return h1.group(1).strip()
    stem = Path(relpath).stem if Path(relpath).name != "index.md" else Path(relpath).parent.name
    return stem.replace("-", " ").replace("_", " ").title()


def _extract_macros(body: str) -> tuple[str, list[tuple[str, dict[str, str]]]]:
    refs: list[tuple[str, dict[str, str]]] = []

    def _sub(m: re.Match) -> str:
        name = m.group(1)
        attrs = dict(_ATTR_RE.findall(m.group(2) or ""))
        idx = len(refs)
        refs.append((name, attrs))
        return _PLACEHOLDER.format(idx=idx)

    return _WIDGET_MACRO_RE.sub(_sub, body), refs


def relpath_to_url(relpath: str) -> str:
    """`.md` file's path relative to root -> the URL that serves it."""
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


class WikiRenderer:
    def __init__(self, root: Path, config: SiteConfig, widgets_dir: Path | None):
        self.root = root.resolve()
        self.config = config
        self.widgets_dir = widgets_dir

    def _safe_join(self, relpath: str) -> Path:
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

    def page_exists(self, url_path: str) -> bool:
        try:
            self.resolve_url(url_path)
            return True
        except PageNotFound:
            return False

    def _read(self, relpath: str) -> tuple[dict, str]:
        path = self._safe_join(relpath)
        if not path.is_file():
            raise PageNotFound(relpath)
        return _parse_frontmatter(path.read_text(encoding="utf-8"))

    def _title_for(self, relpath: str) -> str:
        frontmatter, body = self._read(relpath)
        return _page_title(frontmatter, body, relpath)

    def _hook_attrs(self, hook_name: str, selector: str, relpath: str) -> dict[str, str] | None:
        """Params to pass a hook-injected widget. `next-button` needs
        core-computed "what page is next" from the ordering manifest; other
        hook widgets get no extra params beyond what mdwiki.yml declares
        (none, currently - extend here as new hook widgets need params)."""
        if hook_name == "next-button":
            target = adjacent(self.root, relpath, selector, direction=1)
            if target is None:
                return None  # nothing to render - last page in the sequence
            return {"href": relpath_to_url(target.relpath), "label": self._title_for(target.relpath)}
        return {}

    def render_url(self, url_path: str) -> RenderedPage:
        relpath = self.resolve_url(url_path)
        return self.render_relpath(relpath)

    def render_relpath(self, relpath: str) -> RenderedPage:
        frontmatter, body = self._read(relpath)
        title = _page_title(frontmatter, body, relpath)

        excluded = set((frontmatter.get("widgets") or {}).get("exclude", []) or [])

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

        def _fill(m: re.Match) -> str:
            name, attrs = macro_refs[int(m.group(1))]
            return widget_markup(name, attrs, self.widgets_dir)

        content_html = _PLACEHOLDER_RE.sub(_fill, content_html)

        top_parts: list[str] = []
        bottom_parts: list[str] = []
        for hook in self.config.widget_hooks:
            if hook.name in excluded:
                continue
            if not Path(relpath).match(hook.selector):
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

        return RenderedPage(title=title, content_html=full_html, back_link=back_link, has_mermaid=has_mermaid)
