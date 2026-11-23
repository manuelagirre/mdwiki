from pathlib import Path

from mdwiki.config import SiteConfig
from mdwiki.ordering import ordered_entries, walk
from mdwiki.validate import validate


def _touch(root: Path, *relpaths: str) -> None:
    for rel in relpaths:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# x\n" if rel.endswith(".md") else "x", encoding="utf-8")


def test_dot_dirs_and_pageless_dirs_are_not_ordered(tmp_path):
    _touch(tmp_path, "a.md", "b.md", ".hidden/x.md", "images/logo.png", "deep/more/c.md")
    assert ordered_entries(tmp_path) == ["a.md", "b.md", "deep"]
    assert [p.relpath for p in walk(tmp_path)] == ["a.md", "b.md", "deep/more/c.md"]


def test_validate_ignores_asset_dirs_but_flags_them_if_listed(tmp_path):
    _touch(tmp_path, "a.md", "images/logo.png", ".git/HEAD")
    (tmp_path / "_order.yml").write_text("- a.md\n", encoding="utf-8")
    assert validate(tmp_path, SiteConfig(), None) == []  # no "images is unlisted" noise

    (tmp_path / "_order.yml").write_text("- a.md\n- images\n", encoding="utf-8")
    issues = validate(tmp_path, SiteConfig(), None)
    assert issues == ["_order.yml: entry 'images' is not a page or a directory of pages"]
