from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from nova.assets import AssetError, AssetManager


def test_root_asset_art_is_valid_svg() -> None:
    asset_directory = Path(__file__).resolve().parents[1] / "assets"
    assets = list(asset_directory.glob("*.svg"))

    assert assets
    for path in assets:
        assert ET.parse(path).getroot().tag == "{http://www.w3.org/2000/svg}svg"


def test_missing_asset_is_reported(tmp_path: Path) -> None:
    manager = AssetManager(tmp_path)

    with pytest.raises(AssetError, match="does not exist"):
        manager.load("missing.svg")
