import json
from pathlib import Path

import pytest

from nova.campaign import Campaign
from nova.persistence import SaveError, load_campaign, save_campaign


def test_save_round_trip_preserves_campaign_state(tmp_path: Path) -> None:
    campaign = Campaign(seed=374)
    campaign.perform_action("asterion")
    campaign.perform_action("morrow")
    campaign.propose_treaty("veyra", "non_aggression")
    campaign.start_research("field-survey")
    campaign.move_fleet("frontier-survey-group", "asterion")
    campaign.advance(12)
    campaign.map_bookmarks.append("asterion")
    target = tmp_path / "slot-1.json"

    save_campaign(target, campaign)
    document = json.loads(target.read_text(encoding="utf-8"))
    assert document["metadata"]["galaxy"] == campaign.galaxy.name
    assert document["metadata"]["date"] == campaign.date_label
    loaded = load_campaign(target)

    assert loaded.galaxy.seed == campaign.galaxy.seed
    assert loaded.galaxy.routes == campaign.galaxy.routes
    assert loaded.date_label == campaign.date_label
    assert loaded.get_system("asterion").surveyed
    assert loaded.active_technology == campaign.active_technology
    assert loaded.research_progress == campaign.research_progress
    assert loaded.fleets[0].route == campaign.fleets[0].route
    assert loaded.ai_fleets[0].ship_count == campaign.ai_fleets[0].ship_count
    assert loaded.get_relation("veyra").first_contact
    assert loaded.get_relation("veyra").treaties == ["non_aggression"]
    assert loaded.colony_states.keys() == campaign.colony_states.keys()
    assert loaded.map_bookmarks == ["asterion"]


def test_save_round_trip_preserves_derived_species_and_rights(
    tmp_path: Path,
) -> None:
    campaign = Campaign()
    colony = campaign.player_colonies[0]
    campaign.researched_technologies.add("xeno-biology")
    campaign.engineer_species(
        colony.system_id,
        colony.planet_id,
        "enhanced-growth",
    )
    derived_species_id = colony.species_id
    campaign.set_species_rights(derived_species_id, "resident")
    target = tmp_path / "species-save.json"

    save_campaign(target, campaign)
    loaded = load_campaign(target)

    assert loaded.species_catalog[derived_species_id].derived_from == "union-human"
    assert loaded.species_rights[derived_species_id] == "resident"
    assert loaded.player_colonies[0].species_id == derived_species_id


def test_save_integrity_check_rejects_modified_payload(tmp_path: Path) -> None:
    target = tmp_path / "slot-1.json"
    save_campaign(target, Campaign())
    data = json.loads(target.read_text(encoding="utf-8"))
    data["campaign"]["alloys"] = 9999
    target.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(SaveError, match="integrity check"):
        load_campaign(target)


def test_save_rejects_unsupported_versions(tmp_path: Path) -> None:
    target = tmp_path / "slot-1.json"
    save_campaign(target, Campaign())
    data = json.loads(target.read_text(encoding="utf-8"))
    data["campaign"]["schema_version"] = 999
    import hashlib

    canonical = json.dumps(data["campaign"], sort_keys=True, separators=(",", ":"))
    data["checksum"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    target.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(SaveError, match="Unsupported campaign version"):
        load_campaign(target)


def test_campaign_loader_migrates_v1_saves_to_default_diplomacy() -> None:
    payload = Campaign().to_dict()
    payload["schema_version"] = 1
    payload.pop("ai_fleets")
    payload.pop("diplomacy")

    migrated = Campaign.from_dict(payload)

    assert migrated.ai_fleets
    assert not migrated.get_relation("veyra").first_contact
