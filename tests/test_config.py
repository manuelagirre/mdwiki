import pytest

from mdwiki.cli import main
from mdwiki.config import ConfigError, SiteConfig
from mdwiki.validate import validate


@pytest.mark.parametrize("text, message", [
    ("nav:\n  - label: Home\n", "nav[0] is missing 'href'"),
    ("nav: /home\n", "nav must be a list"),
    ("widgets:\n  - name: x\n", "widgets[0] is missing 'selector'"),
    ("widgets:\n  - {name: x, selector: '*', anchor: middle}\n", "anchor must be one of"),
    ("title: [1, 2\n", "not valid YAML"),
    ("- a list\n", "must be a mapping"),
])
def test_unusable_config_raises_a_clear_error(tmp_path, text, message):
    cfg = tmp_path / "mdwiki.yml"
    cfg.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match=message.replace("[", r"\[").replace("]", r"\]")):
        SiteConfig.load(cfg)


def test_unknown_keys_warn_with_suggestion_and_show_in_validate(tmp_path):
    (tmp_path / "index.md").write_text("# Home\n", encoding="utf-8")
    cfg = tmp_path / "mdwiki.yml"
    cfg.write_text("titel: X\nnavs: []\n", encoding="utf-8")
    config = SiteConfig.load(cfg)
    assert config.warnings == [
        "mdwiki.yml: unknown key 'titel' is ignored - did you mean 'title'?",
        "mdwiki.yml: unknown key 'navs' is ignored - did you mean 'nav'?",
    ]
    assert validate(tmp_path, config, None) == config.warnings


def test_cli_prints_config_errors_without_traceback(tmp_path, capsys):
    cfg = tmp_path / "mdwiki.yml"
    cfg.write_text("nav:\n  - label: Home\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exit_info:
        main(["validate", "--dir", str(tmp_path), "--config", str(cfg)])
    assert exit_info.value.code == 2
    assert "mdwiki: mdwiki.yml: nav[0] is missing 'href'" in capsys.readouterr().err


def _styled_site(tmp_path, config_text: str, css: str | None):
    from fastapi.testclient import TestClient

    from mdwiki.server import create_app

    (tmp_path / "content").mkdir()
    (tmp_path / "content" / "index.md").write_text("# Home\n", encoding="utf-8")
    if css is not None:
        (tmp_path / "style").mkdir()
        (tmp_path / "style" / "wiki.css").write_text(css, encoding="utf-8")
    cfg = tmp_path / "mdwiki.yml"
    cfg.write_text(config_text, encoding="utf-8")
    return TestClient(create_app(content_dir=tmp_path / "content", config_path=cfg)), cfg


def test_stylesheet_is_linked_after_the_default_and_served(tmp_path):
    client, _ = _styled_site(tmp_path, "stylesheet: style/wiki.css\n", "body { color: red }\n")
    html = client.get("/").text
    default = html.index('href="/_assets/app.css"')
    override = html.index('href="/_assets/stylesheet-override.css"')
    assert default < override  # later in the cascade, so it wins on equal selectors
    res = client.get("/_assets/stylesheet-override.css")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/css")
    assert res.text == "body { color: red }\n"
    assert "site-nav" in client.get("/_assets/app.css").text  # default stays intact


def test_no_stylesheet_key_links_nothing_extra(tmp_path):
    client, _ = _styled_site(tmp_path, "title: T\n", None)
    assert "stylesheet-override" not in client.get("/").text
    assert client.get("/_assets/stylesheet-override.css").status_code == 404


def test_missing_stylesheet_warns_and_links_nothing(tmp_path):
    client, cfg = _styled_site(tmp_path, "stylesheet: style/nope.css\n", None)
    assert "stylesheet-override" not in client.get("/").text
    config = SiteConfig.load(cfg)
    assert config.stylesheet is None
    assert config.warnings == ["mdwiki.yml: stylesheet 'style/nope.css' does not exist; ignored"]
    assert validate(tmp_path / "content", config, None) == config.warnings


def test_stylesheet_must_be_a_path(tmp_path):
    cfg = tmp_path / "mdwiki.yml"
    cfg.write_text("stylesheet: [a.css]\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="stylesheet must be a path"):
        SiteConfig.load(cfg)
