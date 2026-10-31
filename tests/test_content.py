import json
from pathlib import Path

import pytest

from nova.content import ContentCatalog, ContentError, load_factions, load_nations


def write_faction(root: Path, faction_id: str = "test_faction") -> None:
    faction_dir = root / "factions" / faction_id
    faction_dir.mkdir(parents=True)
    (faction_dir / "emblem.svg").write_text("<svg/>", encoding="utf-8")
    (faction_dir / "flag.svg").write_text("<svg/>", encoding="utf-8")
    (faction_dir / "faction.json").write_text(
        json.dumps(
            {
                "id": faction_id,
                "name": "Test Faction",
                "species": "aquatic",
                "emblem": "emblem.svg",
                "flag": "flag.svg",
            }
        ),
        encoding="utf-8",
    )


def test_loads_mod_faction_and_emblem_path(tmp_path: Path) -> None:
    write_faction(tmp_path)

    factions = load_factions(tmp_path)

    assert factions["test_faction"].species == "aquatic"
    assert factions["test_faction"].emblem_path.name == "emblem.svg"
    assert factions["test_faction"].flag_path.name == "flag.svg"


def test_player_can_create_faction_and_nation(tmp_path: Path) -> None:
    source_flag = tmp_path / "player-flag.svg"
    source_flag.write_text("<svg/>", encoding="utf-8")
    catalog = ContentCatalog(tmp_path)

    faction = catalog.create_faction("player_faction", "Player Faction", "synthetic", source_flag)
    nation = catalog.create_nation(
        "player_nation", "Player Nation", source_flag, faction_id=faction.faction_id
    )

    assert faction.flag_path.is_file()
    assert nation.faction_id == "player_faction"
    assert (tmp_path / "nations" / "player_nation" / "nation.json").is_file()


def test_loads_nation_with_separate_flag(tmp_path: Path) -> None:
    write_faction(tmp_path)
    nation_dir = tmp_path / "nations" / "test_nation"
    nation_dir.mkdir(parents=True)
    (nation_dir / "flag.svg").write_text("<svg/>", encoding="utf-8")
    (nation_dir / "nation.json").write_text(
        json.dumps(
            {
                "id": "test_nation",
                "name": "Test Nation",
                "faction": "test_faction",
                "flag": "flag.svg",
            }
        ),
        encoding="utf-8",
    )

    nations = load_nations(tmp_path)

    assert nations["test_nation"].faction_id == "test_faction"
    assert nations["test_nation"].flag_path.name == "flag.svg"


def test_rejects_asset_path_escape(tmp_path: Path) -> None:
    write_faction(tmp_path)
    manifest = tmp_path / "factions" / "test_faction" / "faction.json"
    manifest.write_text(
        json.dumps(
            {
                "id": "test_faction",
                "name": "Unsafe",
                "species": "synthetic",
                "emblem": "../../../outside.svg",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContentError, match="inside the content folder"):
        load_factions(tmp_path)
