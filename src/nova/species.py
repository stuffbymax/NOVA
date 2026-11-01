"""Data-driven species profiles and deterministic name generation."""

from dataclasses import dataclass
import json
from pathlib import Path
import random


@dataclass(frozen=True)
class SpeciesProfile:
    species_id: str
    name: str
    classification: tuple[str, ...]
    lifespan_years: int
    annual_growth_rate: float
    preferred_climates: tuple[str, ...]
    needs: tuple[str, ...]
    traits: tuple[str, ...]
    portrait: str
    name_sets: dict[str, tuple[tuple[str, ...], tuple[str, ...]]]

    def generate_name(self, seed: int, culture: str = "all") -> str:
        if culture == "all":
            pools = tuple(self.name_sets.values())
            given = tuple(dict.fromkeys(name for pool, _ in pools for name in pool))
            family = tuple(dict.fromkeys(name for _, pool in pools for name in pool))
        else:
            try:
                given, family = self.name_sets[culture.casefold()]
            except KeyError as error:
                raise ValueError(
                    f"Unknown {self.name} naming culture: {culture}"
                ) from error
        if not given or not family:
            raise ValueError(f"{self.name} has an empty name pool")
        rng = random.Random(seed)
        return f"{rng.choice(given)} {rng.choice(family)}"

    def is_compatible_with(self, other: "SpeciesProfile") -> bool:
        return bool(set(self.preferred_climates) & set(other.preferred_climates))


def load_species_catalog(manifest_path: Path) -> dict[str, SpeciesProfile]:
    """Load and validate species definitions and their hierarchical name pools."""
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not load species catalog: {manifest_path}") from error
    if not isinstance(data, dict) or not isinstance(data.get("species"), list):
        raise ValueError(f"Invalid species catalog: {manifest_path}")

    profiles: dict[str, SpeciesProfile] = {}
    for entry in data["species"]:
        try:
            species_id = str(entry["id"])
            name_sets = {
                str(culture).casefold(): (
                    tuple(map(str, names["given"])),
                    tuple(map(str, names["family"])),
                )
                for culture, names in entry["names"].items()
            }
            profile = SpeciesProfile(
                species_id=species_id,
                name=str(entry["name"]),
                classification=tuple(map(str, entry["classification"])),
                lifespan_years=int(entry["lifespan_years"]),
                annual_growth_rate=float(entry["annual_growth_rate"]),
                preferred_climates=tuple(map(str, entry["preferred_climates"])),
                needs=tuple(map(str, entry["needs"])),
                traits=tuple(map(str, entry["traits"])),
                portrait=str(entry["portrait"]),
                name_sets=name_sets,
            )
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise ValueError(
                f"Invalid species entry in {manifest_path}"
            ) from error
        if not species_id or species_id in profiles:
            raise ValueError(f"Invalid or duplicate species id: {species_id}")
        if profile.lifespan_years <= 0 or profile.annual_growth_rate < 0:
            raise ValueError(f"Invalid biology for species {species_id}")
        if not profile.classification or not profile.name_sets:
            raise ValueError(f"Incomplete species definition: {species_id}")
        if Path(profile.portrait).is_absolute() or ".." in Path(profile.portrait).parts:
            raise ValueError(f"Unsafe portrait path for species {species_id}")
        if any(not given or not family for given, family in profile.name_sets.values()):
            raise ValueError(f"Empty name pool for species {species_id}")
        profiles[species_id] = profile
    if not profiles:
        raise ValueError("Species catalog must contain at least one species")
    return profiles
