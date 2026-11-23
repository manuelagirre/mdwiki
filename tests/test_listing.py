from pathlib import Path

from fastapi.testclient import TestClient

from mdwiki.config import SiteConfig
from mdwiki.server import create_app
from mdwiki.validate import validate


def _write(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def test_directory_without_index_gets_a_listing(tmp_path):
    _write(tmp_path, {
        "index.md": "# Home\n",
        "guides/b.md": "# Second & Guide\n",
        "guides/a.md": "# First Guide\n",
        "guides/_order.yml": "- b.md\n- a.md\n",
        "guides/deep/index.md": "# Deep Dive\n",
        "guides/images/logo.png": "png",
        "guides/.hidden/secret.md": "# Secret\n",
    })
    client = TestClient(create_app(content_dir=tmp_path))
    res = client.get("/guides/")
    assert res.status_code == 200
    body = res.text
    assert '<a href="b">Second &amp; Guide</a>' in body
    assert '<a href="a">First Guide</a>' in body
    assert body.index("Second") < body.index("First")  # _order.yml respected
    assert '<a href="deep/">Deep Dive</a>' in body
    assert "images" not in body and "Secret" not in body

    # canonical form, and relative links on it resolve
    res = client.get("/guides", follow_redirects=False)
    assert res.status_code == 308 and res.headers["location"] == "/guides/"
    assert client.get("/guides/b").status_code == 200


def test_root_without_index_md_gets_a_listing(tmp_path):
    _write(tmp_path, {"notes.md": "# Notes\n"})
    res = TestClient(create_app(content_dir=tmp_path)).get("/")
    assert res.status_code == 200
    assert '<a href="notes">Notes</a>' in res.text


def test_authored_index_still_wins_and_non_page_dirs_404(tmp_path):
    _write(tmp_path, {"index.md": "# Authored Home\n", "x.md": "# X\n", "images/a.png": "png"})
    client = TestClient(create_app(content_dir=tmp_path))
    assert "Authored Home" in client.get("/").text
    assert client.get("/images/").status_code == 404
    assert client.get("/.git/").status_code == 404


def test_validate_accepts_links_to_listed_directories(tmp_path):
    _write(tmp_path, {"index.md": "# Home\n\n[Guides](guides/)\n", "guides/a.md": "# A\n"})
    assert validate(tmp_path, SiteConfig(), None) == []


def test_index_override_is_served_at_root_not_redirected(tmp_path):
    _write(tmp_path, {"Project-Overview.md": "# Overview\n"})
    cfg = tmp_path / "mdwiki.yml"
    cfg.write_text("index: Project-Overview.md\n", encoding="utf-8")
    res = TestClient(create_app(content_dir=tmp_path, config_path=cfg)).get("/", follow_redirects=False)
    assert res.status_code == 200
    assert "Overview" in res.text


def test_breadcrumbs_for_nested_pages_and_listings(tmp_path):
    from mdwiki.render import WikiRenderer

    _write(tmp_path, {
        "index.md": "# Home\n",
        "top.md": "# Top\n",
        "guides/index.md": "# All Guides\n",
        "guides/setup.md": "# Setup\n",
        "guides/deep-dives/caching.md": "# Caching\n",
        "guides/deep-dives/more/x.md": "# X\n",
        "lessons/one.md": "---\nback_link: {href: /, label: Home}\n---\n# One\n",
    })
    r = WikiRenderer(tmp_path, SiteConfig(title="My Wiki"), None)
    crumbs = lambda rel: [(c["href"], c["label"]) for c in r.render_relpath(rel).breadcrumbs]

    assert crumbs("top.md") == []
    assert crumbs("guides/index.md") == []  # a top-level folder's own page
    assert crumbs("guides/setup.md") == [("/", "My Wiki"), ("/guides/", "All Guides")]
    assert crumbs("guides/deep-dives/caching.md") == [
        ("/", "My Wiki"), ("/guides/", "All Guides"), ("/guides/deep-dives/", "Deep Dives"),
    ]
    assert crumbs("lessons/one.md") == []  # explicit back_link wins
    # a generated listing gets crumbs to its parent folders
    listing = r.render_listing("guides/deep-dives/more")
    assert [c["href"] for c in listing.breadcrumbs] == ["/", "/guides/", "/guides/deep-dives/"]

    html = TestClient(create_app(content_dir=tmp_path)).get("/guides/setup").text
    assert '<nav class="breadcrumbs" aria-label="Breadcrumb">' in html
