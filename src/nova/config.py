"""Application configuration."""

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class Config:
    """Settings needed to start NOVA."""

    debug: bool = False
    log_level: str = "INFO"


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
    )
