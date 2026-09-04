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
from .ordering import ORDER_FILENAME, read_order_file
from .render import WIDGET_MACRO_RE, WikiRenderer, relpath_to_url
from .widgets import resolve_widget

_HREF_RE = re.compile(r'<a\b[^>]*\bhref="([^"]*)"')
_ID_RE = re.compile(r'\bid="([^"]*)"')
_EXTERNAL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")


def _all_md_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.md") if p.is_file())


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
        on_disk = {
            p.name for p in dir_path.iterdir() if p.is_dir() or (p.is_file() and p.suffix == ".md")
        }
        rel_dir = dir_path.relative_to(root)
        for name in listed:
            if name not in on_disk:
                issues.append(f"{rel_dir / ORDER_FILENAME}: entry {name!r} does not exist on disk")
        # index.md is never expected in the manifest - it's the directory's
        # own leaf entry, folded in by whichever level lists this directory,
        # not a page this directory's own manifest sequences (see ordering.walk).
        for name in sorted(on_disk - set(listed) - {"index.md"}):
            issues.append(
                f"{rel_dir / ORDER_FILENAME}: {name!r} is present but unlisted "
                "(will append alphabetically until positioned)"
            )

    # --- widget references ---------------------------------------------------
    for md_path in _all_md_files(root):
        text = md_path.read_text(encoding="utf-8")
        for m in WIDGET_MACRO_RE.finditer(text):
            name = m.group(1)
            if resolve_widget(name, widgets_dir) is None:
                rel = md_path.relative_to(root)
                issues.append(f"{rel}: {{{{ widget: {name} }}}} does not resolve under ./widgets/")

    for hook in config.widget_hooks:
        if resolve_widget(hook.name, widgets_dir) is None:
            issues.append(f"mdwiki.yml: hook widget {hook.name!r} does not resolve under ./widgets/")

    issues.extend(_check_links(root, config, widgets_dir))

    return issues


def _check_links(root: Path, config: SiteConfig, widgets_dir: Path | None) -> list[str]:
    """Renders every page (so link hrefs are already in their final,
    post-InternalLinkExtension form - exactly what a browser would request)
    and confirms every internal `<a href>` resolves, and every `#fragment`
    lands on a real `id=` in its target page. Mirrors what
    `mkdocs build --strict` caught for dangling cross-links/anchors; unlike
    that static build, this walks the same renderer the live server uses,
    so it can't drift from actual runtime behavior."""
    renderer = WikiRenderer(root, config, widgets_dir)
    issues: list[str] = []
    ids_cache: dict[str, set[str] | None] = {}  # relpath -> ids, or None if page 404s

    def _ids_for(relpath: str) -> set[str] | None:
        if relpath not in ids_cache:
            try:
                html = renderer.render_relpath(relpath).content_html
            except Exception:
                ids_cache[relpath] = None
            else:
                ids_cache[relpath] = set(_ID_RE.findall(html))
        return ids_cache[relpath]

    for md_path in _all_md_files(root):
        relpath = str(md_path.relative_to(root)).replace("\\", "/")
        rel = Path(relpath)
        current_url = relpath_to_url(relpath)
        try:
            html = renderer.render_relpath(relpath).content_html
        except Exception as exc:
            issues.append(f"{rel}: failed to render ({exc})")
            continue
        ids_cache[relpath] = set(_ID_RE.findall(html))

        for href in _HREF_RE.findall(html):
            if not href or _EXTERNAL_SCHEME_RE.match(href):
                continue
            resolved = urljoin(current_url, href)
            parsed = urlsplit(resolved)
            target_url = parsed.path or current_url
            fragment = parsed.fragment or None

            if not renderer.page_exists(target_url):
                issues.append(f"{rel}: link to {href!r} does not resolve (resolved path {target_url!r})")
                continue

            if fragment:
                target_relpath = renderer.resolve_url(target_url)
                target_ids = _ids_for(target_relpath)
                if target_ids is not None and fragment not in target_ids:
                    issues.append(
                        f"{rel}: link to {href!r} points at anchor #{fragment} "
                        f"which doesn't exist on {target_relpath}"
                    )

    return issues
