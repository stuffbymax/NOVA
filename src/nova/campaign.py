"""Playable campaign rules for the first NOVA exploration scenario."""

from .galaxy import (
    Galaxy,
    GalaxyGenerator,
    GalaxySettings,
    StarSystem,
    SystemObject,
)


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
    ) -> None:
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
        self.alloys = 50.0
        self.science = 18.0
        self.influence = 8.0
        self.volatiles = 4.0
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
