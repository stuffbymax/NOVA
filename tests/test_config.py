from pathlib import Path

from nova.config import Config, load_config


def test_config_loads_window_and_asset_settings(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'asset_path = "custom-assets"\nwindow_width = 1600\nfullscreen = true\n',
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.asset_path == Path("custom-assets")
    assert config.window_width == 1600
    assert config.fullscreen is True


def test_default_config_keeps_display_defaults() -> None:
    assert Config().window_width == 1280
    assert Config().window_height == 720
