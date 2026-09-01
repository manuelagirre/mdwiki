"""Widget resolution: `./widgets/<name>/` convention (host-supplied) plus
the standard set shipped with mdwiki itself (`toast`, `next-button`).
Resolution order: host's widgets dir first, then the standard set, then the
`toast` not-found fallback. See README.md "Writing a widget".
"""
from __future__ import annotations

from html import escape
from pathlib import Path

STANDARD_WIDGETS_DIR = (Path(__file__).parent / "widgets").resolve()


def resolve_widget(name: str, widgets_dir: Path | None) -> Path | None:
    """The directory backing widget `name`, or None if it resolves nowhere.
    A host can shadow a standard widget by providing its own `./widgets/<name>/`
    with the same name - its widgets dir is checked first."""
    if widgets_dir is not None:
        candidate = widgets_dir / name
        if candidate.is_dir():
            return candidate
    candidate = STANDARD_WIDGETS_DIR / name
    if candidate.is_dir():
        return candidate
    return None


def widget_markup(name: str, attrs: dict[str, str], widgets_dir: Path | None) -> str:
    """One widget occurrence's HTML: a Shadow-DOM host `<div>` carrying attrs
    as plain attributes, plus its `<script type="module">` bootstrap tag.
    Never fails the page - an unresolved name substitutes the built-in
    `toast` widget, styled as an error, in its place."""
    resolved = resolve_widget(name, widgets_dir)
    if resolved is None:
        resolved_name = "toast"
        attrs = {"title": "Widget not found", "text": f"No widget named {name!r}.", "style": "error"}
    else:
        resolved_name = name

    attr_str = " ".join(f'{k}="{escape(v, quote=True)}"' for k, v in attrs.items())
    host = f'<div class="mdwiki-widget" data-widget="{resolved_name}"{" " + attr_str if attr_str else ""}></div>'
    script = f'<script type="module" src="/_widgets/{resolved_name}/widget.js"></script>'
    return f"{host}\n{script}"
