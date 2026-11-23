from pathlib import Path

import pytest

from mdwiki.build import MARKER, BuildError, build

EXAMPLE = (Path(__file__).parent.parent / "example").resolve()


def _files(out: Path) -> set[str]:
    return {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}


def test_build_example_site(tmp_path):
    out = tmp_path / "site"
    pages = build(EXAMPLE, out, EXAMPLE / "mdwiki.yml")
    assert pages == 5
    files = _files(out)
    assert {
        "index.html",
        "404.html",
        "lessons/index.html",
        "lessons/lesson-1.html",
        "lessons/lesson-3.html",
        "_assets/app.css",
        "_assets/shadow-helper.js",
        "_widgets/toast/widget.js",
        "_widgets/next-button/widget.css",
        MARKER,
    } <= files
    assert not any(f.endswith(".md") or f.endswith("_order.yml") for f in files)

    lesson = (out / "lessons" / "lesson-1.html").read_text(encoding="utf-8")
    assert 'href="/lessons/lesson-2"' in lesson  # next-button target
    assert 'class="site-search"' not in lesson  # no server behind /_search
    assert "Page not found" in (out / "404.html").read_text(encoding="utf-8")


def test_build_listings_raw_files_and_skips_dot_paths(tmp_path):
    src = tmp_path / "src"
    for rel, text in {
        "guides/a.md": "# A\n",
        "guides/img.png": "png",
        "report.html": "<h1>raw</h1>",
        ".github/x.md": "# hidden\n",
    }.items():
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        (src / rel).write_text(text, encoding="utf-8")
    out = tmp_path / "out"
    build(src, out)
    files = _files(out)
    assert {"index.html", "guides/index.html", "guides/a.html", "guides/img.png", "report.html"} <= files
    assert not any(".github" in f for f in files)
    assert "<h1>raw</h1>" == (out / "report.html").read_text(encoding="utf-8")


def test_rebuild_replaces_previous_output_but_never_foreign_dirs(tmp_path):
    out = tmp_path / "site"
    build(EXAMPLE, out, EXAMPLE / "mdwiki.yml")
    (out / "stale.html").write_text("old", encoding="utf-8")
    build(EXAMPLE, out, EXAMPLE / "mdwiki.yml")
    assert not (out / "stale.html").exists()

    foreign = tmp_path / "mine"
    foreign.mkdir()
    (foreign / "keep.txt").write_text("precious", encoding="utf-8")
    with pytest.raises(BuildError, match="refusing to overwrite"):
        build(EXAMPLE, foreign)
    assert (foreign / "keep.txt").read_text(encoding="utf-8") == "precious"


def test_build_refuses_output_inside_content_and_path_collisions(tmp_path):
    (tmp_path / "index.md").write_text("# Home\n", encoding="utf-8")
    with pytest.raises(BuildError, match="inside the content root"):
        build(tmp_path, tmp_path / "site")

    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.md").write_text("# Foo\n", encoding="utf-8")
    (src / "foo.html").write_text("<p>raw</p>", encoding="utf-8")
    with pytest.raises(BuildError, match="foo.html"):
        build(src, tmp_path / "out")


def test_broken_config_leaves_previous_export_untouched(tmp_path):
    from mdwiki.config import ConfigError

    out = tmp_path / "site"
    build(EXAMPLE, out, EXAMPLE / "mdwiki.yml")
    bad = tmp_path / "bad.yml"
    bad.write_text("nav:\n  - label: Home\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        build(EXAMPLE, out, bad)
    assert (out / "lessons" / "lesson-1.html").is_file()
