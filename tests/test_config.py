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
