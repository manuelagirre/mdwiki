"""The one rule for which content-root paths are part of the site.

Anything under a path segment starting with `.` (`.git/`, `.github/`,
`.drafts/`, a `.notes.md` file) is not: it is never rendered, served raw,
listed, ordered, searched, validated, exported or watched. Every module
asks here instead of re-implementing the check.
"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import PurePath


def is_hidden(rel: str | PurePath | Sequence[str]) -> bool:
    """Whether a root-relative path - a POSIX string like `a/.b/c.md`, a
    PurePath, or its segments - has any dot-segment."""
    if isinstance(rel, str):
        parts: Sequence[str] = rel.split("/")
    elif isinstance(rel, PurePath):
        parts = rel.parts
    else:
        parts = rel
    return any(part.startswith(".") for part in parts)
