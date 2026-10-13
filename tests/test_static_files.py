from pathlib import Path

from fastapi.testclient import TestClient

from mdwiki.config import SiteConfig
from mdwiki.server import create_app
from mdwiki.validate import validate

AUTHOR_HTML = """<!doctype html>
<html><head><title>Q3 Report</title><style>body{color:red}</style></head>
<body><h1 id="summary">Summary</h1><a href="../">Home</a></body></html>
"""


def _site(tmp_path: Path) -> Path:
    (tmp_path / "index.md").write_text("# Home\n\n[Report](reports/q3.html#summary)\n", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "q3.html").write_text(AUTHOR_HTML, encoding="utf-8")
    (tmp_path / "reports" / "chart.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    (tmp_path / "reports" / "_order.yml").write_text("[]\n", encoding="utf-8")
    (tmp_path / ".wiki-manifest.json").write_text("{}", encoding="utf-8")
    return tmp_path


def _client(root: Path) -> TestClient:
    return TestClient(create_app(content_dir=root))


def test_author_html_served_in_full_as_authored(tmp_path):
    res = _client(_site(tmp_path)).get("/reports/q3.html")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    assert res.text == AUTHOR_HTML  # byte-for-byte - no page shell
    assert "site-nav" not in res.text
    assert "/_assets/app.css" not in res.text


def test_static_file_served_raw_with_guessed_content_type(tmp_path):
    res = _client(_site(tmp_path)).get("/reports/chart.png")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content == b"\x89PNG\r\n\x1a\nfake"


def test_md_page_wins_its_url_over_a_raw_file(tmp_path):
    root = _site(tmp_path)
    (root / "odd.html.md").write_text("# From Markdown\n", encoding="utf-8")
    (root / "odd.html").write_text("<p>raw</p>", encoding="utf-8")
    res = _client(root).get("/odd.html")
    assert res.status_code == 200
    assert "From Markdown" in res.text
    assert "site-nav" in res.text


def test_excluded_files_are_404(tmp_path):
    client = _client(_site(tmp_path))
    for path in ("/index.md", "/reports/_order.yml", "/.wiki-manifest.json"):
        res = client.get(path)
        assert res.status_code == 404, path
        assert res.text == "Not found"


def test_missing_raw_file_is_plain_404(tmp_path):
    res = _client(_site(tmp_path)).get("/reports/nope.html")
    assert res.status_code == 404
    assert res.text == "Not found"


def test_raw_file_traversal_is_404(tmp_path):
    root = tmp_path / "content"
    root.mkdir()
    (root / "index.md").write_text("# Home\n", encoding="utf-8")
    (tmp_path / "secret.html").write_text("<p>secret</p>", encoding="utf-8")
    res = _client(root).get("/%2e%2e/secret.html")
    assert res.status_code == 404


def test_validate_accepts_links_to_html_and_static_files(tmp_path):
    root = _site(tmp_path)
    (root / "reports" / "q3.html").write_text(
        AUTHOR_HTML.replace("<body>", '<body><img src="chart.png"><a href="chart.png">png</a>'),
        encoding="utf-8",
    )
    issues = validate(root, SiteConfig(), None)
    assert issues == []


def test_validate_checks_links_and_anchors_inside_html_pages(tmp_path):
    root = _site(tmp_path)
    (root / "reports" / "bad.html").write_text(
        '<p><a href="../nowhere.html">x</a> <a href="q3.html#nope">y</a> <a href="q3.html#summary">z</a></p>',
        encoding="utf-8",
    )
    (root / "index.md").write_text("# Home\n\n[Bad anchor](reports/q3.html#missing)\n", encoding="utf-8")
    issues = validate(root, SiteConfig(), None)
    assert any("reports/bad.html" in i and "nowhere.html" in i and "does not resolve" in i for i in issues)
    assert any("reports/bad.html" in i and "#nope" in i for i in issues)
    assert any("index.md" in i and "#missing" in i for i in issues)
    assert not any("#summary" in i for i in issues)
