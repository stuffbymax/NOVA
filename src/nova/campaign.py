"""Playable campaign rules for the first NOVA exploration scenario."""

from dataclasses import dataclass, field


@dataclass
class SystemObject:
    object_id: str
    name: str
    kind: str
    orbit: float
    size: int
    world_type: str
    description: str
    habitable: bool = False
    anomaly: bool = False
    anomaly_resolved: bool = False
    gateway: bool = False
    surveyed: bool = False
    colonized: bool = False
    parent_id: str | None = None
    population: str = "-"


@dataclass
class StarSystem:
    system_id: str
    name: str
    x: float
    y: float
    star_type: str
    world_type: str
    description: str
    habitable: bool = False
    gateway: bool = False
    surveyed: bool = False
    colonized: bool = False
    population: str = "-"
    objects: list[SystemObject] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.colonized:
            return "Colonized"
        if self.surveyed:
            return "Surveyed"
        return "Uncharted"


class Campaign:
    """A small, deterministic space-colonization campaign."""

    COLONY_ALLOY_COST = 22
    COLONY_INFLUENCE_COST = 3
    SURVEY_SCIENCE_COST = 4
    GATEWAY_SCIENCE_COST = 12

    def __init__(self) -> None:
        self.systems = [
            StarSystem(
                "sol",
                "Sol",
                0.16,
                0.44,
                "G-type",
                "Ocean world",
                "The Union's cradle is secure, but its shipyards are stretched thin.",
                surveyed=True,
                colonized=True,
                population="8.1B",
            ),
            StarSystem(
                "asterion",
                "Asterion",
                0.34,
                0.25,
                "F-type",
                "Jungle world",
                "A warm, cloud-covered world. Long-range scans suggest a rich biosphere.",
                habitable=True,
            ),
            StarSystem(
                "vesper",
                "Vesper",
                0.40,
                0.68,
                "K-type",
                "Desert world",
                "A dry frontier world with accessible minerals and a thin atmosphere.",
                habitable=True,
            ),
            StarSystem(
                "helios",
                "Helios",
                0.59,
                0.34,
                "A-type",
                "Arctic world",
                "A pale blue star illuminates an icebound planet and a field of old debris.",
                habitable=True,
            ),
            StarSystem(
                "cinder",
                "Cinder",
                0.68,
                0.69,
                "K-type",
                "Volcanic world",
                "A violent young world. Its crust is unstable, but its metals are valuable.",
            ),
            StarSystem(
                "eidolon",
                "Eidolon",
                0.84,
                0.45,
                "Unknown",
                "Ancient gateway",
                "A structure older than any known civilization hums beyond the system's star.",
                gateway=True,
            ),
            StarSystem(
                "polaris",
                "Polaris",
                0.14,
                0.17,
                "F-type",
                "Gas giant",
                "A cold blue giant and its moons mark the northern edge of explored space.",
            ),
            StarSystem(
                "new-carthage",
                "New Carthage",
                0.19,
                0.79,
                "G-type",
                "Temperate world",
                "A promising young colony is surrounded by uncharted outer planets.",
                habitable=True,
                surveyed=True,
                colonized=True,
                population="910M",
            ),
            StarSystem(
                "kepler",
                "Kepler's Reach",
                0.29,
                0.51,
                "M-type",
                "Toxic world",
                "A dim red star warms a dense system of rocky planets and ancient signals.",
            ),
            StarSystem(
                "tantalus",
                "Tantalus",
                0.32,
                0.87,
                "K-type",
                "Ocean world",
                "A restless ocean world orbits beneath a broad, luminous asteroid belt.",
                habitable=True,
            ),
            StarSystem(
                "lyra",
                "Lyra",
                0.46,
                0.11,
                "A-type",
                "Arctic world",
                "A bright binary star system with a frozen world and unusual radio echoes.",
            ),
            StarSystem(
                "morrow",
                "Morrow",
                0.53,
                0.86,
                "G-type",
                "Jungle world",
                "Thick cloud bands conceal a vast living world and a quiet moon.",
                habitable=True,
            ),
            StarSystem(
                "nadir",
                "Nadir",
                0.71,
                0.12,
                "M-type",
                "Desert world",
                "A distant red dwarf hosts an old mining station and mineral-rich debris.",
            ),
            StarSystem(
                "orion",
                "Orion's Wake",
                0.81,
                0.83,
                "B-type",
                "Volcanic world",
                "A massive blue star illuminates shattered planets and a spatial rift.",
            ),
            StarSystem(
                "sable",
                "Sable",
                0.94,
                0.21,
                "K-type",
                "Ocean world",
                "An isolated system whose outer moon carries a repeating signal.",
                habitable=True,
            ),
            StarSystem(
                "farpoint",
                "Farpoint",
                0.95,
                0.72,
                "G-type",
                "Arid world",
                "The last charted star before a dark region of interstellar space.",
            ),
        ]
        self.routes = (
            ("sol", "asterion"),
            ("sol", "vesper"),
            ("asterion", "helios"),
            ("vesper", "cinder"),
            ("helios", "eidolon"),
            ("cinder", "eidolon"),
            ("sol", "polaris"),
            ("sol", "new-carthage"),
            ("asterion", "kepler"),
            ("vesper", "tantalus"),
            ("asterion", "lyra"),
            ("cinder", "morrow"),
            ("helios", "nadir"),
            ("eidolon", "orion"),
            ("orion", "sable"),
            ("sable", "farpoint"),
        )
        for system in self.systems:
            system.objects = self._make_system_objects(system)
        earth = self.get_object("sol", "earth")
        earth.surveyed = True
        earth.colonized = True
        earth.population = "8.1B"
        colony = self.get_object("new-carthage", "homeworld")
        colony.surveyed = True
        colony.colonized = True
        colony.population = "910M"
        self.alloys = 50.0
        self.science = 18.0
        self.influence = 8.0
        self.elapsed_days = 0.0
        self.gateway_studied = False
        self.log = [
            "2480.01  The frontier is open. Survey the unknown systems.",
            "2480.01  Union scouts report an ancient signal at Eidolon.",
        ]

    @property
    def colonies(self) -> int:
        return sum(system.colonized for system in self.systems)

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

    def _make_system_objects(self, system: StarSystem) -> list[SystemObject]:
        planet_type = system.world_type
        habitable_world_id = (
            "earth"
            if system.system_id == "sol"
            else "homeworld"
            if system.colonized
            else "frontier"
        )
        objects = [
            SystemObject(
                habitable_world_id,
                system.world_type,
                "Planet",
                0.28,
                13,
                planet_type,
                system.description,
                habitable=system.habitable or system.colonized,
                surveyed=system.surveyed,
                colonized=system.colonized,
                population=system.population,
            ),
            SystemObject(
                "inner-world",
                "Inner World",
                "Planet",
                0.15,
                7,
                "Scorched terrestrial",
                "A small, airless world baked by the nearby star.",
            ),
            SystemObject(
                "outer-giant",
                "Outer Gas Giant",
                "Gas giant",
                0.70,
                18,
                "Gas giant",
                "A banded giant world with a family of moons and faint rings.",
            ),
            SystemObject(
                "outer-moon",
                "Lumen",
                "Moon",
                0.10,
                6,
                "Icy moon",
                "A fractured moon with a subsurface ocean.",
                parent_id="outer-giant",
            ),
            SystemObject(
                "inner-moon",
                "Cinder",
                "Moon",
                0.085,
                5,
                "Airless moon",
                "A cratered companion with deep deposits of rare metals.",
                parent_id="inner-world",
            ),
            SystemObject(
                "asteroid-belt",
                "Outer Asteroid Belt",
                "Asteroid belt",
                0.86,
                5,
                "Metal-rich debris",
                "Thousands of tumbling rocks contain useful metals and volatiles.",
            ),
            SystemObject(
                "deep-signal",
                "Unusual Signal",
                "Anomaly",
                0.53,
                9,
                "Unknown",
                "A repeating transmission is buried in the system's background noise.",
                anomaly=True,
            ),
            SystemObject(
                "derelict",
                "Drifting Derelict",
                "Anomaly",
                0.96,
                9,
                "Unknown",
                "A damaged vessel drifts silently beyond the outer planets.",
                anomaly=True,
            ),
        ]
        if system.gateway:
            objects.append(
                SystemObject(
                    "ancient-gateway",
                    "Ancient Gateway",
                    "Gateway",
                    1.04,
                    14,
                    "Precursor megastructure",
                    system.description,
                    anomaly=True,
                    gateway=True,
                )
            )
        return objects

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
            if system_object.anomaly:
                system_object.world_type = "Anomaly detected"
                message = f"Anomaly detected at {system_object.name} in {system.name}. A special project is ready."
            else:
                self.science += 3
                self.alloys += 2
                message = f"Survey complete: {system_object.name} in {system.name} - {system_object.description}"
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
            message = f"Anomaly resolved: {system_object.name} in {system.name}. The signal contained valuable research."
            self._record(message)
            return message
        if system_object.habitable and not system_object.colonized:
            return self._colonize(system, system_object)
        raise ValueError(f"No available action for {system_object.name}")

    def advance(self, delta: float) -> None:
        if delta < 0:
            raise ValueError("Campaign delta cannot be negative")
        if delta == 0:
            return
        self.elapsed_days += delta
        settled_colonies = max(0, self.colonies - 1)
        self.alloys += delta * (0.12 + settled_colonies * 0.08)
        self.science += delta * (0.04 + settled_colonies * 0.035)

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
        if self.alloys < self.COLONY_ALLOY_COST:
            raise ValueError("Not enough alloys to found a colony")
        if self.influence < self.COLONY_INFLUENCE_COST:
            raise ValueError("Not enough influence to found a colony")
        self.alloys -= self.COLONY_ALLOY_COST
        self.influence -= self.COLONY_INFLUENCE_COST
        target.colonized = True
        target.population = "1.2B"
        system.colonized = True
        system.population = target.population
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
