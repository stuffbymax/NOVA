from pathlib import Path

import pytest

from nova.species import load_species_catalog


ROOT = Path(__file__).resolve().parents[1]


def test_species_catalog_exposes_biology_and_hierarchical_name_sets() -> None:
    species = load_species_catalog(ROOT / "content" / "species.json")
    human = species["union-human"]

    assert human.classification == ("Humanoid", "Human")
    assert human.lifespan_years == 92
    assert human.generate_name(12, "hungarian") in {
        "Ilona Kovacs",
        "Ilona Nagy",
        "Ilona Toth",
        "Ilona Varga",
        "Miklos Kovacs",
        "Miklos Nagy",
        "Miklos Toth",
        "Miklos Varga",
        "Eszter Kovacs",
        "Eszter Nagy",
        "Eszter Toth",
        "Eszter Varga",
        "Bela Kovacs",
        "Bela Nagy",
        "Bela Toth",
        "Bela Varga",
    }
    assert human.generate_name(90) == human.generate_name(90)
    assert human.generate_name(90, "latin") != human.generate_name(90, "hungarian")


def test_species_name_generation_rejects_unknown_culture() -> None:
    human = load_species_catalog(ROOT / "content" / "species.json")["union-human"]

    with pytest.raises(ValueError, match="Unknown Human naming culture"):
        human.generate_name(1, "unknown")


def test_species_loader_rejects_unsafe_portrait_paths(tmp_path: Path) -> None:
    manifest = tmp_path / "species.json"
    manifest.write_text(
        """
        {"species":[{"id":"test","name":"Test","classification":["Test"],
        "lifespan_years":50,"annual_growth_rate":0.01,
        "preferred_climates":["Temperate"],"needs":["Food"],"traits":["Adaptable"],
        "portrait":"../outside.svg","names":{"all":{"given":["A"],"family":["B"]}}}]}
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsafe portrait path"):
        load_species_catalog(manifest)
