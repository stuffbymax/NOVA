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
        window_width=max(640, int(data.get("window_width", 1280))),
        window_height=max(360, int(data.get("window_height", 720))),
        fullscreen=bool(data.get("fullscreen", False)),
    )
