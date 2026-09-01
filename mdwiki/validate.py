"""`mdwiki validate` - a pre-flight check an author runs before publishing.
Separate from the graceful runtime degradation in render.py/widgets.py
(stale _order.yml entries skipped, unresolved widgets fall back to `toast`) -
this reports every such issue in one sweep instead of hiding it behind a
per-page fallback.
"""
from __future__ import annotations

from pathlib import Path

from .config import SiteConfig
from .ordering import ORDER_FILENAME, read_order_file
from .render import WIDGET_MACRO_RE
from .widgets import resolve_widget


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

    return issues
