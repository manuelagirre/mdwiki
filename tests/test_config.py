from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mdwiki.cli import main
from mdwiki.config import ConfigError, SiteConfig
from mdwiki.server import create_app
from mdwiki.validate import validate


def _host_widget(widgets: Path, name: str) -> None:
    (widgets / name).mkdir(parents=True)
    (widgets / name / "widget.js").write_text("// host widget\n", encoding="utf-8")


def test_widgets_dir_resolves_relative_to_config_file(tmp_path):
    (tmp_path / "site").mkdir()
    cfg = tmp_path / "site" / "mdwiki.yml"
    cfg.write_text("widgets_dir: ./my-widgets\n", encoding="utf-8")
    assert SiteConfig.load(cfg).widgets_dir == (tmp_path / "site" / "my-widgets").resolve()
    assert SiteConfig.load(None).widgets_dir is None


def test_widgets_dir_from_config_is_served(tmp_path):
    (tmp_path / "index.md").write_text("# Home\n\n{{ widget: hello }}\n", encoding="utf-8")
    _host_widget(tmp_path / "w", "hello")
    cfg = tmp_path / "mdwiki.yml"
    cfg.write_text("widgets_dir: w\n", encoding="utf-8")

    client = TestClient(create_app(content_dir=tmp_path, config_path=cfg))
    assert 'data-widget="hello"' in client.get("/").text  # not the toast fallback
    assert client.get("/_widgets/hello/widget.js").text == "// host widget\n"


def test_explicit_widgets_arg_overrides_config(tmp_path):
    (tmp_path / "index.md").write_text("# Home\n", encoding="utf-8")
    _host_widget(tmp_path / "from-config", "hello")
    _host_widget(tmp_path / "from-arg", "other")
    cfg = tmp_path / "mdwiki.yml"
    cfg.write_text("widgets_dir: from-config\n", encoding="utf-8")

    client = TestClient(create_app(content_dir=tmp_path, config_path=cfg, widgets_dir=tmp_path / "from-arg"))
    assert client.get("/_widgets/other/widget.js").status_code == 200
    assert client.get("/_widgets/hello/widget.js").status_code == 404


def _themed_client(tmp_path: Path, files: dict[str, str]) -> TestClient:
    (tmp_path / "index.md").write_text("# Home\n", encoding="utf-8")
    theme = tmp_path / "theme"
    theme.mkdir()
    for name, text in files.items():
        (theme / name).write_text(text, encoding="utf-8")
    cfg = tmp_path / "mdwiki.yml"
    cfg.write_text("theme: theme\n", encoding="utf-8")
    return TestClient(create_app(content_dir=tmp_path, config_path=cfg))


def test_css_only_theme_keeps_default_template(tmp_path):
    client = _themed_client(tmp_path, {"app.css": "body { color: red }"})
    res = client.get("/")
    assert res.status_code == 200 and "<h1" in res.text
    assert client.get("/_assets/app.css").text == "body { color: red }"


def test_template_only_theme_keeps_default_css(tmp_path):
    client = _themed_client(tmp_path, {"page.html": "<main>{{ content|safe }}</main>"})
    assert client.get("/").text.startswith("<main>")
    res = client.get("/_assets/app.css")
    assert res.status_code == 200 and "site-nav" in res.text  # the default stylesheet


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
    cfg.write_text("titel: X\nwidget_dir: w\n", encoding="utf-8")
    config = SiteConfig.load(cfg)
    assert config.warnings == [
        "mdwiki.yml: unknown key 'titel' is ignored - did you mean 'title'?",
        "mdwiki.yml: unknown key 'widget_dir' is ignored - did you mean 'widgets_dir'?",
    ]
    assert validate(tmp_path, config, None) == config.warnings


def test_cli_prints_config_errors_without_traceback(tmp_path, capsys):
    cfg = tmp_path / "mdwiki.yml"
    cfg.write_text("nav:\n  - label: Home\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exit_info:
        main(["validate", "--dir", str(tmp_path), "--config", str(cfg)])
    assert exit_info.value.code == 2
    assert "mdwiki: mdwiki.yml: nav[0] is missing 'href'" in capsys.readouterr().err
