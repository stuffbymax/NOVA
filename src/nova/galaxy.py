"""Seeded procedural galaxy and star-system generation."""

from dataclasses import dataclass, field
import math
import random


@dataclass(frozen=True)
class GalaxySettings:
    seed: int = 2480
    size: str = "medium"
    shape: str = "spiral"
    galaxy_name: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise ValueError("Galaxy seed must be an integer")
        if self.size not in GalaxyGenerator.SYSTEM_COUNTS:
            raise ValueError(f"Unknown galaxy size: {self.size}")
        if self.shape not in GalaxyGenerator.SHAPES:
            raise ValueError(f"Unknown galaxy shape: {self.shape}")
        if (
            self.galaxy_name is not None
            and self.galaxy_name not in GalaxyGenerator.GALAXY_MORPHOLOGIES
        ):
            raise ValueError(f"Unknown named galaxy: {self.galaxy_name}")
        if (
            self.galaxy_name is not None
            and GalaxyGenerator.GALAXY_MORPHOLOGIES[self.galaxy_name] != self.shape
        ):
            raise ValueError(
                f"{self.galaxy_name} does not have {self.shape} morphology"
            )


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
    linked_system_id: str | None = None
    resources: dict[str, int] = field(default_factory=dict)
    orbit_au: float | None = None
    mass_earth: float | None = None
    radius_earth: float | None = None
    climate: str = "Unknown"
    gravity_earth: float | None = None
    atmosphere: str = "Unknown"
    surface_conditions: str = "Unknown"
    population_capacity_billions: float = 0.0
    orbit_period_days: float | None = None
    orbit_distance_km: float | None = None
    owner: str | None = None
    history: list[str] = field(default_factory=list)

    @property
    def is_planet(self) -> bool:
        return self.kind in ("Planet", "Gas giant")


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
    z: float = 0.0
    mass_solar: float = 1.0
    luminosity_solar: float = 1.0
    age_gyr: float = 4.5
    metallicity_dex: float = 0.0
    companion_star_type: str | None = None
    companion_mass_solar: float = 0.0
    companion_luminosity_solar: float = 0.0
    binary_separation_au: float | None = None
    owner: str | None = None

    @property
    def status(self) -> str:
        if self.colonized:
            return "Colonized"
        if self.surveyed:
            return "Surveyed"
        return "Uncharted"

    @property
    def total_mass_solar(self) -> float:
        return self.mass_solar + self.companion_mass_solar

    @property
    def total_luminosity_solar(self) -> float:
        return self.luminosity_solar + self.companion_luminosity_solar

    @property
    def planets(self) -> tuple[SystemObject, ...]:
        return tuple(obj for obj in self.objects if obj.is_planet)

    @property
    def moons(self) -> tuple[SystemObject, ...]:
        return tuple(obj for obj in self.objects if obj.kind == "Moon")


@dataclass(frozen=True)
class Nebula:
    name: str
    x: float
    y: float
    radius: float


@dataclass
class Galaxy:
    name: str
    region_name: str
    shape: str
    seed: int
    size: str
    diameter_light_years: int
    systems: list[StarSystem]
    routes: tuple[tuple[str, str], ...]
    nebulae: tuple[Nebula, ...]

    def position_light_years(self, system: StarSystem) -> tuple[float, float]:
        scale = self.diameter_light_years
        vertical_scale = {
            "spiral": 0.72,
            "elliptical": 0.82,
            "irregular": 1.0,
        }[self.shape]
        return (
            (system.x - 0.5) * scale,
            (system.y - 0.5) * scale * vertical_scale,
        )

    def position_3d_light_years(
        self,
        system: StarSystem,
    ) -> tuple[float, float, float]:
        x, y = self.position_light_years(system)
        return x, y, system.z * self.diameter_light_years

    @property
    def morphology(self) -> str:
        return {
            "spiral": "barred spiral (SBbc)",
            "elliptical": "elliptical",
            "irregular": "irregular",
        }[self.shape]


class GalaxyGenerator:
    """Generates a reproducible galaxy in normalized map coordinates."""

    SYSTEM_COUNTS = {"small": 24, "medium": 48, "large": 80}
    SHAPES = ("spiral", "elliptical", "irregular")

    _CORE_SYSTEMS = (
        ("sol", "Sol", "G-type", "Temperate world", True, False, True, True, "8.1B",
         "The Union's cradle is secure, but its shipyards are stretched thin."),
        ("asterion", "Asterion", "F-type", "Jungle world", True, False, False, False, "-",
         "A warm, cloud-covered world. Long-range scans suggest a rich biosphere."),
        ("vesper", "Vesper", "K-type", "Desert world", True, False, False, False, "-",
         "A dry frontier world with accessible minerals and a thin atmosphere."),
        ("helios", "Helios", "A-type", "Arctic world", True, False, False, False, "-",
         "A pale blue star illuminates an icebound planet and a field of old debris."),
        ("cinder", "Cinder", "K-type", "Volcanic world", False, False, False, False, "-",
         "A violent young world. Its crust is unstable, but its metals are valuable."),
        ("eidolon", "Eidolon", "G-type", "Ancient gateway", False, True, False, False, "-",
         "A structure older than any known civilization hums beyond the system's star."),
        ("polaris", "Polaris", "F-type", "Gas giant", False, False, False, False, "-",
         "A cold blue giant and its moons mark the northern edge of explored space."),
        ("new-carthage", "New Carthage", "G-type", "Temperate world", True, False, True, True, "910M",
         "A promising young colony is surrounded by uncharted outer planets."),
        ("kepler", "Kepler's Reach", "M-type", "Toxic world", False, False, False, False, "-",
         "A dim red star warms a dense system of rocky planets and ancient signals."),
        ("tantalus", "Tantalus", "K-type", "Ocean world", True, False, False, False, "-",
         "A restless ocean world orbits beneath a broad, luminous asteroid belt."),
        ("lyra", "Lyra", "A-type", "Arctic world", False, False, False, False, "-",
         "A bright binary star system with a frozen world and unusual radio echoes."),
        ("morrow", "Morrow", "G-type", "Jungle world", True, False, False, False, "-",
         "Thick cloud bands conceal a vast living world and a quiet moon."),
        ("nadir", "Nadir", "M-type", "Desert world", False, False, False, False, "-",
         "A distant red dwarf hosts an old mining station and mineral-rich debris."),
        ("orion", "Orion's Wake", "B-type", "Volcanic world", False, False, False, False, "-",
         "A massive blue star illuminates shattered planets and a spatial rift."),
        ("sable", "Sable", "K-type", "Ocean world", True, False, False, False, "-",
         "An isolated system whose outer moon carries a repeating signal."),
        ("farpoint", "Farpoint", "G-type", "Arid world", False, False, False, False, "-",
         "The last charted star before a dark region of interstellar space."),
    )
    _STAR_WEIGHTS = (
        ("M-type", 0.76),
        ("K-type", 0.12),
        ("G-type", 0.076),
        ("F-type", 0.03),
        ("A-type", 0.01),
        ("B-type", 0.0035),
        ("O-type", 0.0005),
    )
    _WORLD_TYPES = (
        "Barren world",
        "Desert world",
        "Ocean world",
        "Temperate world",
        "Jungle world",
        "Toxic world",
        "Arctic world",
        "Volcanic world",
        "Frozen world",
        "Arid world",
        "Gas giant",
    )
    _STAR_NAMES = (
        "Achernar", "Acrux", "Adhara", "Aldebaran", "Alderamin", "Algieba",
        "Alhena", "Alioth", "Alkaid", "Almach", "Alnair", "Alnilam", "Alnitak",
        "Alphard", "Alphecca", "Alpheratz", "Altair", "Ankaa", "Antares",
        "Arcturus", "Arneb", "Atria", "Avior", "Bellatrix", "Betelgeuse",
        "Canopus", "Capella", "Castor", "Caph", "Deneb", "Denebola", "Diphda",
        "Dubhe", "Elnath", "Eltanin", "Enif", "Fomalhaut", "Gacrux", "Hadar",
        "Hamal", "Izar", "Kaus Australis", "Kochab", "Markab", "Menkalinan",
        "Menkent", "Merak", "Mintaka", "Mira", "Mirach", "Mirfak", "Mizar",
        "Nashira", "Nunki", "Phad", "Polaris", "Pollux", "Procyon", "Rasalhague",
        "Regulus", "Rigel", "Rigil Kentaurus", "Sabik", "Sadr", "Saiph",
        "Scheat", "Schedar", "Shaula", "Sirius", "Spica", "Suhail", "Tarazed",
        "Unukalhai", "Vega", "Vindemiatrix", "Wezen", "Zosma",
    )
    _NEBULA_NAMES = (
        "Orion Nebula (M42)", "Eagle Nebula (M16)", "Crab Nebula (M1)",
        "Lagoon Nebula (M8)", "Carina Nebula", "Tarantula Nebula",
        "Rosette Nebula", "Veil Nebula",
    )
    _GALAXY_PREFIXES = (
        "Carina", "Cygnus", "Eos", "Hesper", "Kepler", "Orion", "Perseus",
        "Phoenix", "Vesper", "Viridian",
    )
    _GALAXY_SUFFIXES = (
        "Reach", "Expanse", "Crescent", "Horizon", "Drift", "Whorl", "Cloud",
    )
    _REGIONS = (
        "Orion Spur",
        "Perseus Arm",
        "Carina-Sagittarius Arm",
        "Cygnus Arm",
        "Outer Disk",
        "Galactic Core",
    )
    GALAXY_MORPHOLOGIES = {
        "Milky Way": "spiral",
        "Andromeda Galaxy (M31)": "spiral",
        "Triangulum Galaxy (M33)": "spiral",
        "Whirlpool Galaxy (M51)": "spiral",
        "Pinwheel Galaxy (M101)": "spiral",
        "Sombrero Galaxy (M104)": "spiral",
        "Messier 87 (Virgo A)": "elliptical",
        "Messier 49": "elliptical",
        "Messier 60": "elliptical",
        "Large Magellanic Cloud": "irregular",
        "Small Magellanic Cloud": "irregular",
        "Barnard's Galaxy (NGC 6822)": "irregular",
    }
    GALAXY_DIAMETERS_LIGHT_YEARS = {
        "Milky Way": 100_000,
        "Andromeda Galaxy (M31)": 152_000,
        "Triangulum Galaxy (M33)": 60_000,
        "Whirlpool Galaxy (M51)": 76_000,
        "Pinwheel Galaxy (M101)": 170_000,
        "Sombrero Galaxy (M104)": 49_000,
        "Messier 87 (Virgo A)": 120_000,
        "Messier 49": 157_000,
        "Messier 60": 120_000,
        "Large Magellanic Cloud": 32_000,
        "Small Magellanic Cloud": 19_000,
        "Barnard's Galaxy (NGC 6822)": 7_000,
    }
    _ANOMALIES = (
        ("Ancient ruins", "Precursor ruins lie buried beneath a fractured surface."),
        ("Spatial rift", "Sensors detect a short-lived distortion in local spacetime."),
        ("Organic signal", "A repeating signal carries patterns unlike any known machine."),
        ("Derelict vessel", "A damaged vessel drifts silently beyond the outer planets."),
        ("Mineral formation", "An unusually dense deposit formed under unknown conditions."),
        ("Quantum echo", "A faint echo repeats from an apparently empty orbit."),
    )

    def __init__(self, settings: GalaxySettings) -> None:
        self.settings = settings
        self.random = random.Random(settings.seed)

    def generate(self) -> Galaxy:
        count = self.SYSTEM_COUNTS[self.settings.size]
        systems = self._generate_systems(count)
        routes = self._generate_routes(systems)
        nebulae = self._generate_nebulae()
        galaxy_name = self.settings.galaxy_name or (
            "Milky Way"
            if self.settings.shape == "spiral"
            else self.random.choice(
                [
                    name
                    for name, morphology in self.GALAXY_MORPHOLOGIES.items()
                    if morphology == self.settings.shape
                ]
            )
        )
        region_name = (
            self.random.choice(self._REGIONS)
            if galaxy_name == "Milky Way"
            else (
                f"{self.random.choice(self._GALAXY_PREFIXES)} "
                f"{self.random.choice(self._GALAXY_SUFFIXES)}"
            )
        )
        galaxy = Galaxy(
            name=galaxy_name,
            region_name=region_name,
            shape=self.settings.shape,
            seed=self.settings.seed,
            size=self.settings.size,
            diameter_light_years=self.GALAXY_DIAMETERS_LIGHT_YEARS[galaxy_name],
            systems=systems,
            routes=routes,
            nebulae=nebulae,
        )
        self._validate(galaxy)
        return galaxy

    @staticmethod
    def _validate(galaxy: Galaxy) -> None:
        system_ids = {system.system_id for system in galaxy.systems}
        system_names = {system.name for system in galaxy.systems}
        if len(system_ids) != len(galaxy.systems):
            raise RuntimeError("Galaxy generation produced duplicate system IDs")
        if len(system_names) != len(galaxy.systems):
            raise RuntimeError("Galaxy generation produced duplicate star names")
        route_keys = [frozenset(route) for route in galaxy.routes]
        if (
            any(len(route) != 2 for route in galaxy.routes)
            or any(len(route) != 2 for route in route_keys)
            or any(not route <= system_ids for route in route_keys)
            or len(route_keys) != len(set(route_keys))
        ):
            raise RuntimeError("Galaxy generation produced invalid star routes")
        if any(
            not 0 <= system.x <= 1
            or not 0 <= system.y <= 1
            or not -0.5 <= system.z <= 0.5
            for system in galaxy.systems
        ):
            raise RuntimeError("Galaxy generation produced an out-of-bounds star")
        if any(
            not math.isfinite(system.mass_solar)
            or not math.isfinite(system.luminosity_solar)
            or not math.isfinite(system.age_gyr)
            or not math.isfinite(system.metallicity_dex)
            or system.mass_solar <= 0
            or system.luminosity_solar < 0
            or system.companion_mass_solar < 0
            or system.companion_luminosity_solar < 0
            or not 0 < system.age_gyr <= 13.8
            or not -2.5 <= system.metallicity_dex <= 1.0
            for system in galaxy.systems
        ):
            raise RuntimeError("Galaxy generation produced invalid stellar data")
        if any(
            (system.companion_star_type is None)
            != (system.binary_separation_au is None)
            or (
                system.binary_separation_au is not None
                and system.binary_separation_au <= 0
            )
            for system in galaxy.systems
        ):
            raise RuntimeError("Galaxy generation produced invalid binary-star data")

        reached = {galaxy.systems[0].system_id}
        while True:
            connected = {
                second if first in reached else first
                for first, second in galaxy.routes
                if first in reached or second in reached
            }
            updated = reached | connected
            if updated == reached:
                break
            reached = updated
        if reached != system_ids:
            raise RuntimeError("Galaxy generation produced disconnected star routes")

        for system in galaxy.systems:
            object_ids = {obj.object_id for obj in system.objects}
            if len(object_ids) != len(system.objects):
                raise RuntimeError(
                    f"Galaxy generation produced duplicate objects in {system.name}"
                )
            if any(
                obj.parent_id is not None and obj.parent_id not in object_ids
                for obj in system.objects
            ):
                raise RuntimeError(
                    f"Galaxy generation produced an orphaned moon in {system.name}"
                )
            if system.habitable != any(obj.habitable for obj in system.objects):
                raise RuntimeError(
                    f"Galaxy generation produced inconsistent habitability in {system.name}"
                )
            if any(
                obj.linked_system_id is not None
                and obj.linked_system_id not in system_ids
                for obj in system.objects
            ):
                raise RuntimeError(
                    f"Galaxy generation produced an invalid wormhole in {system.name}"
                )
            if any(
                obj.orbit_au is not None
                and (not math.isfinite(obj.orbit_au) or obj.orbit_au <= 0)
                for obj in system.objects
            ):
                raise RuntimeError(
                    f"Galaxy generation produced a non-positive orbit in {system.name}"
                )
            if any(
                value is not None and (not math.isfinite(value) or value <= 0)
                for obj in system.objects
                for value in (
                    obj.mass_earth,
                    obj.radius_earth,
                    obj.gravity_earth,
                    obj.orbit_period_days,
                    obj.orbit_distance_km,
                )
            ):
                raise RuntimeError(
                    f"Galaxy generation produced invalid planetary data in {system.name}"
                )
            if any(
                not math.isfinite(obj.population_capacity_billions)
                or obj.population_capacity_billions < 0
                or (obj.owner is not None and not obj.colonized)
                or (
                    obj.is_planet
                    and (
                        obj.mass_earth is None
                        or obj.radius_earth is None
                        or obj.gravity_earth is None
                        or obj.orbit_period_days is None
                    )
                )
                for obj in system.objects
            ):
                raise RuntimeError(
                    f"Galaxy generation produced inconsistent planet data in {system.name}"
                )
            if any(
                amount < 0
                for obj in system.objects
                for amount in obj.resources.values()
            ):
                raise RuntimeError(
                    f"Galaxy generation produced a negative deposit in {system.name}"
                )
        wormholes = [
            (system, obj)
            for system in galaxy.systems
            for obj in system.objects
            if obj.kind == "Wormhole"
        ]
        if len(wormholes) % 2:
            raise RuntimeError("Galaxy generation produced an unpaired wormhole")
        for system, wormhole in wormholes:
            destination = next(
                entry
                for entry in galaxy.systems
                if entry.system_id == wormhole.linked_system_id
            )
            if not any(
                obj.kind == "Wormhole"
                and obj.linked_system_id == system.system_id
                and obj.object_id == wormhole.object_id
                for obj in destination.objects
            ):
                raise RuntimeError("Galaxy generation produced a one-way wormhole")
        if any(
            not 0 <= nebula.x <= 1
            or not 0 <= nebula.y <= 1
            or nebula.radius <= 0
            for nebula in galaxy.nebulae
        ):
            raise RuntimeError("Galaxy generation produced an invalid nebula")

    def _generate_systems(self, count: int) -> list[StarSystem]:
        systems: list[StarSystem] = []
        positions: list[tuple[float, float]] = []
        used_names = {entry[1] for entry in self._CORE_SYSTEMS}
        for index in range(count):
            x, y, z = self._position(index, positions)
            positions.append((x, y))
            if index < len(self._CORE_SYSTEMS):
                (
                    system_id,
                    name,
                    star_type,
                    world_type,
                    habitable,
                    gateway,
                    surveyed,
                    colonized,
                    population,
                    description,
                ) = self._CORE_SYSTEMS[index]
            else:
                system_id = f"system-{index + 1:03d}"
                name = self._new_star_name(used_names)
                used_names.add(name)
                star_type = self._star_type()
                remnant_roll = self.random.random()
                if remnant_roll < 0.002:
                    star_type = "Black hole"
                elif remnant_roll < 0.007:
                    star_type = "Neutron star"
                elif remnant_roll < 0.087:
                    star_type = "White dwarf"
                habitable = False
                world_type = self.random.choice(self._WORLD_TYPES)
                gateway = False
                surveyed = False
                colonized = False
                population = "-"
                description = (
                    f"A {star_type} star hosts a "
                    f"{world_type.casefold()} and a varied planetary system."
                )
                if star_type in ("Black hole", "Neutron star", "White dwarf"):
                    world_type = f"{star_type} system"
                    habitable = False
                    description = (
                        "A compact stellar remnant sculpts the orbits of nearby worlds."
                    )

            system = StarSystem(
                system_id=system_id,
                name=name,
                x=x,
                y=y,
                star_type=star_type,
                world_type=world_type,
                description=description,
                habitable=habitable,
                gateway=gateway,
                surveyed=surveyed,
                colonized=colonized,
                population=population,
                z=z,
                owner="Union" if colonized else None,
            )
            (
                system.mass_solar,
                system.luminosity_solar,
                system.age_gyr,
                system.metallicity_dex,
            ) = self._stellar_properties(
                system.star_type,
                math.dist((system.x, system.y), (0.5, 0.5)),
            )
            if system.system_id == "sol":
                system.mass_solar = 1.0
                system.luminosity_solar = 1.0
                system.age_gyr = 4.57
                system.metallicity_dex = 0.012
            self._generate_companion(system)
            system.objects = self._generate_objects(system)
            if system.system_id not in {entry[0] for entry in self._CORE_SYSTEMS}:
                habitable_world = next(
                    (obj for obj in system.objects if obj.habitable),
                    None,
                )
                system.habitable = habitable_world is not None
                if habitable_world is not None:
                    system.world_type = habitable_world.world_type
                    system.description = (
                        f"A {system.star_type} star hosts a "
                        f"{system.world_type.casefold()} in its temperate zone."
                    )
                    habitable_world.description = system.description
                else:
                    first_planet = next(
                        obj
                        for obj in system.objects
                        if obj.kind in ("Planet", "Gas giant")
                    )
                    if system.star_type not in (
                        "Black hole",
                        "Neutron star",
                        "White dwarf",
                    ):
                        system.world_type = first_planet.world_type
                        system.description = (
                            f"A {system.star_type} star hosts a "
                            f"{system.world_type.casefold()} and a varied planetary system."
                        )
                        first_planet.description = system.description
            systems.append(system)
        self._add_wormholes(systems)
        return systems

    def _position(
        self,
        index: int,
        existing: list[tuple[float, float]],
    ) -> tuple[float, float, float]:
        if index == 0:
            return 0.5, 0.5, 0.0
        for _ in range(300):
            if self.settings.shape == "spiral":
                arms = 4
                arm = self.random.randrange(arms)
                radius = min(0.47, self.random.gammavariate(2.0, 0.105))
                if self.random.random() < 0.16:
                    angle = self.random.random() * math.tau
                else:
                    pitch = math.radians(13)
                    angle = (
                        arm * math.tau / arms
                        + math.log(max(radius, 0.015) / 0.04) / math.tan(pitch)
                    )
                angle += self.random.gauss(0, 0.08 + radius * 0.35)
                x = 0.5 + math.cos(angle) * radius
                y = 0.5 + math.sin(angle) * radius * 0.72
            elif self.settings.shape == "elliptical":
                radius = min(0.47, self.random.gammavariate(2.2, 0.105))
                angle = self.random.random() * math.tau
                x = 0.5 + math.cos(angle) * radius
                y = 0.5 + math.sin(angle) * radius * 0.82
            else:
                center_x = self.random.choice((0.26, 0.49, 0.74))
                center_y = self.random.choice((0.30, 0.52, 0.73))
                x = self.random.gauss(center_x, 0.105)
                y = self.random.gauss(center_y, 0.105)
            candidate = (min(0.97, max(0.03, x)), min(0.97, max(0.03, y)))
            minimum_distance = 0.018 if len(existing) > 48 else 0.026
            if all(
                math.dist(candidate, position) >= minimum_distance
                for position in existing
            ):
                thickness = {
                    "spiral": 0.004,
                    "elliptical": 0.045,
                    "irregular": 0.055,
                }[self.settings.shape]
                z = min(0.18, max(-0.18, self.random.gauss(0, thickness)))
                return candidate[0], candidate[1], z
        thickness = {"spiral": 0.004, "elliptical": 0.045, "irregular": 0.055}[
            self.settings.shape
        ]
        z = min(0.18, max(-0.18, self.random.gauss(0, thickness)))
        return candidate[0], candidate[1], z

    def _generate_objects(self, system: StarSystem) -> list[SystemObject]:
        planet_count = 3 + sum(self.random.random() < 0.57 for _ in range(6))
        worlds: list[SystemObject] = []
        is_campaign_system = system.system_id in {
            entry[0] for entry in self._CORE_SYSTEMS
        }
        primary_id = "earth" if system.system_id == "sol" else (
            "homeworld" if system.colonized else "frontier"
        )
        primary_type = system.world_type
        inner_orbit_au = max(
            0.025,
            0.04 * math.sqrt(system.total_mass_solar),
            (system.binary_separation_au or 0) * 2.5,
        )
        previous_orbit_au = inner_orbit_au
        habitable_inner = 0.95 * math.sqrt(max(system.total_luminosity_solar, 0.0001))
        habitable_outer = 1.67 * math.sqrt(max(system.total_luminosity_solar, 0.0001))
        main_sequence_lifetime = (
            10.0 * max(
                system.mass_solar,
                system.companion_mass_solar,
            )**-2.5
            if system.star_type not in ("Black hole", "Neutron star", "White dwarf")
            else 0
        )
        habitable_types = (
            "Ocean world",
            "Temperate world",
            "Jungle world",
        )
        for index in range(planet_count):
            if index == 0:
                orbit_au = inner_orbit_au
            else:
                previous_orbit_au *= self.random.uniform(1.45, 2.0)
                orbit_au = previous_orbit_au
            if is_campaign_system:
                if index == 0 and system.habitable:
                    orbit_au = max(
                        inner_orbit_au,
                        math.sqrt(max(system.total_luminosity_solar, 0.0001)),
                    )
                    previous_orbit_au = orbit_au
                object_id = primary_id if index == 0 else f"planet-{index + 1}"
                world_type = primary_type
                habitable = system.habitable or system.colonized
                name = (
                    "Earth"
                    if system.system_id == "sol"
                    else system.world_type
                    if system.habitable or system.colonized
                    else "Inner World"
                )
            else:
                beyond_ice_line = orbit_au > 2.7 * math.sqrt(
                    max(system.total_luminosity_solar, 0.0001)
                )
                gas_giant_chance = 0.3 if beyond_ice_line else 0.08
                is_gas_giant = self.random.random() < gas_giant_chance
                if is_gas_giant:
                    world_type = "Gas giant"
                elif orbit_au < habitable_inner:
                    world_type = self.random.choice(
                        ("Scorched terrestrial", "Volcanic world", "Barren world")
                    )
                elif orbit_au > habitable_outer:
                    world_type = self.random.choice(
                        ("Frozen world", "Arid world", "Toxic world", "Barren world")
                    )
                else:
                    world_type = self.random.choice(
                        ("Barren world", "Desert world", "Ocean world", "Temperate world")
                    )
                can_support_life = (
                    not is_gas_giant
                    and not any(world.habitable for world in worlds)
                    and main_sequence_lifetime >= 4.0
                    and habitable_inner <= orbit_au <= habitable_outer
                )
                habitable = can_support_life and self.random.random() < 0.38
                if habitable:
                    world_type = self.random.choice(habitable_types)
                    object_id = "frontier"
                else:
                    object_id = f"planet-{index + 1}"
                roman_numerals = (
                    "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX"
                )
                name = f"{system.name} {roman_numerals[min(index, 8)]}"

            mass_earth = self._planet_mass(world_type, orbit_au)
            radius_earth = (
                mass_earth**0.27
                if world_type == "Gas giant"
                else mass_earth**0.28
            )
            climate = self._planet_climate(world_type)
            gravity_earth = mass_earth / radius_earth**2
            atmosphere = self._planet_atmosphere(world_type, habitable)
            surface_conditions = self._planet_surface(world_type)
            population_capacity = (
                round(max(2.0, 8.0 * radius_earth**1.5), 1)
                if habitable
                else 0.0
            )
            orbit_period_days = (
                365.25
                * math.sqrt(orbit_au**3 / max(system.total_mass_solar, 0.0001))
            )
            worlds.append(
                SystemObject(
                    object_id=object_id,
                    name=name,
                    kind="Gas giant" if world_type == "Gas giant" else "Planet",
                    orbit=0.12 + index * (0.72 / max(1, planet_count - 1)),
                    size=max(5, min(22, round(7 + math.log2(radius_earth + 1) * 2))),
                    world_type=world_type,
                    description=(
                        system.description
                        if index == 0
                        else f"A {world_type.casefold()} on the system's "
                        f"{'inner' if index < 3 else 'outer'} orbit."
                    ),
                    habitable=habitable,
                    surveyed=system.surveyed if index == 0 else False,
                    colonized=system.colonized if index == 0 else False,
                    population=system.population if index == 0 else "-",
                    resources=self._resource_deposits(
                        world_type,
                        system.metallicity_dex,
                    ),
                    orbit_au=orbit_au,
                    mass_earth=mass_earth,
                    radius_earth=radius_earth,
                    climate=climate,
                    gravity_earth=gravity_earth,
                    atmosphere=atmosphere,
                    surface_conditions=surface_conditions,
                    population_capacity_billions=population_capacity,
                    orbit_period_days=orbit_period_days,
                    owner="Union" if system.colonized and index == 0 else None,
                )
            )

        moons: list[SystemObject] = []
        moon_count = max(
            2 if is_campaign_system else 1,
            round(self.random.gauss(planet_count * 0.65, 1.0)),
        )
        giant_hosts = [world for world in worlds if world.kind == "Gas giant"]
        for moon_index in range(moon_count):
            eligible_hosts = giant_hosts or worlds[1:]
            parent = eligible_hosts[moon_index % len(eligible_hosts)]
            moon_type = self.random.choice(("Icy moon", "Airless moon", "Ocean moon"))
            moon_name = ("I", "II", "III", "IV", "V", "VI")
            moon_mass = self.random.uniform(0.001, 0.08)
            moon_radius = moon_mass**0.28
            orbit_distance = self.random.uniform(120_000, 900_000)
            parent_mass = parent.mass_earth or 1.0
            moons.append(
                SystemObject(
                    object_id=f"moon-{moon_index + 1}",
                    name=f"{parent.name} {moon_name[moon_index % len(moon_name)]}",
                    kind="Moon",
                    orbit=0.075 + (moon_index % 3) * 0.035,
                    size=self.random.randint(3, 7),
                    world_type=moon_type,
                    description="A small natural satellite shaped by tidal forces.",
                    parent_id=parent.object_id,
                    resources=self._resource_deposits(
                        moon_type,
                        system.metallicity_dex,
                    ),
                    mass_earth=moon_mass,
                    radius_earth=moon_radius,
                    gravity_earth=moon_mass / moon_radius**2,
                    climate=self._planet_climate(moon_type),
                    atmosphere=self._planet_atmosphere(moon_type, False),
                    surface_conditions=self._planet_surface(moon_type),
                    orbit_period_days=(
                        27.3
                        * (orbit_distance / 384_400) ** 1.5
                        / math.sqrt(parent_mass)
                    ),
                    orbit_distance_km=orbit_distance,
                )
            )

        objects = [*worlds, *moons]
        outermost_au = max(
            (world.orbit_au for world in worlds if world.orbit_au is not None),
            default=1.0,
        )
        outermost_au = max(1.0, outermost_au * 1.25)
        for world in worlds:
            assert world.orbit_au is not None
            world.orbit = 0.12 + (
                0.72
                * math.log1p(world.orbit_au)
                / math.log1p(outermost_au)
            )
        if is_campaign_system or self.random.random() < 0.68:
            belt_count = 1 + int(not is_campaign_system and self.random.random() < 0.18)
            for belt_index in range(belt_count):
                belt_au = outermost_au * (0.82 if belt_index else 1.0)
                objects.append(
                    SystemObject(
                        object_id="asteroid-belt" if belt_index == 0 else "inner-belt",
                        name=(
                            "Outer Asteroid Belt"
                            if belt_index == 0
                            else "Inner Asteroid Belt"
                        ),
                        kind="Asteroid belt",
                        orbit=min(
                            0.96,
                            0.12
                            + 0.72 * math.log1p(belt_au) / math.log1p(outermost_au),
                        ),
                        size=5,
                        world_type="Metal-rich debris",
                        description="A wide belt of rocky bodies, metals, and volatile ice.",
                        resources=self._resource_deposits(
                            "Metal-rich debris",
                            system.metallicity_dex,
                        ),
                        orbit_au=belt_au,
                    )
                )
        anomaly_chance = min(
            0.7,
            0.15 + system.age_gyr / 45 + max(0, system.metallicity_dex) * 0.08,
        )
        anomaly_count = (
            2
            if is_campaign_system
            else int(self.random.random() < anomaly_chance)
        )
        for anomaly_index in range(anomaly_count):
            anomaly_name, anomaly_description = self.random.choice(self._ANOMALIES)
            object_id = "deep-signal" if anomaly_index == 0 else "derelict"
            objects.append(
                SystemObject(
                    object_id=object_id,
                    name=(
                        "Unusual Signal"
                        if object_id == "deep-signal"
                        else anomaly_name
                    ),
                    kind="Anomaly",
                    orbit=0.48 if object_id == "deep-signal" else 0.92,
                    size=9,
                    world_type=anomaly_name,
                    description=anomaly_description,
                    anomaly=True,
                    resources=self._resource_deposits(
                        anomaly_name,
                        system.metallicity_dex,
                    ),
                )
            )
        if system.gateway:
            objects.append(
                SystemObject(
                    object_id="ancient-gateway",
                    name="Ancient Gateway",
                    kind="Gateway",
                    orbit=1.04,
                    size=14,
                    world_type="Precursor megastructure",
                    description=system.description,
                    anomaly=True,
                    gateway=True,
                )
            )
        return objects

    def _resource_deposits(
        self,
        body_type: str,
        metallicity_dex: float = 0.0,
    ) -> dict[str, int]:
        deposits: dict[str, int] = {}
        world = body_type.casefold()
        metal_bonus = max(-1, min(2, round(metallicity_dex * 2)))
        if "metal" in world or "asteroid" in world or "barren" in world:
            deposits["Alloys"] = max(1, self.random.randint(2, 8) + metal_bonus)
        elif self.random.random() < 0.38:
            deposits["Alloys"] = max(1, self.random.randint(1, 4) + metal_bonus)
        if "ice" in world or "frozen" in world or "ocean" in world:
            deposits["Volatiles"] = self.random.randint(1, 5)
        elif self.random.random() < 0.22:
            deposits["Volatiles"] = self.random.randint(1, 3)
        if "ruins" in world or "signal" in world or "echo" in world:
            deposits["Research"] = self.random.randint(2, 6)
        elif self.random.random() < 0.14:
            deposits["Research"] = self.random.randint(1, 3)
        return deposits

    def _stellar_properties(
        self,
        star_type: str,
        galactocentric_radius: float,
    ) -> tuple[float, float, float, float]:
        ranges = {
            "M-type": (0.08, 0.50),
            "K-type": (0.50, 0.80),
            "G-type": (0.80, 1.04),
            "F-type": (1.04, 1.40),
            "A-type": (1.40, 2.10),
            "B-type": (2.10, 16.0),
            "O-type": (16.0, 60.0),
            "Black hole": (5.0, 30.0),
            "Neutron star": (1.1, 2.2),
            "White dwarf": (0.5, 1.3),
            "Unknown": (0.80, 1.04),
        }
        lower_mass, upper_mass = ranges[star_type]
        mass = self.random.uniform(lower_mass, upper_mass)
        if star_type == "Black hole":
            luminosity = 0.0
            age = self.random.uniform(1.0, 13.8)
        elif star_type == "Neutron star":
            luminosity = self.random.uniform(0.0001, 0.01)
            age = self.random.uniform(0.01, 13.8)
        elif star_type == "White dwarf":
            luminosity = self.random.uniform(0.0001, 0.03)
            age = self.random.uniform(0.1, 13.8)
        else:
            luminosity = (
                0.23 * mass**2.3
                if mass < 0.43
                else mass**3.8
            )
            lifetime = min(13.8, 10.0 * mass**-2.5)
            age = self.random.uniform(min(0.01, lifetime), lifetime)
        metallicity_mean = 0.15 - galactocentric_radius * 1.2
        metallicity = min(0.6, max(-2.0, self.random.gauss(metallicity_mean, 0.18)))
        return mass, luminosity, age, metallicity

    def _generate_companion(self, system: StarSystem) -> None:
        if system.system_id == "sol":
            return
        binary_chance = {
            "M-type": 0.27,
            "K-type": 0.35,
            "G-type": 0.46,
            "F-type": 0.55,
            "A-type": 0.70,
            "B-type": 0.80,
            "O-type": 0.90,
            "Black hole": 0.18,
            "Neutron star": 0.12,
            "White dwarf": 0.18,
            "Unknown": 0.45,
        }[system.star_type]
        if system.system_id == "lyra" or self.random.random() < binary_chance:
            companion_mass = max(
                0.08,
                system.mass_solar * self.random.uniform(0.15, 0.95),
            )
            companion_type = self._spectral_type_for_mass(companion_mass)
            companion_luminosity = (
                0.23 * companion_mass**2.3
                if companion_mass < 0.43
                else companion_mass**3.8
            )
            system.companion_star_type = companion_type
            system.companion_mass_solar = companion_mass
            system.companion_luminosity_solar = companion_luminosity
            system.binary_separation_au = math.exp(
                self.random.uniform(math.log(0.05), math.log(20))
            )

    @staticmethod
    def _spectral_type_for_mass(mass: float) -> str:
        if mass < 0.5:
            return "M-type"
        if mass < 0.8:
            return "K-type"
        if mass < 1.04:
            return "G-type"
        if mass < 1.4:
            return "F-type"
        if mass < 2.1:
            return "A-type"
        if mass < 16:
            return "B-type"
        return "O-type"

    def _planet_mass(self, world_type: str, orbit_au: float) -> float:
        if world_type == "Gas giant":
            return self.random.lognormvariate(math.log(80), 0.8)
        if orbit_au < 0.15:
            return self.random.uniform(0.05, 1.5)
        return self.random.lognormvariate(math.log(1.2), 0.8)

    @staticmethod
    def _planet_climate(world_type: str) -> str:
        world = world_type.casefold()
        if "gas giant" in world:
            return "Deep atmosphere"
        if "ocean" in world:
            return "Oceanic"
        if "jungle" in world:
            return "Tropical"
        if "temperate" in world:
            return "Temperate"
        if "desert" in world or "arid" in world:
            return "Arid"
        if "arctic" in world or "icy" in world or "frozen" in world:
            return "Polar"
        if "volcanic" in world or "scorched" in world:
            return "Volcanic"
        if "toxic" in world:
            return "Toxic"
        if "airless" in world or "barren" in world:
            return "Airless"
        return "Mixed"

    @staticmethod
    def _planet_atmosphere(world_type: str, habitable: bool) -> str:
        world = world_type.casefold()
        if "gas giant" in world:
            return "Hydrogen-helium"
        if habitable:
            return "Breathable nitrogen-oxygen"
        if "toxic" in world:
            return "Toxic, sulfur-rich"
        if "ocean" in world or "ice" in world or "frozen" in world:
            return "Dense carbon dioxide"
        if "airless" in world or "barren" in world or "scorched" in world:
            return "No substantial atmosphere"
        return "Thin carbon dioxide"

    @staticmethod
    def _planet_surface(world_type: str) -> str:
        world = world_type.casefold()
        if "gas giant" in world:
            return "No solid surface; turbulent cloud bands"
        if "ocean" in world:
            return "Global liquid-water ocean"
        if "jungle" in world:
            return "Dense vegetation and humid lowlands"
        if "temperate" in world:
            return "Stable continents and liquid-water basins"
        if "desert" in world or "arid" in world:
            return "Dry rocky terrain and shifting dunes"
        if "arctic" in world or "icy" in world or "frozen" in world:
            return "Water-ice crust and frozen plains"
        if "volcanic" in world:
            return "Active volcanism and molten regions"
        if "scorched" in world:
            return "Baked rock and exposed impact basins"
        if "toxic" in world:
            return "Corrosive deposits and unstable terrain"
        if "airless" in world or "barren" in world:
            return "Airless rock and impact craters"
        return "Rocky terrain with varied surface features"

    def _add_wormholes(self, systems: list[StarSystem]) -> None:
        if len(systems) < 20:
            return
        pair_count = sum(
            self.random.random() < 0.006 for _ in range(len(systems))
        )
        pair_count = min(pair_count, max(1, len(systems) // 40))
        candidates = systems[16:]
        endpoints = self.random.sample(candidates, pair_count * 2)
        for pair_index in range(pair_count):
            first, second = endpoints[pair_index * 2 : pair_index * 2 + 2]
            for system, destination in ((first, second), (second, first)):
                system.objects.append(
                    SystemObject(
                        object_id="wormhole" if pair_index == 0 else f"wormhole-{pair_index + 1}",
                        name="Unstable Wormhole",
                        kind="Wormhole",
                        orbit=1.08,
                        size=12,
                        world_type="Spacetime anomaly",
                        description=(
                            f"A traversable spatial tunnel appears to lead to "
                            f"{destination.name}."
                        ),
                        anomaly=True,
                        linked_system_id=destination.system_id,
                    )
                )

    def _generate_routes(
        self,
        systems: list[StarSystem],
    ) -> tuple[tuple[str, str], ...]:
        candidates = sorted(
            (
                math.dist((first.x, first.y), (second.x, second.y)),
                first.system_id,
                second.system_id,
            )
            for index, first in enumerate(systems)
            for second in systems[index + 1 :]
        )
        parents = {system.system_id: system.system_id for system in systems}

        def find(system_id: str) -> str:
            while parents[system_id] != system_id:
                parents[system_id] = parents[parents[system_id]]
                system_id = parents[system_id]
            return system_id

        routes: list[tuple[str, str]] = []
        for _, first_id, second_id in candidates:
            first_root = find(first_id)
            second_root = find(second_id)
            if first_root != second_root:
                parents[first_root] = second_root
                routes.append((first_id, second_id))

        existing = {frozenset(route) for route in routes}
        maximum_distance = 0.17 if self.settings.size == "small" else 0.13
        for distance, first_id, second_id in candidates:
            route = frozenset((first_id, second_id))
            if distance <= maximum_distance and route not in existing:
                routes.append((first_id, second_id))
                existing.add(route)
        return tuple(routes)

    def _generate_nebulae(self) -> tuple[Nebula, ...]:
        count = max(1, self.SYSTEM_COUNTS[self.settings.size] // 24)
        nebulae = []
        for index in range(count):
            if self.settings.shape == "spiral":
                arm = self.random.randrange(4)
                radius = self.random.uniform(0.12, 0.43)
                angle = (
                    arm * math.tau / 4
                    + math.log(radius / 0.04) / math.tan(math.radians(13))
                    + self.random.gauss(0, 0.12)
                )
                x = 0.5 + math.cos(angle) * radius
                y = 0.5 + math.sin(angle) * radius * 0.72
            elif self.settings.shape == "elliptical":
                radius = min(0.43, self.random.gammavariate(2.0, 0.10))
                angle = self.random.random() * math.tau
                x = 0.5 + math.cos(angle) * radius
                y = 0.5 + math.sin(angle) * radius * 0.82
            else:
                x = self.random.gauss(self.random.choice((0.26, 0.49, 0.74)), 0.08)
                y = self.random.gauss(self.random.choice((0.30, 0.52, 0.73)), 0.08)
            nebulae.append(
                Nebula(
                    name=self.random.choice(self._NEBULA_NAMES),
                    x=min(0.9, max(0.1, x)),
                    y=min(0.9, max(0.1, y)),
                    radius=self.random.uniform(0.035, 0.09),
                )
            )
        return tuple(nebulae)

    def _star_type(self) -> str:
        value = self.random.random()
        for star_type, weight in self._STAR_WEIGHTS:
            value -= weight
            if value <= 0:
                return star_type
        return "M-type"

    def _new_star_name(self, used_names: set[str]) -> str:
        while True:
            name = self.random.choice(self._STAR_NAMES)
            if self.random.random() < 0.5:
                name = f"{name} {self.random.choice(('A', 'B', 'C', 'Prime'))}"
            if name not in used_names:
                return name
