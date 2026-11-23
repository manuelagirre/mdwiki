"""`mdwiki validate` - a pre-flight check an author runs before publishing.
Separate from the graceful runtime degradation in render.py/widgets.py
(stale _order.yml entries skipped, unresolved widgets fall back to `toast`) -
this reports every such issue in one sweep instead of hiding it behind a
per-page fallback.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from .config import SiteConfig
from .ordering import ORDER_FILENAME, orderable_names, read_order_file
from .render import PageNotFound, RenderedPage, WikiRenderer, frontmatter_problems, relpath_to_url
from .widgets import resolve_widget

_HREF_RE = re.compile(r'<a\b[^>]*\bhref="([^"]*)"')
_ID_RE = re.compile(r'\bid="([^"]*)"')
_EXTERNAL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")


_HTML_SUFFIXES = (".html", ".htm")


def _all_md_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.md") if p.is_file())


def _is_html(relpath: str) -> bool:
    return relpath.lower().endswith(_HTML_SUFFIXES)


def _all_page_files(root: Path) -> list[Path]:
    """Every page whose links get checked: `.md` pages plus author-written
    `.html` pages served raw (skipping dot-paths, which are never served)."""
    html = [
        p
        for p in root.rglob("*")
        if p.is_file()
        and _is_html(p.name)
        and not any(part.startswith(".") for part in p.relative_to(root).parts)
    ]
    return sorted(_all_md_files(root) + html)


class _CachingRenderer(WikiRenderer):
    """validate() inspects each page more than once (macros, links,
    back_link, anchors of link targets); render each one only once."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._rendered: dict[str, RenderedPage] = {}

    def render_relpath(self, relpath: str) -> RenderedPage:
        if relpath not in self._rendered:
            self._rendered[relpath] = super().render_relpath(relpath)
        return self._rendered[relpath]


def validate(root: Path, config: SiteConfig, widgets_dir: Path | None) -> list[str]:
    """Returns a list of human-readable issue strings; empty means clean."""
    root = root.resolve()
    issues: list[str] = []

    # --- _order.yml entries -------------------------------------------------
    for dir_path in [root] + [p for p in root.rglob("*") if p.is_dir()]:
        order_path = dir_path / ORDER_FILENAME
        if not order_path.is_file():
            continue
        listed = read_order_file(dir_path)
        on_disk = orderable_names(dir_path)
        rel_dir = dir_path.relative_to(root)
        for name in listed:
            if name in on_disk:
                continue
            if (dir_path / name).exists():
                issues.append(f"{rel_dir / ORDER_FILENAME}: entry {name!r} is not a page or a directory of pages")
            else:
                issues.append(f"{rel_dir / ORDER_FILENAME}: entry {name!r} does not exist on disk")
        # index.md is never expected in the manifest - it's the directory's
        # own leaf entry, folded in by whichever level lists this directory,
        # not a page this directory's own manifest sequences (see ordering.walk).
        for name in sorted(on_disk - set(listed) - {"index.md"}):
            issues.append(
                f"{rel_dir / ORDER_FILENAME}: {name!r} is present but unlisted "
                "(will append alphabetically until positioned)"
            )

    # --- frontmatter + widget references --------------------------------------
    renderer = _CachingRenderer(root, config, widgets_dir)
    for md_path in _all_md_files(root):
        rel = md_path.relative_to(root)
        for problem in frontmatter_problems(md_path.read_text(encoding="utf-8-sig")):
            issues.append(f"{rel}: {problem}")
        # Only macros the renderer actually expands - a `{{ widget: x }}`
        # shown inside code is an example of the syntax, not a reference.
        try:
            live = renderer.render_relpath(rel.as_posix()).macro_widgets
        except Exception:
            continue  # reported as "failed to render" by _check_links below
        for name in live:
            if resolve_widget(name, widgets_dir) is None:
                issues.append(f"{rel}: {{{{ widget: {name} }}}} does not resolve under ./widgets/")

    for hook in config.widget_hooks:
        if resolve_widget(hook.name, widgets_dir) is None:
            issues.append(f"mdwiki.yml: hook widget {hook.name!r} does not resolve under ./widgets/")

    issues.extend(_check_links(root, renderer))

    return issues


def _check_links(root: Path, renderer: WikiRenderer) -> list[str]:
    """Renders every page (so link hrefs are already in their final,
    post-InternalLinkExtension form - exactly what a browser would request)
    and confirms every internal `<a href>` resolves, and every `#fragment`
    lands on a real `id=` in its target page. Mirrors what
    `mkdocs build --strict` caught for dangling cross-links/anchors; unlike
    that static build, this walks the same renderer the live server uses,
    so it can't drift from actual runtime behavior."""
    config = renderer.config
    issues: list[str] = []
    ids_cache: dict[str, set[str] | None] = {}  # relpath -> ids, or None if page 404s

    def _page_html(relpath: str) -> str:
        """Final HTML a browser receives: `.md` pages rendered, author-written
        `.html` pages read as-is (they're served raw, never rendered)."""
        if _is_html(relpath):
            return renderer.file_path(relpath).read_text(encoding="utf-8")
        return renderer.render_relpath(relpath).content_html

    def _ids_for(relpath: str) -> set[str] | None:
        if relpath not in ids_cache:
            try:
                html = _page_html(relpath)
            except Exception:
                ids_cache[relpath] = None
            else:
                ids_cache[relpath] = set(_ID_RE.findall(html))
        return ids_cache[relpath]

    def _resolve_target(url: str) -> tuple[str | None, bool]:
        """(relpath whose ids an `#anchor` is checked against, or None for a
        raw non-HTML file; whether the URL resolves at all)."""
        if renderer.page_exists(url):
            return renderer.resolve_url(url), True
        try:
            relpath = renderer.resolve_file(url)
        except PageNotFound:
            return None, False
        return (relpath if _is_html(relpath) else None), True

    def _check_href(where: str, base_url: str, href: str) -> None:
        """One link, as the browser would follow it from `base_url`."""
        if not href or _EXTERNAL_SCHEME_RE.match(href):
            return
        resolved = urljoin(base_url, href)
        parsed = urlsplit(resolved)
        target_url = parsed.path or base_url
        fragment = parsed.fragment or None

        target_relpath, resolves = _resolve_target(target_url)
        if not resolves:
            issues.append(f"{where}: link to {href!r} does not resolve (resolved path {target_url!r})")
            return

        if fragment and target_relpath is not None:
            target_ids = _ids_for(target_relpath)
            if target_ids is not None and fragment not in target_ids:
                issues.append(
                    f"{where}: link to {href!r} points at anchor #{fragment} "
                    f"which doesn't exist on {target_relpath}"
                )

    # --- site config: nav links and the `index:` override ---------------------
    for link in config.nav:
        _check_href("mdwiki.yml nav", "/", link.href)
    if config.index_page and not renderer.file_path(config.index_page).is_file():
        issues.append(
            f"mdwiki.yml: index {config.index_page!r} does not exist (falling back to index.md at /)"
        )

    for page_path in _all_page_files(root):
        relpath = str(page_path.relative_to(root)).replace("\\", "/")
        rel = Path(relpath)
        current_url = relpath_to_url(relpath)
        try:
            html = _page_html(relpath)
            back_link = None if _is_html(relpath) else renderer.render_relpath(relpath).back_link
        except Exception as exc:
            issues.append(f"{rel}: failed to render ({exc})")
            continue
        ids_cache[relpath] = set(_ID_RE.findall(html))

        for href in _HREF_RE.findall(html):
            _check_href(str(rel), current_url, href)
        if back_link and back_link.get("href"):
            _check_href(f"{rel} (back_link)", current_url, str(back_link["href"]))

    return issues
