from pathlib import Path

from fastapi.testclient import TestClient

from mdwiki.config import SiteConfig
from mdwiki.render import WikiRenderer
from mdwiki.search import search
from mdwiki.server import create_app


def _site(root: Path) -> Path:
    files = {
        "index.md": "# Home\n\nWelcome. See the [routing guide](routing.md).\n",
        "routing.md": "# Routing\n\nHow URLs map to files. Routing is path-mirroring.\n",
        "deep/widgets.md": "---\ntitle: Widgets & Hooks\n---\nWidgets can be auto-injected; routing is not involved.\n",
        "My Notes.md": "# My Notes\n\nSome <b>bold</b> claims about routing.\n",
        ".hidden/secret.md": "# Secret routing\n",
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def test_title_hits_rank_first_and_dot_dirs_are_skipped(tmp_path):
    hits = search(WikiRenderer(_site(tmp_path), SiteConfig(), None), "routing")
    urls = [h.url for h in hits]
    assert urls[0] == "/routing"  # title match
    assert set(urls) == {"/routing", "/", "/deep/widgets", "/My Notes"}


def test_all_terms_must_match_and_case_is_ignored(tmp_path):
    renderer = WikiRenderer(_site(tmp_path), SiteConfig(), None)
    assert [h.url for h in search(renderer, "WIDGETS injected")] == ["/deep/widgets"]
    assert search(renderer, "widgets nonexistentword") == []
    assert search(renderer, "   ") == []


def test_search_page_escapes_and_highlights(tmp_path):
    client = TestClient(create_app(content_dir=_site(tmp_path)))
    res = client.get("/_search", params={"q": "nomatch <script>x</script>"})
    assert res.status_code == 200
    assert "<script>" not in res.text.split("<main", 1)[1]
    assert "No pages match" in res.text

    res = client.get("/_search", params={"q": "claims"})
    assert '<a href="/My%20Notes">My Notes</a>' in res.text
    assert "<mark>claims</mark>" in res.text
    assert "<b>bold</b>" not in res.text  # page HTML is not echoed into snippets


def test_nav_has_a_search_box(tmp_path):
    res = TestClient(create_app(content_dir=_site(tmp_path))).get("/")
    assert 'action="/_search"' in res.text


def test_identifiers_with_markdown_punctuation_are_findable(tmp_path):
    (tmp_path / "code.md").write_text("# Code\n\nCalls `widget_markup()` here.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n", encoding="utf-8")
    renderer = WikiRenderer(tmp_path, SiteConfig(), None)
    [hit] = search(renderer, "widget_markup")
    assert "---" not in hit.snippet_html


def test_result_count_is_exact_and_list_is_capped(tmp_path):
    from mdwiki.search import MAX_RESULTS, results_html

    for i in range(MAX_RESULTS + 3):
        (tmp_path / f"p{i:03}.md").write_text(f"# P{i}\n\nneedle\n", encoding="utf-8")
    hits = search(WikiRenderer(tmp_path, SiteConfig(), None), "needle")
    html = results_html("needle", hits)
    assert f"{MAX_RESULTS + 3} pages match" in html
    assert f"showing the first {MAX_RESULTS}" in html
    assert html.count("<li>") == MAX_RESULTS

    html = results_html("needle", hits[:MAX_RESULTS])
    assert f"{MAX_RESULTS} pages match" in html and "showing" not in html
