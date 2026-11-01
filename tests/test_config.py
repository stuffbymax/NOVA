from pathlib import Path

from nova.config import Config, load_config


def test_config_loads_window_and_asset_settings(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'asset_path = "custom-assets"\nwindow_width = 1600\nfullscreen = true\n'
        'galaxy_seed = 19384\ngalaxy_size = "large"\ngalaxy_shape = "elliptical"\n'
        'galaxy_name = "Messier 87 (Virgo A)"\n',
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.asset_path == Path("custom-assets")
    assert config.window_width == 1600
    assert config.fullscreen is True
    assert config.galaxy_seed == 19384
    assert config.galaxy_size == "large"
    assert config.galaxy_shape == "elliptical"
    assert config.galaxy_name == "Messier 87 (Virgo A)"


def test_default_config_keeps_display_defaults() -> None:
    assert Config().window_width == 1280
    assert Config().window_height == 720
    assert Config().galaxy_seed == 2480
