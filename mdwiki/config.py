"""mdwiki.yml site config: title, nav links, theme override, widgets dir,
backend_base, index override, and widget hook rows (auto-injected
widgets). See README.md "Site config".
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

VALID_ANCHORS = ("top", "bottom", "both")


KNOWN_KEYS = ("title", "index", "nav", "theme", "widgets_dir", "backend_base", "widgets")


class ConfigError(ValueError):
    """mdwiki.yml can't be used as written; the message names the file and
    the offending key or list entry."""


def _entries(raw: dict, key: str, required: tuple[str, ...], path: Path) -> list[dict]:
    """`raw[key]` as a list of mappings that each have `required` keys."""
    items = raw.get(key) or []
    if not isinstance(items, list):
        raise ConfigError(f"{path.name}: {key} must be a list of entries")
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ConfigError(f"{path.name}: {key}[{i}] must be a mapping like {{{', '.join(f'{r}: ...' for r in required)}}}")
        missing = [r for r in required if r not in item]
        if missing:
            raise ConfigError(f"{path.name}: {key}[{i}] is missing {', '.join(repr(m) for m in missing)}")
    return items


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
    widgets_dir: Path | None = None
    """`widgets_dir:` - host widgets directory, resolved relative to the
    config file (like `theme:`). An explicit `--widgets` / `widgets=`
    argument takes precedence over it."""
    index_page: str | None = None
    """Relpath (e.g. "Project-Overview.md") of the file to serve at `/`,
    instead of requiring a literal `index.md` at the content root. See
    README.md "Site config" - `index:`. WikiRenderer tries this before
    falling back to plain `index.md`, so an absent/missing override never
    breaks the plain-`index.md` case."""

    warnings: list[str] = field(default_factory=list)
    """Non-fatal problems found while loading (unknown keys, most likely
    typos). `serve` prints them at startup; `validate` reports them."""

    @classmethod
    def load(cls, path: Path | None) -> "SiteConfig":
        """Raises ConfigError (with the offending key/entry named) for a
        config that can't be used as written."""
        if path is None or not path.is_file():
            return cls()
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
        except yaml.YAMLError as exc:
            raise ConfigError(f"{path.name}: not valid YAML ({str(exc).splitlines()[0]})") from None
        raw = {} if raw is None else raw
        if not isinstance(raw, dict):
            raise ConfigError(f"{path.name}: must be a mapping of settings (title:, nav:, ...)")

        warnings = []
        for key in raw:
            if key not in KNOWN_KEYS:
                close = difflib.get_close_matches(str(key), KNOWN_KEYS, n=1)
                hint = f" - did you mean {close[0]!r}?" if close else ""
                warnings.append(f"{path.name}: unknown key {key!r} is ignored{hint}")

        nav = [
            NavLink(label=str(item["label"]), href=str(item["href"]))
            for item in _entries(raw, "nav", ("label", "href"), path)
        ]
        hooks = []
        for i, item in enumerate(_entries(raw, "widgets", ("name", "selector"), path)):
            try:
                hooks.append(
                    WidgetHook(name=str(item["name"]), anchor=item.get("anchor", "bottom"), selector=str(item["selector"]))
                )
            except ValueError as exc:
                raise ConfigError(f"{path.name}: widgets[{i}]: {exc}") from None
        theme = raw.get("theme")
        theme_dir = (path.parent / theme).resolve() if theme else None
        widgets = raw.get("widgets_dir")
        widgets_dir = (path.parent / widgets).resolve() if widgets else None
        return cls(
            title=str(raw.get("title", "Wiki")),
            nav=nav,
            theme_dir=theme_dir,
            widgets_dir=widgets_dir,
            backend_base=raw.get("backend_base", "") or "",
            widget_hooks=hooks,
            index_page=raw.get("index"),
            warnings=warnings,
        )

