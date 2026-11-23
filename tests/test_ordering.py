from pathlib import Path

import pytest

from mdwiki.cli import main
from mdwiki.config import SiteConfig
from mdwiki.ordering import OrderError, append, insert_after, insert_before, ordered_entries, read_order_file, walk
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


def test_insert_moves_an_already_listed_entry_instead_of_duplicating(tmp_path):
    _touch(tmp_path, "a.md", "b.md", "c.md")
    insert_after(tmp_path, "a.md", "c.md")
    assert read_order_file(tmp_path) == ["a.md", "c.md", "b.md"]
    insert_before(tmp_path, "a.md", "b.md")
    assert read_order_file(tmp_path) == ["b.md", "a.md", "c.md"]
    append(tmp_path, "b.md")
    assert read_order_file(tmp_path) == ["a.md", "c.md", "b.md"]


def test_insert_relative_to_unknown_entry_fails_without_writing(tmp_path):
    _touch(tmp_path, "a.md")
    for op in (insert_after, insert_before):
        with pytest.raises(OrderError):
            op(tmp_path, "typo.md", "new.md")
    assert not (tmp_path / "_order.yml").exists()


def test_new_entry_can_be_listed_before_its_file_exists(tmp_path):
    _touch(tmp_path, "a.md", "b.md")
    insert_after(tmp_path, "a.md", "draft.md")
    assert read_order_file(tmp_path) == ["a.md", "draft.md", "b.md"]


def test_order_cli_reports_errors_instead_of_a_traceback(tmp_path, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["order", "append", str(tmp_path / "missing"), "x.md"])
    assert exit_info.value.code == 2
    assert "is not a directory" in capsys.readouterr().err


def test_broken_manifest_falls_back_to_alphabetical_and_is_reported(tmp_path):
    _touch(tmp_path, "l/b.md", "l/a.md")
    (tmp_path / "l" / "_order.yml").write_text("- b.md\n- [a.md\n", encoding="utf-8")
    assert ordered_entries(tmp_path / "l") == ["a.md", "b.md"]
    [issue] = validate(tmp_path, SiteConfig(), None)
    assert issue.startswith("l/_order.yml: not valid YAML")

    (tmp_path / "l" / "_order.yml").write_text("first: b.md\n", encoding="utf-8")
    [issue] = validate(tmp_path, SiteConfig(), None)
    assert "must be a YAML list" in issue


def test_order_commands_refuse_to_overwrite_a_broken_manifest(tmp_path):
    _touch(tmp_path, "a.md", "b.md")
    broken = "- b.md\n- [a.md\n"
    (tmp_path / "_order.yml").write_text(broken, encoding="utf-8")
    with pytest.raises(OrderError, match="fix it by hand"):
        append(tmp_path, "c.md")
    assert (tmp_path / "_order.yml").read_text(encoding="utf-8") == broken
