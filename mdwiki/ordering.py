"""Page ordering: `_order.yml`, one per directory, optional. Drives
next()/prev() for the standard `next-button` widget. See README.md
"Page ordering" for the full design writeup.

Whole-tree order is one global depth-first traversal, following each level's
_order.yml (or alphabetical fallback) all the way down. A directory with its
own index.md is a leaf (folds to `dir/`, per the routing convention);
otherwise it's a transparent grouping node the walk descends into.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

ORDER_FILENAME = "_order.yml"


def read_order_file(dir_path: Path) -> list[str]:
    order_path = dir_path / ORDER_FILENAME
    if not order_path.is_file():
        return []
    raw = yaml.safe_load(order_path.read_text(encoding="utf-8")) or []
    if not isinstance(raw, list):
        return []
    return [str(entry) for entry in raw]


_read_order_file = read_order_file  # internal alias, kept for brevity below


def ordered_entries(dir_path: Path) -> list[str]:
    """Basenames of dir_path's children (files and subdirectories, `.md`
    only for files), in the manifest's order, then unlisted entries appended
    alphabetically. Stale manifest entries (no longer on disk) are skipped."""
    on_disk = {
        p.name
        for p in dir_path.iterdir()
        if p.is_dir() or (p.is_file() and p.suffix == ".md")
    }
    explicit = [name for name in _read_order_file(dir_path) if name in on_disk]
    remaining = sorted(on_disk - set(explicit))
    return explicit + remaining


@dataclass(frozen=True)
class Page:
    """One leaf in the global DFS order: a `.md` file, or a `dir/index.md`
    folded to that directory, identified by its path relative to root
    (POSIX-style, no leading slash, `.md` extension included)."""

    relpath: str


def walk(root: Path) -> list[Page]:
    """The whole content tree's pages, in global depth-first order. A
    directory with its own `index.md` is visited as a leaf on entering it
    (folds to `dir/`, per the routing convention) - the walk then continues
    into the rest of that directory's children (its `index.md` itself isn't
    re-visited), so pages nested underneath (e.g. an `exercises/` subfolder)
    are still reachable in the same global order."""
    pages: list[Page] = []

    def _walk_dir(dir_path: Path, rel_prefix: str, *, skip_own_index: bool = False) -> None:
        for name in ordered_entries(dir_path):
            if skip_own_index and name == "index.md":
                continue
            child = dir_path / name
            if child.is_file():
                pages.append(Page(relpath=f"{rel_prefix}{name}"))
            elif child.is_dir():
                index = child / "index.md"
                if index.is_file():
                    pages.append(Page(relpath=f"{rel_prefix}{name}/index.md"))
                _walk_dir(child, f"{rel_prefix}{name}/", skip_own_index=True)

    _walk_dir(root, "")
    return pages


def adjacent(root: Path, current_relpath: str, selector: str, *, direction: int) -> Page | None:
    """next(page) (direction=+1) / prev(page) (direction=-1): the adjacent
    leaf in the global DFS order, filtered down to pages matching `selector`
    (a glob against the leaf's relpath; `*` does not cross `/`, matching
    PurePosixPath.match semantics)."""
    all_pages = walk(root)
    matching = [p for p in all_pages if Path(p.relpath).match(selector)]
    relpaths = [p.relpath for p in matching]
    try:
        idx = relpaths.index(current_relpath)
    except ValueError:
        return None
    new_idx = idx + direction
    if 0 <= new_idx < len(matching):
        return matching[new_idx]
    return None


# --- insert/remove API, mirrored as `mdwiki order` CLI subcommands ---------

def _load_raw(dir_path: Path) -> list[str]:
    return _read_order_file(dir_path)


def _save_raw(dir_path: Path, entries: list[str]) -> None:
    order_path = dir_path / ORDER_FILENAME
    order_path.write_text(yaml.safe_dump(entries, sort_keys=False), encoding="utf-8")


def insert_after(dir_path: Path, existing_name: str, new_name: str) -> None:
    entries = _load_raw(dir_path)
    if existing_name not in entries:
        entries = ordered_entries(dir_path)
    idx = entries.index(existing_name) if existing_name in entries else len(entries) - 1
    entries.insert(idx + 1, new_name)
    _save_raw(dir_path, entries)


def insert_before(dir_path: Path, existing_name: str, new_name: str) -> None:
    entries = _load_raw(dir_path)
    if existing_name not in entries:
        entries = ordered_entries(dir_path)
    idx = entries.index(existing_name) if existing_name in entries else 0
    entries.insert(idx, new_name)
    _save_raw(dir_path, entries)


def append(dir_path: Path, new_name: str) -> None:
    entries = _load_raw(dir_path) or ordered_entries(dir_path)
    if new_name not in entries:
        entries.append(new_name)
    _save_raw(dir_path, entries)


def remove(dir_path: Path, name: str) -> None:
    entries = _load_raw(dir_path)
    if name in entries:
        entries.remove(name)
        _save_raw(dir_path, entries)
