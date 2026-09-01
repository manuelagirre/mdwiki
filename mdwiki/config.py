"""mdwiki.yml site config: title, nav links, theme override, backend_base,
and widget hook rows (auto-injected widgets). See README.md "Site config".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

VALID_ANCHORS = ("top", "bottom", "both")


@dataclass
class NavLink:
    label: str
    href: str


@dataclass
class WidgetHook:
    """One row of the `widgets:` list in mdwiki.yml: a widget auto-injected
    into every page whose resolved relative path matches `selector`."""

    name: str
    anchor: str
    selector: str

    def __post_init__(self) -> None:
        if self.anchor not in VALID_ANCHORS:
            raise ValueError(
                f"widget hook {self.name!r}: anchor must be one of {VALID_ANCHORS}, got {self.anchor!r}"
            )


@dataclass
class SiteConfig:
    title: str = "Wiki"
    nav: list[NavLink] = field(default_factory=list)
    theme_dir: Path | None = None
    backend_base: str = ""
    widget_hooks: list[WidgetHook] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path | None) -> "SiteConfig":
        if path is None or not path.is_file():
            return cls()
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

        nav = [NavLink(**item) for item in raw.get("nav", [])]
        theme = raw.get("theme")
        theme_dir = (path.parent / theme).resolve() if theme else None
        hooks = [
            WidgetHook(name=item["name"], anchor=item.get("anchor", "bottom"), selector=item["selector"])
            for item in raw.get("widgets", [])
        ]
        return cls(
            title=raw.get("title", "Wiki"),
            nav=nav,
            theme_dir=theme_dir,
            backend_base=raw.get("backend_base", ""),
            widget_hooks=hooks,
        )
