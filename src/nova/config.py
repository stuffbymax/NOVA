"""Application configuration."""

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class Config:
    """Settings needed to start NOVA."""

    debug: bool = False
    log_level: str = "INFO"
    content_path: Path = Path("content")
    asset_path: Path = Path("assets")
    save_path: Path = Path("saves")
    galaxy_seed: int = 2480
    galaxy_size: str = "medium"
    galaxy_shape: str = "spiral"
    galaxy_name: str | None = None
    window_width: int = 1280
    window_height: int = 720
    fullscreen: bool = False


def load_config(path: Path | None = None) -> Config:
    """Load optional TOML settings, falling back to safe defaults."""
    if path is None:
        path = Path("config.toml")
    if not path.is_file():
        return Config()

    with path.open("rb") as config_file:
        data = tomllib.load(config_file)
    return Config(
        debug=bool(data.get("debug", False)),
        log_level=str(data.get("log_level", "INFO")).upper(),
        content_path=Path(str(data.get("content_path", "content"))),
        asset_path=Path(str(data.get("asset_path", "assets"))),
        save_path=Path(str(data.get("save_path", "saves"))),
        galaxy_seed=int(data.get("galaxy_seed", 2480)),
        galaxy_size=str(data.get("galaxy_size", "medium")).casefold(),
        galaxy_shape=str(data.get("galaxy_shape", "spiral")).casefold(),
        galaxy_name=(
            str(data["galaxy_name"])
            if data.get("galaxy_name") is not None
            else None
        ),
        window_width=max(640, int(data.get("window_width", 1280))),
        window_height=max(360, int(data.get("window_height", 720))),
        fullscreen=bool(data.get("fullscreen", False)),
    )
