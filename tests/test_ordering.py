import pytest

from mdwiki.cli import main
from mdwiki.config import SiteConfig
from mdwiki.ordering import OrderError, append, ordered_entries, walk
from mdwiki.validate import validate


def _touch(root, *relpaths):
    for rel in relpaths:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {path.stem}\n", encoding="utf-8")


def test_broken_manifest_falls_back_to_alphabetical_and_is_reported(tmp_path):
    _touch(tmp_path, "l/b.md", "l/a.md")
    (tmp_path / "l" / "_order.yml").write_text("- b.md\n- [a.md\n", encoding="utf-8")
    assert ordered_entries(tmp_path / "l") == ["a.md", "b.md"]
    [issue] = validate(tmp_path, SiteConfig(), None)
    assert issue.startswith("l/_order.yml: not valid YAML")

    (tmp_path / "l" / "_order.yml").write_text("first: b.md\n", encoding="utf-8")
    [issue] = validate(tmp_path, SiteConfig(), None)
    assert "must be a YAML list" in issue


@pytest.mark.parametrize("broken", ["- b.md\n- [a.md\n", "first: b.md\n"])
def test_order_commands_refuse_to_overwrite_a_broken_manifest(tmp_path, broken):
    _touch(tmp_path, "a.md", "b.md")
    (tmp_path / "_order.yml").write_text(broken, encoding="utf-8")
    with pytest.raises(OrderError, match="fix it by hand"):
        append(tmp_path, "c.md")
    assert (tmp_path / "_order.yml").read_text(encoding="utf-8") == broken


def test_order_cli_prints_the_refusal_without_traceback(tmp_path, capsys):
    _touch(tmp_path, "a.md")
    (tmp_path / "_order.yml").write_text("first: a.md\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exit_info:
        main(["order", "append", str(tmp_path), "c.md"])
    assert exit_info.value.code == 2
    assert "fix it by hand first" in capsys.readouterr().err


def test_git_dir_and_pageless_dirs_are_not_ordered(tmp_path):
    _touch(tmp_path, "a.md", "b.md", ".git/x.md", "images/logo.png", "deep/more/c.md")
    assert ordered_entries(tmp_path) == ["a.md", "b.md", "deep"]
    assert [p.relpath for p in walk(tmp_path)] == ["a.md", "b.md", "deep/more/c.md"]


def test_other_dot_dirs_stay_ordered_until_the_hide_rules_land(tmp_path):
    """Dot-paths other than .git are still served, so they stay in the
    order too; hiding them is the "Hide Gitignored And Configured Paths
    From Site" backlog item, which will route this through one predicate."""
    _touch(tmp_path, "a.md", ".drafts/x.md")
    assert ordered_entries(tmp_path) == [".drafts", "a.md"]


def test_validate_ignores_asset_dirs_but_flags_them_if_listed(tmp_path):
    _touch(tmp_path, "a.md", "images/logo.png", ".git/HEAD")
    (tmp_path / "_order.yml").write_text("- a.md\n", encoding="utf-8")
    assert validate(tmp_path, SiteConfig(), None) == []  # no "images is unlisted" noise

    (tmp_path / "_order.yml").write_text("- a.md\n- images\n", encoding="utf-8")
    issues = validate(tmp_path, SiteConfig(), None)
    assert issues == ["_order.yml: entry 'images' is not a page or a directory of pages"]

    (tmp_path / "_order.yml").write_text("- a.md\n- gone.md\n", encoding="utf-8")
    assert validate(tmp_path, SiteConfig(), None) == ["_order.yml: entry 'gone.md' does not exist on disk"]
