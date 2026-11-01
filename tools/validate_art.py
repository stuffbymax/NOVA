"""Validate the editable SVG art pack without rewriting its source assets."""

from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets"
SVG_NAMESPACE = "{http://www.w3.org/2000/svg}"


def main() -> None:
    assets = sorted(ASSET_DIR.glob("*.svg"))
    if not assets:
        raise SystemExit(f"No SVG assets found in {ASSET_DIR}")

    for path in assets:
        root = ET.parse(path).getroot()
        if root.tag != f"{SVG_NAMESPACE}svg":
            raise SystemExit(f"Not an SVG document: {path.name}")
    print(f"Validated {len(assets)} SVG assets in {ASSET_DIR}")


if __name__ == "__main__":
    main()
