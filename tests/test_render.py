import re
from pathlib import Path

from fastapi.testclient import TestClient

from mdwiki.server import create_app
from mdwiki.validate import validate
from mdwiki.config import SiteConfig
from mdwiki.render import WikiRenderer

EXAMPLE = (Path(__file__).parent.parent / "example").resolve()


def _client() -> TestClient:
    app = create_app(
        content_dir=EXAMPLE,
        config_path=EXAMPLE / "mdwiki.yml",
        widgets_dir=None,
    )
    return TestClient(app)


def test_home_page_renders_and_has_toast_macro():
    client = _client()
    res = client.get("/")
    assert res.status_code == 200
    assert "Example Wiki" in res.text
    assert 'data-widget="toast"' in res.text
    assert '/_widgets/toast/widget.js' in res.text


def test_lessons_index_has_back_link_and_no_next_button():
    client = _client()
    res = client.get("/lessons/")
    assert res.status_code == 200
    assert "Back to Home" in res.text
    assert 'data-widget="next-button"' not in res.text


def test_lesson_1_has_next_button_pointing_to_lesson_2():
    client = _client()
    res = client.get("/lessons/lesson-1")
    assert res.status_code == 200
    assert 'data-widget="next-button"' in res.text
    assert 'href="/lessons/lesson-2"' in res.text
    assert "Lesson 2" in res.text  # label = target's title
    assert 'data-widget="toast"' in res.text  # macro-authored widget


def test_lesson_3_is_last_no_next_button():
    client = _client()
    res = client.get("/lessons/lesson-3")
    assert res.status_code == 200
    assert 'data-widget="next-button"' not in res.text


def test_unresolved_widget_falls_back_to_toast_error():
    from mdwiki.widgets import widget_markup

    markup = widget_markup("does-not-exist", {}, None)
    assert 'data-widget="toast"' in markup
    assert 'style="error"' in markup


def test_path_traversal_is_404():
    client = _client()
    res = client.get("/../../etc/passwd")
    assert res.status_code in (404, 307)  # some clients normalize the path first
    if res.status_code == 307:
        res = client.get(res.headers["location"])
    assert res.status_code == 404


def test_missing_page_is_404():
    client = _client()
    res = client.get("/nope/does-not-exist")
    assert res.status_code == 404


def test_widget_assets_serve():
    client = _client()
    res = client.get("/_widgets/toast/widget.js")
    assert res.status_code == 200
    res = client.get("/_widgets/toast/widget.css")
    assert res.status_code == 200
    res = client.get("/_widgets/no-such-widget/widget.js")
    assert res.status_code == 404


def test_theme_assets_serve():
    client = _client()
    res = client.get("/_assets/app.css")
    assert res.status_code == 200
    res = client.get("/_assets/shadow-helper.js")
    assert res.status_code == 200


def test_validate_is_clean_on_example_site():
    config = SiteConfig.load(EXAMPLE / "mdwiki.yml")
    issues = validate(EXAMPLE, config, None)
    assert issues == []


def test_md_suffixed_relative_link_resolves_through_the_live_server():
    """lesson-1.md links to `lesson-2.md#lesson-2-widgets` - the GitHub-native
    relative convention. Confirms the rewritten href a browser actually
    follows (resolved relative to the *page's* URL, not the request root)
    lands on a real 200 with the anchor present - not just that validate()
    agrees with itself."""
    from urllib.parse import urljoin

    client = _client()
    res = client.get("/lessons/lesson-1")
    assert res.status_code == 200
    m = re.search(r'<a href="(lesson-2[^"]*)">Lesson 2</a>', res.text)
    assert m, "expected the rewritten lesson-2 link in lesson-1's rendered HTML"
    href = m.group(1)
    assert href == "lesson-2#lesson-2-widgets"  # `.md` suffix stripped

    target_url = urljoin("/lessons/lesson-1", href)
    path, _, fragment = target_url.partition("#")
    target_res = client.get(path)
    assert target_res.status_code == 200
    assert f'id="{fragment}"' in target_res.text


def test_index_override_serves_at_root(tmp_path):
    (tmp_path / "Project-Overview.md").write_text("# Overview\n", encoding="utf-8")
    config = SiteConfig(index_page="Project-Overview.md")
    renderer = WikiRenderer(tmp_path, config, None)
    assert renderer.resolve_url("") == "Project-Overview.md"
    assert renderer.render_url("").title == "Overview"


def test_index_override_falls_back_to_plain_index_md_when_missing(tmp_path):
    (tmp_path / "index.md").write_text("# Fallback\n", encoding="utf-8")
    config = SiteConfig(index_page="Project-Overview.md")  # declared but file absent
    renderer = WikiRenderer(tmp_path, config, None)
    assert renderer.resolve_url("") == "index.md"


def test_validate_catches_dangling_link_and_broken_anchor(tmp_path):
    (tmp_path / "a.md").write_text(
        "# Page A\n\n[Broken](nowhere.md)\n\n[Bad anchor](b.md#nope)\n\n[Good](b.md#hello)\n",
        encoding="utf-8",
    )
    (tmp_path / "b.md").write_text("# Hello\n", encoding="utf-8")

    issues = validate(tmp_path, SiteConfig(), None)
    assert any("nowhere" in i and "does not resolve" in i for i in issues)
    assert any("#nope" in i for i in issues)
    assert not any("hello" in i.lower() and "anchor" in i.lower() for i in issues)
