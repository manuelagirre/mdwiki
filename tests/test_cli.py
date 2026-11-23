import pytest

from mdwiki import __version__
from mdwiki.cli import main


def _run(argv, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(argv)
    out = capsys.readouterr()
    return exit_info.value.code, out.out + out.err


def test_version(capsys):
    code, out = _run(["--version"], capsys)
    assert code == 0 and __version__ in out


@pytest.mark.parametrize("argv, message", [
    (["validate", "--dir", "{tmp}/nope"], "not a directory"),
    (["validate", "--dir", "{tmp}", "--config", "{tmp}/nope.yml"], "no such file"),
    (["validate", "--dir", "{tmp}", "--widgets", "{tmp}/nope"], "not a directory"),
    (["serve", "--dir", "{tmp}/nope"], "not a directory"),
])
def test_mistyped_paths_are_errors_not_silently_clean(tmp_path, capsys, argv, message):
    code, out = _run([a.format(tmp=tmp_path) for a in argv], capsys)
    assert code == 2
    assert message in out


def test_validate_on_a_real_dir_still_works(tmp_path, capsys):
    (tmp_path / "index.md").write_text("# Home\n", encoding="utf-8")
    code, out = _run(["validate", "--dir", str(tmp_path)], capsys)
    assert code == 0 and "clean" in out


def test_warnings_alone_pass_unless_strict(tmp_path, capsys):
    (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# B\n", encoding="utf-8")
    (tmp_path / "_order.yml").write_text("- a.md\n", encoding="utf-8")  # b.md unlisted

    code, out = _run(["validate", "--dir", str(tmp_path)], capsys)
    assert code == 0 and "1 warning(s)" in out and "'b.md' is present but unlisted" in out
    code, out = _run(["validate", "--dir", str(tmp_path), "--strict"], capsys)
    assert code == 1 and "failing: --strict" in out


def test_errors_fail_and_are_listed_before_warnings(tmp_path, capsys):
    (tmp_path / "a.md").write_text("# A\n\n[x](nope.md)\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# B\n", encoding="utf-8")
    (tmp_path / "_order.yml").write_text("- a.md\n", encoding="utf-8")
    code, out = _run(["validate", "--dir", str(tmp_path)], capsys)
    assert code == 1
    assert out.index("1 error(s)") < out.index("1 warning(s)")
