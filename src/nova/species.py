"""Data-driven species profiles and deterministic name generation."""

from dataclasses import dataclass
import json
from pathlib import Path
import random
from typing import Any


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
    synthetic: bool = False
    derived_from: str | None = None

    @property
    def name_cultures(self) -> tuple[str, ...]:
        return ("all", *sorted(culture for culture in self.name_sets if culture != "all"))

    def _name_pools(
        self,
        culture: str,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        requested = culture.casefold().strip().replace("\\", "/").strip("/")
        if not requested or requested == "all":
            selected = tuple(self.name_sets.values())
        else:
            roots = [
                name
                for name in self.name_sets
                if name == requested
                or name.endswith(f"/{requested}")
            ]
            if not roots:
                raise ValueError(f"Unknown {self.name} naming culture: {culture}")
            descendants = [
                pools
                for name, pools in self.name_sets.items()
                if any(name.startswith(f"{root}/") for root in roots)
            ]
            deepest = max(root.count("/") for root in roots)
            selected = tuple(
                [
                    self.name_sets[root]
                    for root in roots
                    if root.count("/") == deepest
                ]
                + descendants
            )
        given = tuple(dict.fromkeys(name for first, _ in selected for name in first))
        family = tuple(dict.fromkeys(name for _, second in selected for name in second))
        return given, family

    def generate_name(self, seed: int, culture: str = "all") -> str:
        given, family = self._name_pools(culture)
        if not given or not family:
            raise ValueError(f"{self.name} has an empty name pool")
        rng = random.Random(seed)
        return f"{rng.choice(given)} {rng.choice(family)}"

    def is_compatible_with(self, other: "SpeciesProfile") -> bool:
        return bool(set(self.preferred_climates) & set(other.preferred_climates))

    def to_dict(self) -> dict[str, object]:
        return {
            "species_id": self.species_id,
            "name": self.name,
            "classification": list(self.classification),
            "lifespan_years": self.lifespan_years,
            "annual_growth_rate": self.annual_growth_rate,
            "preferred_climates": list(self.preferred_climates),
            "needs": list(self.needs),
            "traits": list(self.traits),
            "portrait": self.portrait,
            "name_sets": {
                culture: {"given": list(given), "family": list(family)}
                for culture, (given, family) in self.name_sets.items()
            },
            "synthetic": self.synthetic,
            "derived_from": self.derived_from,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SpeciesProfile":
        name_sets = {
            str(culture).casefold(): (
                tuple(map(str, names["given"])),
                tuple(map(str, names["family"])),
            )
            for culture, names in data["name_sets"].items()
        }
        return cls(
            species_id=str(data["species_id"]),
            name=str(data["name"]),
            classification=tuple(map(str, data["classification"])),
            lifespan_years=int(data["lifespan_years"]),
            annual_growth_rate=float(data["annual_growth_rate"]),
            preferred_climates=tuple(map(str, data["preferred_climates"])),
            needs=tuple(map(str, data["needs"])),
            traits=tuple(map(str, data["traits"])),
            portrait=str(data["portrait"]),
            name_sets=name_sets,
            synthetic=bool(data.get("synthetic", False)),
            derived_from=(
                str(data["derived_from"])
                if data.get("derived_from") is not None
                else None
            ),
        )


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
                synthetic=bool(entry.get("synthetic", False)),
                derived_from=(
                    str(entry["derived_from"])
                    if entry.get("derived_from") is not None
                    else None
                ),
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
        if not profile.preferred_climates or not profile.traits or not profile.needs:
            raise ValueError(f"Incomplete biology definition: {species_id}")
        if Path(profile.portrait).is_absolute() or ".." in Path(profile.portrait).parts:
            raise ValueError(f"Unsafe portrait path for species {species_id}")
        if any(not given or not family for given, family in profile.name_sets.values()):
            raise ValueError(f"Empty name pool for species {species_id}")
        profiles[species_id] = profile
    if not profiles:
        raise ValueError("Species catalog must contain at least one species")
    return profiles
