"""Validated, data-driven building and technology definitions."""

from dataclasses import dataclass
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class BuildingDefinition:
    building_id: str
    name: str
    cost_alloys: float
    energy_upkeep: float
    jobs: int
    days_to_build: float
    production: dict[str, float]
    prerequisites: tuple[str, ...]


@dataclass(frozen=True)
class TechnologyDefinition:
    technology_id: str
    name: str
    category: str
    cost: float
    prerequisites: tuple[str, ...]
    description: str


@dataclass(frozen=True)
class GameContent:
    buildings: dict[str, BuildingDefinition]
    technologies: dict[str, TechnologyDefinition]


def load_game_content(path: Path) -> GameContent:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not load gameplay content: {path}") from error
    if not isinstance(data, dict):
        raise ValueError(f"Invalid gameplay content: {path}")
    try:
        technologies: dict[str, TechnologyDefinition] = {}
        for entry in data["technologies"]:
            technology_id = str(entry["id"])
            if not technology_id or technology_id in technologies:
                raise ValueError(f"Invalid or duplicate technology id: {technology_id}")
            technologies[technology_id] = TechnologyDefinition(
                technology_id=technology_id,
                name=str(entry["name"]),
                category=str(entry["category"]),
                cost=float(entry["cost"]),
                prerequisites=tuple(map(str, entry["prerequisites"])),
                description=str(entry["description"]),
            )
        buildings: dict[str, BuildingDefinition] = {}
        for entry in data["buildings"]:
            building_id = str(entry["id"])
            if not building_id or building_id in buildings:
                raise ValueError(f"Invalid or duplicate building id: {building_id}")
            buildings[building_id] = BuildingDefinition(
                building_id=building_id,
                name=str(entry["name"]),
                cost_alloys=float(entry["cost_alloys"]),
                energy_upkeep=float(entry["energy_upkeep"]),
                jobs=int(entry["jobs"]),
                days_to_build=float(entry["days_to_build"]),
                production={
                    str(resource): float(amount)
                    for resource, amount in entry["production"].items()
                },
                prerequisites=tuple(map(str, entry["prerequisites"])),
            )
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ValueError(f"Invalid gameplay definition in {path}: {error}") from error
    if not buildings or not technologies:
        raise ValueError("Gameplay content needs buildings and technologies")
    if any(
        not math.isfinite(item.cost_alloys)
        or item.cost_alloys < 0
        or not math.isfinite(item.energy_upkeep)
        or item.energy_upkeep < 0
        or item.jobs < 0
        or not math.isfinite(item.days_to_build)
        or item.days_to_build <= 0
        or any(
            not math.isfinite(amount) or amount < 0
            for amount in item.production.values()
        )
        for item in buildings.values()
    ):
        raise ValueError(
            "Building costs, upkeep, jobs, and production must be valid; "
            "construction duration must be positive"
        )
    if any(
        not math.isfinite(item.cost) or item.cost < 0
        for item in technologies.values()
    ):
        raise ValueError("Technology costs must be nonnegative")
    for building in buildings.values():
        if any(technology not in technologies for technology in building.prerequisites):
            raise ValueError(f"Unknown technology requirement for {building.name}")
    for technology in technologies.values():
        if any(required not in technologies for required in technology.prerequisites):
            raise ValueError(f"Unknown prerequisite for {technology.name}")
    return GameContent(buildings, technologies)
