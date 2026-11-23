from pathlib import Path

from fastapi.testclient import TestClient

from mdwiki.config import SiteConfig
from mdwiki.server import create_app


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
