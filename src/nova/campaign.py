"""Playable campaign rules for the NOVA frontier scenario."""

from collections import deque
from dataclasses import asdict, dataclass, field
import logging
import math
from pathlib import Path

from .galaxy import (
    Galaxy,
    GalaxyGenerator,
    GalaxySettings,
    Nebula,
    StarSystem,
    SystemObject,
)
from .economy import GameContent, load_game_content
from .species import load_species_catalog


logger = logging.getLogger(__name__)


@dataclass
class Fleet:
    fleet_id: str
    name: str
    system_id: str
    ship_count: int = 3
    route: list[str] = field(default_factory=list)
    days_to_arrival: float = 0.0

    @property
    def destination_id(self) -> str | None:
        return self.route[-1] if self.route else None


@dataclass
class ColonyState:
    system_id: str
    planet_id: str
    species_id: str
    population_billions: float
    happiness: float = 0.75
    buildings: list[str] = field(default_factory=list)
    construction: str | None = None
    construction_days_remaining: float = 0.0


@dataclass
class AIEmpire:
    empire_id: str
    name: str
    species_id: str
    system_ids: list[str]
    next_expansion_day: float = 365.0


class Campaign:
    """Space-colonization campaign set in a seeded procedural galaxy."""

    COLONY_ALLOY_COST = 22
    COLONY_INFLUENCE_COST = 3
    SURVEY_SCIENCE_COST = 4
    GATEWAY_SCIENCE_COST = 12

    def __init__(
        self,
        seed: int = 2480,
        size: str = "medium",
        shape: str = "spiral",
        galaxy_name: str | None = None,
        player_species_id: str = "union-human",
        content_path: Path | None = None,
    ) -> None:
        self.content_path = content_path or Path(__file__).resolve().parents[2] / "content"
        self.species_catalog = load_species_catalog(
            self._content_file("species.json")
        )
        self.game_content: GameContent = load_game_content(
            self._content_file("gameplay.json")
        )
        if player_species_id not in self.species_catalog:
            raise ValueError(f"Unknown player species: {player_species_id}")
        self.player_species_id = player_species_id
        self.galaxy: Galaxy = GalaxyGenerator(
            GalaxySettings(
                seed=seed,
                size=size,
                shape=shape,
                galaxy_name=galaxy_name,
            )
        ).generate()
        self.systems = self.galaxy.systems
        self.routes = self.galaxy.routes
        self.fleets = [Fleet("frontier-survey-group", "Frontier Survey Group", "sol")]
        self.map_bookmarks: list[str] = []
        self.alloys = 50.0
        self.science = 18.0
        self.influence = 8.0
        self.volatiles = 4.0
        self.energy = 60.0
        self.food = 60.0
        self.research_points = 0.0
        self.active_technology: str | None = None
        self.research_progress = 0.0
        self.researched_technologies: set[str] = set()
        self.elapsed_days = 0.0
        self.gateway_studied = False
        self.colony_states: dict[str, ColonyState] = {}
        self.ai_empires = [
            AIEmpire("veyra", "Veyran Compact", "veyra", ["morrow"])
        ]
        self.log = [
            "2480.01  The frontier is open. Survey the unknown systems.",
            "2480.01  Union scouts report an ancient signal at Eidolon.",
        ]
        for system in self.systems:
            for planet in system.planets:
                if planet.colonized:
                    self._add_colony(
                        system,
                        planet,
                        self.player_species_id,
                        self._population_billions(planet.population),
                    )
                    planet.history.append(
                        f"{self.date_label}  Colony established under Union administration."
                    )
        rival = self.get_system("morrow")
        rival_world = next(
            (planet for planet in rival.planets if planet.habitable),
            None,
        )
        if rival_world is not None:
            rival.owner = "Veyran Compact"
            rival.colonized = True
            rival_world.owner = "Veyran Compact"
            rival_world.colonized = True
            rival_world.population = "1.1B"
            self._add_colony(rival, rival_world, "veyra", 1.1)
            self.ai_empires[0].system_ids = [rival.system_id]
        self._refresh_population_labels()

    def _content_file(self, name: str) -> Path:
        content_file = self.content_path / name
        if content_file.is_file():
            return content_file
        builtin_file = Path(__file__).resolve().parents[2] / "content" / name
        if content_file.resolve() != builtin_file.resolve():
            logger.info(
                "No %s in %s; using built-in game content",
                name,
                self.content_path,
            )
        return builtin_file

    @property
    def colonies(self) -> int:
        return sum(system.owner == "Union" for system in self.systems)

    @property
    def player_population_billions(self) -> float:
        return sum(
            colony.population_billions
            for colony in self.colony_states.values()
            if self.get_system(colony.system_id).owner == "Union"
        )

    @property
    def player_colonies(self) -> list[ColonyState]:
        return [
            colony
            for colony in self.colony_states.values()
            if self.get_system(colony.system_id).owner == "Union"
        ]

    @staticmethod
    def colony_key(system_id: str, planet_id: str) -> str:
        return f"{system_id}/{planet_id}"

    @property
    def objective_complete(self) -> bool:
        return self.gateway_studied and self.colonies >= 3

    @property
    def objective(self) -> str:
        if self.objective_complete:
            return "Frontier secured. The gateway is yours to command."
        colonies_needed = max(0, 3 - self.colonies)
        colony_goal = (
            f"{colonies_needed} frontier colony"
            if colonies_needed == 1
            else f"{colonies_needed} frontier colonies"
        )
        if self.gateway_studied:
            return f"Establish {colony_goal}."
        return f"Survey Eidolon, study the gateway, and establish {colony_goal}."

    @property
    def date_label(self) -> str:
        year = 2480 + int(self.elapsed_days // 365)
        day = int(self.elapsed_days % 365) + 1
        return f"{year}.{day:03d}"

    def get_system(self, system_id: str) -> StarSystem:
        for system in self.systems:
            if system.system_id == system_id:
                return system
        raise KeyError(f"Unknown star system: {system_id}")

    def get_object(self, system_id: str, object_id: str) -> SystemObject:
        system = self.get_system(system_id)
        for system_object in system.objects:
            if system_object.object_id == object_id:
                return system_object
        raise KeyError(f"Unknown object in {system.name}: {object_id}")

    def action_label(self, system_id: str) -> str:
        system = self.get_system(system_id)
        if not system.surveyed:
            return f"Survey ({self.SURVEY_SCIENCE_COST} science)"
        if system.gateway and not self.gateway_studied:
            return f"Study gateway ({self.GATEWAY_SCIENCE_COST} science)"
        if system.habitable and not system.colonized:
            return f"Found colony ({self.COLONY_ALLOY_COST} alloys)"
        if system.colonized:
            return "Colony established"
        return "No further action"

    def perform_action(self, system_id: str) -> str:
        system = self.get_system(system_id)
        if not system.surveyed:
            return self._survey(system)
        if system.gateway and not self.gateway_studied:
            return self._study_gateway(system)
        if system.habitable and not system.colonized:
            return self._colonize(system)
        raise ValueError(f"No available action for {system.name}")

    def object_action_label(self, system_id: str, object_id: str) -> str:
        system_object = self.get_object(system_id, object_id)
        if not system_object.surveyed:
            return f"Survey {system_object.name} ({self.SURVEY_SCIENCE_COST} science)"
        if system_object.gateway and not self.gateway_studied:
            return f"Study gateway ({self.GATEWAY_SCIENCE_COST} science)"
        if system_object.gateway:
            return "Gateway secured"
        if system_object.anomaly_resolved:
            return "Anomaly resolved"
        if system_object.anomaly:
            return f"Investigate anomaly (5 science)"
        if system_object.habitable and not system_object.colonized:
            return f"Found colony ({self.COLONY_ALLOY_COST} alloys)"
        if system_object.colonized:
            return "Colony established"
        return "Object surveyed"

    def perform_object_action(self, system_id: str, object_id: str) -> str:
        system = self.get_system(system_id)
        system_object = self.get_object(system_id, object_id)
        if not system_object.surveyed:
            if self.science < self.SURVEY_SCIENCE_COST:
                raise ValueError("Not enough science to survey this object")
            self.science -= self.SURVEY_SCIENCE_COST
            system_object.surveyed = True
            system.surveyed = True
            if system_object.is_planet or system_object.kind == "Moon":
                self._record_planet_history(
                    system_object,
                    "Survey completed; planetary observations added to the archive.",
                )
            if system_object.anomaly:
                system_object.world_type = "Anomaly detected"
                message = f"Anomaly detected at {system_object.name} in {system.name}. A special project is ready."
            else:
                self.science += 3
                self.alloys += 2
                recovered = self._recover_deposits(system_object)
                message = (
                    f"Survey complete: {system_object.name} in {system.name} - "
                    f"{system_object.description}{recovered}"
                )
            self._record(message)
            return message
        if system_object.gateway and not self.gateway_studied:
            return self._study_gateway(system)
        if system_object.gateway:
            raise ValueError("The gateway is already under Union control")
        if system_object.anomaly_resolved:
            raise ValueError(f"{system_object.name} has already been investigated")
        if system_object.anomaly:
            if self.science < 5:
                raise ValueError("Not enough science to investigate this anomaly")
            self.science -= 5
            system_object.anomaly_resolved = True
            self.science += 14
            self.influence += 1
            recovered = self._recover_deposits(system_object)
            message = (
                f"Anomaly resolved: {system_object.name} in {system.name}. "
                f"The signal contained valuable research.{recovered}"
            )
            self._record(message)
            return message
        if system_object.habitable and not system_object.colonized:
            return self._colonize(system, system_object)
        raise ValueError(f"No available action for {system_object.name}")

    def building_options(self) -> tuple[str, ...]:
        return tuple(
            building_id
            for building_id, definition in self.game_content.buildings.items()
            if set(definition.prerequisites).issubset(self.researched_technologies)
        )

    def available_technologies(self) -> tuple[str, ...]:
        return tuple(
            technology_id
            for technology_id, definition in self.game_content.technologies.items()
            if technology_id not in self.researched_technologies
            and set(definition.prerequisites).issubset(self.researched_technologies)
        )

    def get_colony(self, system_id: str, planet_id: str) -> ColonyState:
        key = self.colony_key(system_id, planet_id)
        try:
            return self.colony_states[key]
        except KeyError as error:
            raise KeyError(f"No colony on {system_id}/{planet_id}") from error

    def build_building(
        self,
        system_id: str,
        planet_id: str,
        building_id: str,
    ) -> str:
        colony = self.get_colony(system_id, planet_id)
        system = self.get_system(system_id)
        if system.owner != "Union":
            raise ValueError("Buildings can only be constructed in Union colonies")
        if colony.construction is not None:
            raise ValueError("This colony already has construction underway")
        try:
            definition = self.game_content.buildings[building_id]
        except KeyError as error:
            raise ValueError(f"Unknown building: {building_id}") from error
        if not set(definition.prerequisites).issubset(self.researched_technologies):
            raise ValueError(f"Required technology is not researched for {definition.name}")
        if self.alloys < definition.cost_alloys:
            raise ValueError(f"Not enough alloys to construct {definition.name}")
        self.alloys -= definition.cost_alloys
        colony.construction = building_id
        colony.construction_days_remaining = definition.days_to_build
        message = (
            f"Construction started: {definition.name} on "
            f"{self.get_object(system_id, planet_id).name}."
        )
        self._record(message)
        return message

    def start_research(self, technology_id: str) -> str:
        if self.active_technology is not None:
            raise ValueError("A research project is already active")
        try:
            definition = self.game_content.technologies[technology_id]
        except KeyError as error:
            raise ValueError(f"Unknown technology: {technology_id}") from error
        if technology_id in self.researched_technologies:
            raise ValueError(f"{definition.name} is already researched")
        if not set(definition.prerequisites).issubset(self.researched_technologies):
            raise ValueError(f"Research prerequisites are incomplete for {definition.name}")
        self.active_technology = technology_id
        self.research_progress = 0.0
        self._record(f"Research begun: {definition.name}.")
        return f"Research begun: {definition.name}."

    def create_fleet(self, name: str = "Frontier Squadron") -> Fleet:
        cost = 35.0
        if self.alloys < cost:
            raise ValueError("Not enough alloys to commission a fleet")
        self.alloys -= cost
        fleet = Fleet(
            fleet_id=f"union-fleet-{len(self.fleets) + 1}",
            name=name,
            system_id="sol",
        )
        self.fleets.append(fleet)
        self._record(f"Fleet commissioned: {fleet.name} at Sol.")
        return fleet

    def move_fleet(self, fleet_id: str, target_system_id: str) -> str:
        fleet = next((item for item in self.fleets if item.fleet_id == fleet_id), None)
        if fleet is None:
            raise KeyError(f"Unknown fleet: {fleet_id}")
        self.get_system(target_system_id)
        if fleet.system_id == target_system_id:
            raise ValueError("Fleet is already at that system")
        if fleet.route:
            raise ValueError(f"{fleet.name} is already in transit")
        route = self._find_route(fleet.system_id, target_system_id)
        if not route:
            raise ValueError(f"No navigable route to {target_system_id}")
        fleet.route = route
        fleet.days_to_arrival = self._jump_duration(fleet.system_id, route[0])
        message = f"{fleet.name} is en route to {target_system_id}."
        self._record(message)
        return message

    def _find_route(self, start: str, goal: str) -> list[str]:
        neighbors: dict[str, list[str]] = {}
        for first, second in self.routes:
            neighbors.setdefault(first, []).append(second)
            neighbors.setdefault(second, []).append(first)
        queue = deque([(start, [])])
        visited = {start}
        while queue:
            current, path = queue.popleft()
            if current == goal:
                return path
            for neighbor in sorted(neighbors.get(current, [])):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, [*path, neighbor]))
        return []

    def _jump_duration(self, first_id: str, second_id: str) -> float:
        first = self.get_system(first_id)
        second = self.get_system(second_id)
        distance = math.hypot(first.x - second.x, first.y - second.y)
        return max(1.0, distance * self.galaxy.diameter_light_years / 40.0)

    def fleet_position(self, fleet: Fleet) -> tuple[float, float]:
        current = self.get_system(fleet.system_id)
        if not fleet.route:
            return current.x, current.y
        destination = self.get_system(fleet.route[0])
        duration = self._jump_duration(current.system_id, destination.system_id)
        progress = min(1.0, max(0.0, 1.0 - fleet.days_to_arrival / duration))
        return (
            current.x + (destination.x - current.x) * progress,
            current.y + (destination.y - current.y) * progress,
        )

    def advance(self, delta: float) -> None:
        if delta < 0:
            raise ValueError("Campaign delta cannot be negative")
        if delta == 0:
            return
        self.elapsed_days += delta
        settled_colonies = max(0, self.colonies - 1)
        self.alloys += delta * (0.12 + settled_colonies * 0.08)
        self.science += delta * (0.04 + settled_colonies * 0.035)
        self.volatiles += delta * (0.025 + settled_colonies * 0.02)
        production = {
            "energy": 0.0,
            "food": 0.0,
            "alloys": 0.0,
            "science": 0.0,
            "volatiles": 0.0,
        }
        energy_upkeep = 0.0
        research_rate = 0.025
        for colony in self.colony_states.values():
            system = self.get_system(colony.system_id)
            if system.owner == "Union":
                population = colony.population_billions
                production["food"] += 0.28
                production["energy"] += 0.3
                production["food"] -= population * 0.025
                production["energy"] -= population * 0.025
                species = self.species_catalog[colony.species_id]
                planet = self.get_object(colony.system_id, colony.planet_id)
                climate_factor = (
                    1.0 if planet.climate in species.preferred_climates else 0.65
                )
                room = max(
                    0.0,
                    planet.population_capacity_billions - population,
                )
                food_factor = 1.0 if self.food > 0 else 0.25
                colony.population_billions += min(
                    room,
                    population
                    * species.annual_growth_rate
                    * climate_factor
                    * food_factor
                    * delta
                    / 365.0,
                )
                colony.happiness = min(
                    1.0,
                    max(
                        0.0,
                        0.75
                        + (0.08 if self.food > 0 else -0.3)
                        + (0.06 if climate_factor == 1.0 else -0.08),
                    ),
                )
            for building_id in colony.buildings:
                definition = self.game_content.buildings[building_id]
                energy_upkeep += definition.energy_upkeep
                for resource, amount in definition.production.items():
                    if resource in production:
                        production[resource] += amount
                    elif resource == "research":
                        research_rate += amount
            if colony.construction is not None:
                colony.construction_days_remaining -= delta
                if colony.construction_days_remaining <= 0:
                    building_id = colony.construction
                    colony.buildings.append(building_id)
                    colony.construction = None
                    colony.construction_days_remaining = 0.0
                    building = self.game_content.buildings[building_id]
                    self._record(
                        f"Construction complete: {building.name} on "
                        f"{self.get_object(colony.system_id, colony.planet_id).name}."
                    )

        self.food = max(0.0, min(9999.0, self.food + production["food"] * delta))
        self.energy = max(
            0.0,
            min(9999.0, self.energy + (production["energy"] - energy_upkeep) * delta),
        )
        self.alloys += production["alloys"] * delta
        self.science += production["science"] * delta
        self.volatiles += production["volatiles"] * delta
        self.research_points += research_rate * delta
        self._advance_research()
        self._advance_fleets(delta)
        self._advance_ai()
        self._refresh_population_labels()

    def _advance_research(self) -> None:
        if self.active_technology is None:
            return
        technology = self.game_content.technologies[self.active_technology]
        self.research_progress += self.research_points
        self.research_points = 0.0
        if self.research_progress >= technology.cost:
            self.researched_technologies.add(technology.technology_id)
            self._record(f"Technology researched: {technology.name}.")
            self.active_technology = None
            self.research_progress = 0.0

    def _advance_fleets(self, delta: float) -> None:
        for fleet in self.fleets:
            remaining = delta
            while fleet.route and remaining >= fleet.days_to_arrival:
                remaining -= fleet.days_to_arrival
                previous = fleet.system_id
                fleet.system_id = fleet.route.pop(0)
                self._record(f"{fleet.name} arrived in {self.get_system(fleet.system_id).name}.")
                if fleet.route:
                    fleet.days_to_arrival = self._jump_duration(previous, fleet.system_id)
                else:
                    fleet.days_to_arrival = 0.0
            if fleet.route:
                fleet.days_to_arrival = max(0.0, fleet.days_to_arrival - remaining)

    def _advance_ai(self) -> None:
        for empire in self.ai_empires:
            while self.elapsed_days >= empire.next_expansion_day:
                candidates = [
                    (system, planet)
                    for system in self.systems
                    if system.owner is None
                    for planet in system.planets
                    if planet.habitable and not planet.colonized
                ]
                if candidates:
                    system, planet = min(
                        candidates,
                        key=lambda pair: (
                            min(
                                math.hypot(
                                    pair[0].x - self.get_system(owned_id).x,
                                    pair[0].y - self.get_system(owned_id).y,
                                )
                                for owned_id in empire.system_ids
                            ),
                            pair[0].system_id,
                        ),
                    )
                    system.owner = empire.name
                    system.colonized = True
                    system.surveyed = True
                    planet.owner = empire.name
                    planet.colonized = True
                    planet.surveyed = True
                    planet.population = "0.8B"
                    empire.system_ids.append(system.system_id)
                    self._add_colony(system, planet, empire.species_id, 0.8)
                    self._record(f"{empire.name} founded a colony at {system.name}.")
                empire.next_expansion_day += 365.0

    def _add_colony(
        self,
        system: StarSystem,
        planet: SystemObject,
        species_id: str,
        population: float,
    ) -> None:
        self.colony_states[self.colony_key(system.system_id, planet.object_id)] = (
            ColonyState(system.system_id, planet.object_id, species_id, population)
        )

    @staticmethod
    def _population_billions(population: str) -> float:
        if population.endswith("B"):
            return float(population[:-1])
        if population.endswith("M"):
            return float(population[:-1]) / 1000.0
        return 0.0

    def _refresh_population_labels(self) -> None:
        system_populations: dict[str, float] = {}
        for colony in self.colony_states.values():
            population = colony.population_billions
            label = self._format_population(population)
            self.get_object(colony.system_id, colony.planet_id).population = label
            system_populations[colony.system_id] = (
                system_populations.get(colony.system_id, 0.0) + population
            )
        for system_id, population in system_populations.items():
            system = self.get_system(system_id)
            system.population = self._format_population(population)

    @staticmethod
    def _format_population(population_billions: float) -> str:
        if population_billions < 1:
            return f"{round(population_billions * 1000):,}M"
        if population_billions < 10:
            return f"{population_billions:.2f}B"
        return f"{population_billions:.1f}B"

    def to_dict(self) -> dict[str, object]:
        """Return a complete JSON-compatible snapshot of the campaign."""
        return {
            "schema_version": 1,
            "galaxy": asdict(self.galaxy),
            "player_species_id": self.player_species_id,
            "elapsed_days": self.elapsed_days,
            "alloys": self.alloys,
            "science": self.science,
            "influence": self.influence,
            "volatiles": self.volatiles,
            "energy": self.energy,
            "food": self.food,
            "research_points": self.research_points,
            "active_technology": self.active_technology,
            "research_progress": self.research_progress,
            "researched_technologies": sorted(self.researched_technologies),
            "gateway_studied": self.gateway_studied,
            "map_bookmarks": list(self.map_bookmarks),
            "colonies": [asdict(colony) for colony in self.colony_states.values()],
            "fleets": [asdict(fleet) for fleet in self.fleets],
            "ai_empires": [asdict(empire) for empire in self.ai_empires],
            "log": list(self.log),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, object],
        content_path: Path | None = None,
    ) -> "Campaign":
        if data.get("schema_version") != 1:
            raise ValueError(f"Unsupported campaign version: {data.get('schema_version')}")
        galaxy_data = data.get("galaxy")
        if not isinstance(galaxy_data, dict):
            raise ValueError("Save is missing its galaxy")
        seed = int(galaxy_data["seed"])
        campaign = cls(
            seed=seed,
            size=str(galaxy_data["size"]),
            shape=str(galaxy_data["shape"]),
            galaxy_name=None,
            player_species_id=str(data["player_species_id"]),
            content_path=content_path,
        )
        try:
            systems = [
                StarSystem(
                    **{
                        **system_data,
                        "objects": [
                            SystemObject(**item)
                            for item in system_data["objects"]
                        ],
                    }
                )
                for system_data in galaxy_data["systems"]
            ]
            galaxy = Galaxy(
                name=str(galaxy_data["name"]),
                region_name=str(galaxy_data["region_name"]),
                shape=str(galaxy_data["shape"]),
                seed=seed,
                size=str(galaxy_data["size"]),
                diameter_light_years=int(galaxy_data["diameter_light_years"]),
                systems=systems,
                routes=tuple(tuple(route) for route in galaxy_data["routes"]),
                nebulae=tuple(Nebula(**nebula) for nebula in galaxy_data["nebulae"]),
            )
            colonies = [
                ColonyState(**colony_data)
                for colony_data in data["colonies"]
            ]
            fleets = [
                Fleet(**fleet_data)
                for fleet_data in data["fleets"]
            ]
            ai_empires = [
                AIEmpire(**empire_data)
                for empire_data in data["ai_empires"]
            ]
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Save contains invalid campaign data") from error

        system_ids = {system.system_id for system in systems}
        if len(system_ids) != len(systems):
            raise ValueError("Save contains duplicate star systems")
        object_ids = {
            cls.colony_key(system.system_id, item.object_id)
            for system in systems
            for item in system.objects
        }
        for colony in colonies:
            key = cls.colony_key(colony.system_id, colony.planet_id)
            if (
                key not in object_ids
                or colony.species_id not in campaign.species_catalog
                or not math.isfinite(colony.population_billions)
                or colony.population_billions < 0
                or not 0 <= colony.happiness <= 1
                or any(item not in campaign.game_content.buildings for item in colony.buildings)
                or (
                    colony.construction is not None
                    and colony.construction not in campaign.game_content.buildings
                )
                or colony.construction_days_remaining < 0
            ):
                raise ValueError("Save contains an invalid colony")
        route_edges = {
            tuple(sorted(route))
            for route in galaxy.routes
        }
        for fleet in fleets:
            route = [fleet.system_id, *fleet.route]
            if (
                fleet.system_id not in system_ids
                or fleet.ship_count <= 0
                or fleet.days_to_arrival < 0
                or not math.isfinite(fleet.days_to_arrival)
                or any(item not in system_ids for item in fleet.route)
                or any(
                    tuple(sorted((first, second))) not in route_edges
                    for first, second in zip(route, route[1:])
                )
            ):
                raise ValueError("Save contains an invalid fleet route")
        for empire in ai_empires:
            if (
                empire.species_id not in campaign.species_catalog
                or any(item not in system_ids for item in empire.system_ids)
                or len(set(empire.system_ids)) != len(empire.system_ids)
                or empire.next_expansion_day < 0
            ):
                raise ValueError("Save contains an invalid AI empire")
        numeric_state = (
            float(data["elapsed_days"]),
            float(data["alloys"]),
            float(data["science"]),
            float(data["influence"]),
            float(data["volatiles"]),
            float(data["energy"]),
            float(data["food"]),
            float(data["research_points"]),
            float(data["research_progress"]),
        )
        if any(not math.isfinite(value) or value < 0 for value in numeric_state):
            raise ValueError("Save contains invalid resource or simulation values")
        researched = set(data["researched_technologies"])
        if any(item not in campaign.game_content.technologies for item in researched):
            raise ValueError("Save references unknown researched technology")
        active_technology = data["active_technology"]
        if active_technology is not None and (
            active_technology not in campaign.game_content.technologies
            or active_technology in researched
        ):
            raise ValueError("Save references an invalid active technology")

        campaign.galaxy = galaxy
        campaign.systems = galaxy.systems
        campaign.routes = galaxy.routes
        campaign.elapsed_days = float(data["elapsed_days"])
        campaign.alloys = float(data["alloys"])
        campaign.science = float(data["science"])
        campaign.influence = float(data["influence"])
        campaign.volatiles = float(data["volatiles"])
        campaign.energy = float(data["energy"])
        campaign.food = float(data["food"])
        campaign.research_points = float(data["research_points"])
        campaign.active_technology = data["active_technology"]
        campaign.research_progress = float(data["research_progress"])
        campaign.researched_technologies = researched
        campaign.gateway_studied = bool(data["gateway_studied"])
        campaign.map_bookmarks = [
            item for item in data["map_bookmarks"] if item in system_ids
        ]
        campaign.colony_states = {
            campaign.colony_key(colony.system_id, colony.planet_id): colony
            for colony in colonies
        }
        campaign.fleets = fleets
        campaign.ai_empires = ai_empires
        campaign.log = list(data["log"])
        campaign._refresh_population_labels()
        return campaign

    def _survey(self, system: StarSystem) -> str:
        if self.science < self.SURVEY_SCIENCE_COST:
            raise ValueError("Not enough science to survey this system")
        self.science -= self.SURVEY_SCIENCE_COST
        self.science += 6
        self.alloys += 5
        system.surveyed = True
        message = (
            f"Survey complete: {system.name} - {system.world_type} identified. "
            "Survey teams recovered research and alloys."
        )
        self._record(message)
        return message

    def _colonize_object(self, system: StarSystem, target: SystemObject) -> str:
        if system.owner not in (None, "Union"):
            raise ValueError(f"{system.name} is controlled by {system.owner}")
        if self.alloys < self.COLONY_ALLOY_COST:
            raise ValueError("Not enough alloys to found a colony")
        if self.influence < self.COLONY_INFLUENCE_COST:
            raise ValueError("Not enough influence to found a colony")
        self.alloys -= self.COLONY_ALLOY_COST
        self.influence -= self.COLONY_INFLUENCE_COST
        target.colonized = True
        target.owner = "Union"
        target.population = "1.2B"
        system.colonized = True
        system.owner = "Union"
        system.population = target.population
        self._add_colony(system, target, self.player_species_id, 1.2)
        self._record_planet_history(
            target,
            "Colony founded; Union administration established.",
        )
        system.owner = "Union"
        message = (
            f"Colony founded: {system.name}. "
            "The new settlement will expand the Union's reach."
        )
        self._record(message)
        return message

    def _colonize(self, system: StarSystem, target: SystemObject | None = None) -> str:
        if target is None:
            target = next(
                (
                    obj
                    for obj in system.objects
                    if obj.habitable and not obj.colonized
                ),
                None,
            )
        if target is None:
            raise ValueError(f"{system.name} cannot support another colony")
        return self._colonize_object(system, target)

    def _study_gateway(self, system: StarSystem) -> str:
        if self.science < self.GATEWAY_SCIENCE_COST:
            raise ValueError("Not enough science to study the gateway")
        self.science -= self.GATEWAY_SCIENCE_COST
        self.gateway_studied = True
        self.alloys += 24
        self.influence += 2
        message = (
            f"Gateway decoded at {system.name}. "
            "Its dormant transit network is now under Union control."
        )
        self._record(message)
        return message

    def _record(self, message: str) -> None:
        self.log.append(f"{self.date_label}  {message}")
        self.log = self.log[-30:]

    def _record_planet_history(
        self,
        planet: SystemObject,
        event: str,
    ) -> None:
        planet.history.append(f"{self.date_label}  {event}")

    def _recover_deposits(self, system_object: SystemObject) -> str:
        deposits = system_object.resources
        alloys = deposits.get("Alloys", 0)
        science = deposits.get("Research", 0)
        volatiles = deposits.get("Volatiles", 0)
        self.alloys += alloys
        self.science += science
        self.volatiles += volatiles
        recovered = [
            f"{amount} {resource.lower()}"
            for resource, amount in (
                ("Alloys", alloys),
                ("Research", science),
                ("Volatiles", volatiles),
            )
            if amount
        ]
        return f" Recovered {', '.join(recovered)}." if recovered else ""
