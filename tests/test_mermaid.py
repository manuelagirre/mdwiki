from fastapi.testclient import TestClient

from mdwiki.config import SiteConfig
from mdwiki.render import WikiRenderer
from mdwiki.server import create_app


def test_mermaid_fence_becomes_pre_mermaid_with_raw_source(tmp_path):
    (tmp_path / "a.md").write_text(
        "# A\n\n```mermaid\nsequenceDiagram\n  A->>B: hi\n```\n",
        encoding="utf-8",
    )
    renderer = WikiRenderer(tmp_path, SiteConfig(), None)
    page = renderer.render_relpath("a.md")

    assert page.has_mermaid is True
    assert '<pre class="mermaid">' in page.content_html
    # entity-escaped in the markup, decodes back to the original text in a
    # real DOM's .textContent - never plain `<code>`/pygments highlighting.
    assert "A-&gt;&gt;B: hi" in page.content_html
    assert "<code" not in page.content_html


def test_page_without_mermaid_fence_is_unflagged(tmp_path):
    (tmp_path / "a.md").write_text("# A\n\nJust text, no diagram.\n", encoding="utf-8")
    renderer = WikiRenderer(tmp_path, SiteConfig(), None)
    page = renderer.render_relpath("a.md")

    assert page.has_mermaid is False
    assert "mermaid" not in page.content_html


def test_other_fenced_languages_still_syntax_highlighted(tmp_path):
    (tmp_path / "a.md").write_text("# A\n\n```python\nx = 1\n```\n", encoding="utf-8")
    renderer = WikiRenderer(tmp_path, SiteConfig(), None)
    page = renderer.render_relpath("a.md")

    assert page.has_mermaid is False
    assert 'class="codehilite"' in page.content_html


def test_mermaid_script_only_loaded_on_pages_that_need_it(tmp_path):
    (tmp_path / "index.md").write_text("# Home\n\n```mermaid\ngraph TD; A-->B;\n```\n", encoding="utf-8")
    (tmp_path / "plain.md").write_text("# Plain\n\nNo diagram.\n", encoding="utf-8")
    app = create_app(content_dir=tmp_path, config_path=None, widgets_dir=None)
    client = TestClient(app)

    home = client.get("/")
    plain = client.get("/plain")
    assert "mermaid.esm.min.mjs" in home.text
    assert 'class="mermaid"' in home.text
    assert "mermaid.esm.min.mjs" not in plain.text


def test_mermaid_diagram_with_parens_and_quotes_round_trips(tmp_path):
    """The exact shape wiki-describe-feature's guidance calls out: a
    participant alias with punctuation the fence must survive verbatim
    through HTML-entity escaping."""
    (tmp_path / "a.md").write_text(
        '# A\n\n```mermaid\nsequenceDiagram\n'
        '  participant SafeAlias as "handleFoo(bar)"\n'
        "  User->>SafeAlias: click\n"
        "```\n",
        encoding="utf-8",
    )
    renderer = WikiRenderer(tmp_path, SiteConfig(), None)
    page = renderer.render_relpath("a.md")

    assert "&quot;handleFoo(bar)&quot;" in page.content_html
    assert "User-&gt;&gt;SafeAlias: click" in page.content_html
