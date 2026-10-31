from pathlib import Path

from nova.config import Config, load_config


def test_default_config_is_safe(tmp_path: Path) -> None:
    assert load_config(tmp_path / "missing.toml") == Config()


def test_config_loads_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('debug = true\nlog_level = "debug"\n', encoding="utf-8")

    assert load_config(config_path) == Config(debug=True, log_level="DEBUG")
