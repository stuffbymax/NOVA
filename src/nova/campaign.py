"""Playable campaign rules for the NOVA frontier scenario."""

from collections import deque
from dataclasses import asdict, dataclass, field, replace
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
from .species import SpeciesProfile, load_species_catalog


logger = logging.getLogger(__name__)


@dataclass
class Fleet:
    fleet_id: str
    name: str
    system_id: str
    ship_count: int = 3
    route: list[str] = field(default_factory=list)
    days_to_arrival: float = 0.0
    owner_id: str = "union"

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
    evolution_progress: float = 0.0


@dataclass
class AIEmpire:
    empire_id: str
    name: str
    species_id: str
    system_ids: list[str]
    next_expansion_day: float = 365.0


@dataclass
class DiplomaticRelation:
    empire_id: str
    opinion: int = -5
    trust: int = 0
    first_contact: bool = False
    treaties: list[str] = field(default_factory=list)
    at_war: bool = False
    war_started_day: float | None = None
    last_envoy_day: float = -365.0


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
        name_culture: str = "all",
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
        player_species = self.species_catalog[player_species_id]
        player_species.generate_name(seed, name_culture)
        self.name_culture = name_culture.casefold().strip().replace("\\", "/").strip("/")
        self.leader_name = player_species.generate_name(seed, self.name_culture)
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
        self.species_rights = {
            species_id: "citizen" if species_id == player_species_id else "resident"
            for species_id in self.species_catalog
        }
        self.ai_fleets = [
            Fleet(
                "veyra-defense",
                "Veyran Defense Fleet",
                "morrow",
                ship_count=3,
                owner_id="veyra",
            )
        ]
        self.diplomacy = {
            empire.empire_id: DiplomaticRelation(empire.empire_id)
            for empire in self.ai_empires
        }
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

    @property
    def all_fleets(self) -> list[Fleet]:
        return [*self.fleets, *self.ai_fleets]

    def get_empire(self, empire_id: str) -> AIEmpire:
        for empire in self.ai_empires:
            if empire.empire_id == empire_id:
                return empire
        raise KeyError(f"Unknown empire: {empire_id}")

    def get_relation(self, empire_id: str) -> DiplomaticRelation:
        try:
            return self.diplomacy[empire_id]
        except KeyError as error:
            raise KeyError(f"Unknown diplomatic relationship: {empire_id}") from error

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
            first_contact = self._establish_contacts_in_system(system)
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
            if first_contact:
                message += f" {first_contact}"
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

    def set_species_rights(self, species_id: str, rights: str) -> str:
        if species_id not in self.species_catalog:
            raise ValueError(f"Unknown species: {species_id}")
        if rights not in {"citizen", "resident", "restricted"}:
            raise ValueError(f"Unknown species rights: {rights}")
        self.species_rights[species_id] = rights
        message = f"Species rights changed: {self.species_catalog[species_id].name} now has {rights} status."
        self._record(message)
        return message

    def migrate_population(
        self,
        source_system_id: str,
        source_planet_id: str,
        target_system_id: str,
        target_planet_id: str,
    ) -> str:
        source = self.get_colony(source_system_id, source_planet_id)
        target = self.get_colony(target_system_id, target_planet_id)
        source_system = self.get_system(source_system_id)
        target_system = self.get_system(target_system_id)
        if source_system.owner != "Union" or target_system.owner != "Union":
            raise ValueError("Migration is limited to Union colonies")
        if source is target:
            raise ValueError("Choose a different destination colony")
        if source.species_id != target.species_id:
            raise ValueError("Migration requires the same species at both colonies")
        if self.species_rights.get(source.species_id) == "restricted":
            raise ValueError("Restricted species cannot migrate")
        if self.influence < 1:
            raise ValueError("Not enough influence to organize migration")
        target_planet = self.get_object(target_system_id, target_planet_id)
        capacity = max(
            0.0,
            target_planet.population_capacity_billions
            - target.population_billions,
        )
        population = min(source.population_billions * 0.1, 0.1, capacity)
        if population <= 0:
            raise ValueError("No population can be moved to that colony")
        self.influence -= 1
        source.population_billions -= population
        target.population_billions += population
        self._refresh_population_labels()
        message = (
            f"Migration complete: {self._format_population(population)} moved "
            f"from {source_system.name} to {target_system.name}."
        )
        self._record(message)
        return message

    def engineer_species(
        self,
        system_id: str,
        planet_id: str,
        modification: str,
    ) -> str:
        colony = self.get_colony(system_id, planet_id)
        if self.get_system(system_id).owner != "Union":
            raise ValueError("Genetic engineering is limited to Union colonies")
        if "xeno-biology" not in self.researched_technologies:
            raise ValueError("Research Xenobiology before genetic engineering")
        parent = self.species_catalog[colony.species_id]
        planet = self.get_object(system_id, planet_id)
        if modification == "climate-adaptation":
            if planet.climate in parent.preferred_climates:
                raise ValueError("This species is already adapted to the local climate")
            changes = {
                "preferred_climates": (*parent.preferred_climates, planet.climate),
                "traits": (*parent.traits, f"Adapted to {planet.climate}"),
            }
        elif modification == "enhanced-growth":
            if parent.annual_growth_rate >= 0.05:
                raise ValueError("This species is already at its growth limit")
            changes = {
                "annual_growth_rate": min(0.05, parent.annual_growth_rate + 0.005),
                "traits": (*parent.traits, "Enhanced reproduction"),
            }
        elif modification == "extended-lifespan":
            changes = {
                "lifespan_years": parent.lifespan_years + 25,
                "traits": (*parent.traits, "Extended lifespan"),
            }
        else:
            raise ValueError(f"Unknown genetic modification: {modification}")
        if self.science < 15 or self.influence < 3:
            raise ValueError("Genetic engineering requires 15 science and 3 influence")
        self.science -= 15
        self.influence -= 3
        engineered = self._derive_species(
            parent,
            modification,
            changes,
        )
        colony.species_id = engineered.species_id
        colony.evolution_progress = 0.0
        self.species_rights[engineered.species_id] = self.species_rights.get(
            parent.species_id,
            "citizen",
        )
        message = f"Genetic engineering complete: {engineered.name} established on {planet.name}."
        self._record(message)
        return message

    def synthesize_species(self, system_id: str, planet_id: str) -> str:
        colony = self.get_colony(system_id, planet_id)
        if self.get_system(system_id).owner != "Union":
            raise ValueError("Synthetic conversion is limited to Union colonies")
        if "xeno-biology" not in self.researched_technologies:
            raise ValueError("Research Xenobiology before synthetic conversion")
        if self.species_catalog[colony.species_id].synthetic:
            raise ValueError("This colony is already synthetic")
        if self.science < 30 or self.influence < 5:
            raise ValueError("Synthetic conversion requires 30 science and 5 influence")
        self.science -= 30
        self.influence -= 5
        parent = self.species_catalog[colony.species_id]
        synthetic = self._derive_species(
            parent,
            "synthetic",
            {
                "name": f"{parent.name} Synthetic",
                "classification": (*parent.classification, "Synthetic"),
                "lifespan_years": 5000,
                "annual_growth_rate": 0.004,
                "preferred_climates": (
                    "Temperate",
                    "Oceanic",
                    "Tropical",
                    "Arid",
                    "Polar",
                    "Volcanic",
                    "Toxic",
                    "Airless",
                    "Mixed",
                    "Deep atmosphere",
                ),
                "needs": ("Energy", "Minerals", "Maintenance"),
                "traits": ("Synthetic", "Modular chassis"),
                "portrait": "species/synthetic.svg",
                "synthetic": True,
            },
        )
        colony.species_id = synthetic.species_id
        colony.evolution_progress = 0.0
        self.species_rights[synthetic.species_id] = "citizen"
        message = f"Synthetic ascension complete: {synthetic.name} now inhabits {self.get_object(system_id, planet_id).name}."
        self._record(message)
        return message

    def _derive_species(
        self,
        parent: SpeciesProfile,
        suffix: str,
        changes: dict[str, object],
    ) -> SpeciesProfile:
        species_id = f"{parent.species_id}-{suffix}"
        if species_id in self.species_catalog:
            species_id = f"{species_id}-{len(self.species_catalog)}"
        species = replace(
            parent,
            species_id=species_id,
            name=str(changes.pop("name", f"{parent.name} {suffix.replace('-', ' ').title()}")),
            derived_from=parent.species_id,
            **changes,
        )
        self.species_catalog[species_id] = species
        return species

    def _evolve_colony(self, colony: ColonyState, planet: SystemObject) -> None:
        parent = self.species_catalog[colony.species_id]
        evolved = self._derive_species(
            parent,
            f"evolved-{planet.climate.casefold().replace(' ', '-')}",
            {
                "name": f"{parent.name} (Adapted)",
                "preferred_climates": (*parent.preferred_climates, planet.climate),
                "traits": (*parent.traits, f"Natural {planet.climate} adaptation"),
            },
        )
        self.species_rights[evolved.species_id] = self.species_rights.get(
            parent.species_id,
            "citizen",
        )
        colony.species_id = evolved.species_id
        colony.evolution_progress = 0.0
        self._record(
            f"Species evolution: {evolved.name} adapted to {planet.climate} conditions on {planet.name}."
        )

    def establish_first_contact(self, empire_id: str) -> str:
        empire = self.get_empire(empire_id)
        relation = self.get_relation(empire_id)
        if relation.first_contact:
            raise ValueError(f"First contact with {empire.name} is already established")
        if not any(self.get_system(system_id).surveyed for system_id in empire.system_ids):
            raise ValueError(f"Survey a {empire.name} system to establish first contact")
        relation.first_contact = True
        relation.opinion = 0
        message = f"First contact established with the {empire.name}."
        self._record(message)
        return message

    def _establish_contacts_in_system(self, system: StarSystem) -> str:
        for empire in self.ai_empires:
            if system.system_id in empire.system_ids:
                relation = self.get_relation(empire.empire_id)
                if not relation.first_contact:
                    return self.establish_first_contact(empire.empire_id)
        return ""

    def send_envoy(self, empire_id: str) -> str:
        empire = self.get_empire(empire_id)
        relation = self.get_relation(empire_id)
        self._require_contact(empire, relation)
        if self.elapsed_days - relation.last_envoy_day < 365:
            raise ValueError("An envoy can improve relations once per year")
        if relation.at_war:
            raise ValueError("Envoys cannot improve relations during a war")
        if self.influence < 1:
            raise ValueError("Not enough influence to send an envoy")
        self.influence -= 1
        relation.last_envoy_day = self.elapsed_days
        relation.opinion = min(100, relation.opinion + 15)
        relation.trust = min(100, relation.trust + 5)
        message = (
            f"Envoy mission improved relations with the {empire.name} "
            f"(opinion {relation.opinion:+d})."
        )
        self._record(message)
        return message

    def propose_treaty(self, empire_id: str, treaty_id: str) -> str:
        empire = self.get_empire(empire_id)
        relation = self.get_relation(empire_id)
        self._require_contact(empire, relation)
        if relation.at_war:
            raise ValueError("A treaty cannot be proposed during a war")
        requirements = {
            "non_aggression": (1, -10, ()),
            "trade": (2, 5, ()),
            "research": (2, 10, ()),
            "defensive_alliance": (3, 35, ("non_aggression",)),
        }
        try:
            cost, minimum_opinion, prerequisites = requirements[treaty_id]
        except KeyError as error:
            raise ValueError(f"Unknown diplomatic treaty: {treaty_id}") from error
        if treaty_id in relation.treaties:
            raise ValueError("This treaty is already active")
        if not set(prerequisites).issubset(relation.treaties):
            raise ValueError("A non-aggression pact is required for a defensive alliance")
        if self.influence < cost:
            raise ValueError("Not enough influence to propose this treaty")
        self.influence -= cost
        treaty_names = {
            "non_aggression": "Non-aggression pact",
            "trade": "Trade agreement",
            "research": "Research agreement",
            "defensive_alliance": "Defensive alliance",
        }
        treaty_name = treaty_names[treaty_id]
        if relation.opinion < minimum_opinion:
            relation.opinion = max(-100, relation.opinion - 5)
            message = (
                f"The {empire.name} rejected the {treaty_name} "
                f"(opinion {relation.opinion:+d})."
            )
        else:
            relation.treaties.append(treaty_id)
            relation.opinion = min(100, relation.opinion + 5)
            relation.trust = min(100, relation.trust + 8)
            message = f"The {empire.name} accepted the {treaty_name}."
        self._record(message)
        return message

    def declare_war(self, empire_id: str) -> str:
        empire = self.get_empire(empire_id)
        relation = self.get_relation(empire_id)
        self._require_contact(empire, relation)
        if relation.at_war:
            raise ValueError(f"The Union is already at war with the {empire.name}")
        if relation.treaties:
            raise ValueError("Break active treaties before declaring war")
        if self.influence < 4:
            raise ValueError("Not enough influence to declare war")
        self.influence -= 4
        relation.at_war = True
        relation.war_started_day = self.elapsed_days
        relation.opinion = max(-100, relation.opinion - 50)
        message = f"The Union has declared war on the {empire.name}."
        self._record(message)
        return message

    def break_treaty(self, empire_id: str, treaty_id: str) -> str:
        empire = self.get_empire(empire_id)
        relation = self.get_relation(empire_id)
        self._require_contact(empire, relation)
        if treaty_id not in relation.treaties:
            raise ValueError("This treaty is not active")
        relation.treaties.remove(treaty_id)
        relation.opinion = max(-100, relation.opinion - 20)
        relation.trust = max(0, relation.trust - 15)
        treaty_name = treaty_id.replace("_", " ")
        message = f"The Union broke its {treaty_name} with the {empire.name}."
        self._record(message)
        return message

    def negotiate_peace(self, empire_id: str) -> str:
        empire = self.get_empire(empire_id)
        relation = self.get_relation(empire_id)
        self._require_contact(empire, relation)
        if not relation.at_war or relation.war_started_day is None:
            raise ValueError("There is no active war to resolve")
        held_systems = sum(
            self.get_system(system_id).owner == "Union"
            for system_id in empire.system_ids
        )
        war_days = self.elapsed_days - relation.war_started_day
        if held_systems == 0 and empire.system_ids and war_days < 180:
            self._record(f"The {empire.name} rejected a premature peace offer.")
            return f"The {empire.name} rejected the peace offer. Continue the war or wait."
        relation.at_war = False
        relation.war_started_day = None
        relation.treaties.clear()
        relation.opinion = max(-100, min(100, relation.opinion + 25))
        message = f"A ceasefire with the {empire.name} has ended hostilities."
        self._record(message)
        return message

    def _require_contact(
        self,
        empire: AIEmpire,
        relation: DiplomaticRelation,
    ) -> None:
        if not relation.first_contact:
            raise ValueError(f"First contact with the {empire.name} is required")

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
        destination_owner = self.get_system(target_system_id).owner
        if destination_owner not in (None, "Union"):
            empire = next(
                (item for item in self.ai_empires if item.name == destination_owner),
                None,
            )
            if empire is None or not self.get_relation(empire.empire_id).at_war:
                raise ValueError(f"Declare war before sending fleets into {destination_owner} territory")
        route = self._find_route(fleet.system_id, target_system_id, fleet.owner_id)
        if not route:
            raise ValueError(f"No navigable route to {target_system_id}")
        fleet.route = route
        fleet.days_to_arrival = self._jump_duration(fleet.system_id, route[0])
        message = f"{fleet.name} is en route to {target_system_id}."
        self._record(message)
        return message

    def _find_route(
        self,
        start: str,
        goal: str,
        owner_id: str = "union",
    ) -> list[str]:
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
                if not self._can_transit(owner_id, neighbor):
                    continue
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, [*path, neighbor]))
        return []

    def _can_transit(self, owner_id: str, system_id: str) -> bool:
        owner = "Union" if owner_id == "union" else self.get_empire(owner_id).name
        system = self.get_system(system_id)
        if system.owner is None or system.owner == owner:
            return True
        if system.owner == "Union":
            relation = self.diplomacy.get(owner_id)
            return bool(
                owner_id == "union"
                or (relation is not None and relation.at_war)
            )
        empire = next(
            (item for item in self.ai_empires if item.name == system.owner),
            None,
        )
        if empire is None:
            return False
        return (
            system.owner == empire.name
            and self.get_relation(empire.empire_id).at_war
        )

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
        trade_bonus = sum(
            "trade" in relation.treaties and relation.first_contact
            for relation in self.diplomacy.values()
        ) * 0.08
        research_bonus = sum(
            "research" in relation.treaties and relation.first_contact
            for relation in self.diplomacy.values()
        ) * 0.08
        production["energy"] += trade_bonus
        research_rate += research_bonus
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
                rights_factor = {
                    "citizen": 1.0,
                    "resident": 0.9,
                    "restricted": 0.65,
                }[self.species_rights.get(colony.species_id, "resident")]
                colony.population_billions += min(
                    room,
                    population
                    * species.annual_growth_rate
                    * climate_factor
                    * food_factor
                    * rights_factor
                    * delta
                    / 365.0,
                )
                if planet.climate not in species.preferred_climates:
                    colony.evolution_progress += delta / 365.0 * 0.1
                    if colony.evolution_progress >= 1.0:
                        colony.evolution_progress -= 1.0
                        self._evolve_colony(colony, planet)
                colony.happiness = min(
                    1.0,
                    max(
                        0.0,
                        0.75
                        + (0.08 if self.food > 0 else -0.3)
                        + (0.06 if climate_factor == 1.0 else -0.08)
                        + {
                            "citizen": 0.0,
                            "resident": -0.05,
                            "restricted": -0.2,
                        }[self.species_rights.get(colony.species_id, "resident")],
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
        for fleet in tuple(self.all_fleets):
            if fleet.ship_count <= 0:
                continue
            remaining = delta
            while fleet.route and remaining >= fleet.days_to_arrival:
                remaining -= fleet.days_to_arrival
                previous = fleet.system_id
                fleet.system_id = fleet.route.pop(0)
                system = self.get_system(fleet.system_id)
                self._record(f"{fleet.name} arrived in {system.name}.")
                if self._is_hostile_system(fleet.owner_id, system):
                    self._resolve_battle(fleet, system, previous)
                    if not fleet.route:
                        remaining = 0.0
                        break
                if fleet.route:
                    fleet.days_to_arrival = self._jump_duration(
                        fleet.system_id,
                        fleet.route[0],
                    )
                else:
                    fleet.days_to_arrival = 0.0
            if fleet.route:
                fleet.days_to_arrival = max(0.0, fleet.days_to_arrival - remaining)
        self.fleets = [fleet for fleet in self.fleets if fleet.ship_count > 0]
        self.ai_fleets = [fleet for fleet in self.ai_fleets if fleet.ship_count > 0]

    def _is_hostile_system(self, owner_id: str, system: StarSystem) -> bool:
        if owner_id == "union":
            empire = next(
                (entry for entry in self.ai_empires if entry.name == system.owner),
                None,
            )
            return bool(
                empire is not None
                and self.get_relation(empire.empire_id).at_war
            )
        empire = self.get_empire(owner_id)
        return (
            system.owner == "Union"
            and self.get_relation(empire.empire_id).at_war
        )

    def _resolve_battle(
        self,
        attacker: Fleet,
        system: StarSystem,
        previous_system_id: str,
    ) -> None:
        owner_id = attacker.owner_id
        defender_owner = "union" if system.owner == "Union" else next(
            (
                empire.empire_id
                for empire in self.ai_empires
                if empire.name == system.owner
            ),
            None,
        )
        if defender_owner is None:
            return
        relation_id = defender_owner if owner_id == "union" else owner_id
        relation = self.get_relation(relation_id)
        if not relation.at_war:
            return
        defenders = [
            fleet
            for fleet in self.all_fleets
            if fleet.owner_id == defender_owner
            and fleet.system_id == system.system_id
            and fleet.ship_count > 0
        ]
        defense_strength = sum(fleet.ship_count for fleet in defenders) + 1
        attack_strength = attacker.ship_count
        attacker_wins = attack_strength > defense_strength
        if attacker_wins:
            attacker_losses = min(
                attacker.ship_count - 1,
                max(1, math.ceil(defense_strength * 0.35)),
            )
            defender_losses = defense_strength
        else:
            attacker_losses = attacker.ship_count
            defender_losses = min(
                defense_strength - 1,
                max(1, math.ceil(attack_strength * 0.4)),
            )
        attacker.ship_count -= attacker_losses
        remaining_defender_losses = defender_losses
        for fleet in defenders:
            losses = min(fleet.ship_count, remaining_defender_losses)
            fleet.ship_count -= losses
            remaining_defender_losses -= losses
        result = "won" if attacker_wins else "lost"
        self._record(
            f"Battle of {system.name}: {attacker.name} {result}; "
            f"{attacker_losses} attacking and {defender_losses} defending ships lost."
        )
        if attacker_wins:
            self._capture_system(system, owner_id)
            relation.opinion = max(-100, relation.opinion - 10)
            return
        if attacker.ship_count:
            attacker.route = [previous_system_id]
            attacker.days_to_arrival = self._jump_duration(
                system.system_id,
                previous_system_id,
            )

    def _capture_system(self, system: StarSystem, owner_id: str) -> None:
        previous_owner = system.owner
        if owner_id == "union":
            system.owner = "Union"
            for planet in system.planets:
                if planet.colonized:
                    planet.owner = "Union"
            self._record(f"Union forces secured {system.name}.")
        else:
            empire = self.get_empire(owner_id)
            system.owner = empire.name
            for planet in system.planets:
                if planet.colonized:
                    planet.owner = empire.name
            self._record(f"{empire.name} forces secured {system.name}.")
        if previous_owner == "Union" and owner_id != "union":
            for colony in self.colony_states.values():
                if colony.system_id == system.system_id:
                    colony.happiness = max(0.0, colony.happiness - 0.25)
        if previous_owner not in (None, "Union"):
            previous_empire = next(
                (
                    empire
                    for empire in self.ai_empires
                    if empire.name == previous_owner
                ),
                None,
            )
            if previous_empire is not None and owner_id == "union":
                previous_empire.system_ids = [
                    item
                    for item in previous_empire.system_ids
                    if item != system.system_id
                ]
        if owner_id != "union":
            empire = self.get_empire(owner_id)
            if system.system_id not in empire.system_ids:
                empire.system_ids.append(system.system_id)

    def _advance_ai(self) -> None:
        for empire in self.ai_empires:
            relation = self.get_relation(empire.empire_id)
            if relation.at_war:
                for fleet in self.ai_fleets:
                    if fleet.owner_id != empire.empire_id or fleet.route:
                        continue
                    targets = [
                        system
                        for system in self.systems
                        if system.owner == "Union"
                    ]
                    if not targets:
                        continue
                    target = min(
                        targets,
                        key=lambda system: math.hypot(
                            system.x - self.get_system(fleet.system_id).x,
                            system.y - self.get_system(fleet.system_id).y,
                        ),
                    )
                    route = self._find_route(
                        fleet.system_id,
                        target.system_id,
                        fleet.owner_id,
                    )
                    if route:
                        fleet.route = route
                        fleet.days_to_arrival = self._jump_duration(
                            fleet.system_id,
                            route[0],
                        )
                        self._record(
                            f"{empire.name} forces are advancing on {target.name}."
                        )
            while (
                empire.system_ids
                and self.elapsed_days >= empire.next_expansion_day
            ):
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
            "schema_version": 3,
            "galaxy": asdict(self.galaxy),
            "player_species_id": self.player_species_id,
            "name_culture": self.name_culture,
            "leader_name": self.leader_name,
            "custom_species": [
                profile.to_dict()
                for profile in self.species_catalog.values()
                if profile.derived_from is not None
            ],
            "species_rights": dict(self.species_rights),
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
            "ai_fleets": [asdict(fleet) for fleet in self.ai_fleets],
            "ai_empires": [asdict(empire) for empire in self.ai_empires],
            "diplomacy": {
                empire_id: asdict(relation)
                for empire_id, relation in self.diplomacy.items()
            },
            "log": list(self.log),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, object],
        content_path: Path | None = None,
    ) -> "Campaign":
        version = data.get("schema_version")
        if version not in (1, 2, 3):
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
            name_culture=str(data.get("name_culture", "all")),
            content_path=content_path,
        )
        try:
            custom_species = [
                SpeciesProfile.from_dict(item)
                for item in data.get("custom_species", [])
            ]
            for profile in custom_species:
                if (
                    profile.species_id in campaign.species_catalog
                    or profile.derived_from not in campaign.species_catalog
                    or not profile.name
                    or profile.lifespan_years <= 0
                    or not math.isfinite(profile.annual_growth_rate)
                    or profile.annual_growth_rate < 0
                    or not profile.classification
                    or not profile.preferred_climates
                    or not profile.traits
                    or not profile.needs
                    or not profile.name_sets
                    or Path(profile.portrait).is_absolute()
                    or ".." in Path(profile.portrait).parts
                ):
                    raise ValueError("Invalid custom species in save")
                campaign.species_catalog[profile.species_id] = profile
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
            ai_fleets = [
                Fleet(**fleet_data)
                for fleet_data in data.get("ai_fleets", [])
            ]
            ai_empires = [
                AIEmpire(**empire_data)
                for empire_data in data["ai_empires"]
            ]
            diplomacy = {
                empire_id: DiplomaticRelation(**relation_data)
                for empire_id, relation_data in data.get("diplomacy", {}).items()
            }
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Save contains invalid campaign data") from error

        if version >= 3:
            raw_rights = data.get("species_rights")
            if not isinstance(raw_rights, dict):
                raise ValueError("Save contains invalid species rights")
            species_rights = {
                str(species_id): str(rights)
                for species_id, rights in raw_rights.items()
            }
            if any(
                species_id not in campaign.species_catalog
                or rights not in {"citizen", "resident", "restricted"}
                for species_id, rights in species_rights.items()
            ):
                raise ValueError("Save contains invalid species rights")
            campaign.species_rights = species_rights
            campaign.leader_name = str(data.get("leader_name", campaign.leader_name))
            if (
                not campaign.leader_name
                or campaign.name_culture not in campaign.species_catalog[campaign.player_species_id].name_cultures
            ):
                raise ValueError("Save contains an invalid species identity")

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
                or not math.isfinite(colony.evolution_progress)
                or colony.evolution_progress < 0
                or colony.evolution_progress >= 1
            ):
                raise ValueError("Save contains an invalid colony")
        route_edges = {
            tuple(sorted(route))
            for route in galaxy.routes
        }
        for fleet in [*fleets, *ai_fleets]:
            route = [fleet.system_id, *fleet.route]
            if (
                fleet.system_id not in system_ids
                or fleet.ship_count <= 0
                or fleet.owner_id not in {"union", *(empire.empire_id for empire in ai_empires)}
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
        if version == 1 and not ai_fleets:
            ai_fleets = campaign.ai_fleets
        if version == 1 and not diplomacy:
            diplomacy = campaign.diplomacy
        if set(diplomacy) != {empire.empire_id for empire in ai_empires}:
            raise ValueError("Save contains invalid diplomatic relationships")
        known_treaties = {
            "non_aggression",
            "trade",
            "research",
            "defensive_alliance",
        }
        for relation in diplomacy.values():
            if (
                any(treaty not in known_treaties for treaty in relation.treaties)
                or len(set(relation.treaties)) != len(relation.treaties)
                or not -100 <= relation.opinion <= 100
                or not 0 <= relation.trust <= 100
                or (
                    relation.at_war
                    and relation.war_started_day is None
                )
                or (
                    relation.war_started_day is not None
                    and not 0 <= relation.war_started_day <= float(data["elapsed_days"])
                )
            ):
                raise ValueError("Save contains an invalid diplomatic relationship")
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
        campaign.ai_fleets = ai_fleets
        campaign.ai_empires = ai_empires
        campaign.diplomacy = diplomacy
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
        first_contact = self._establish_contacts_in_system(system)
        message = (
            f"Survey complete: {system.name} - {system.world_type} identified. "
            "Survey teams recovered research and alloys."
        )
        if first_contact:
            message += f" {first_contact}"
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
