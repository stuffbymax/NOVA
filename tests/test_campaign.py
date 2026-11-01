import pytest

from nova.campaign import Campaign


def test_survey_reveals_world_and_records_findings() -> None:
    campaign = Campaign()

    message = campaign.perform_action("asterion")

    assert "Jungle world" in message
    assert campaign.get_system("asterion").surveyed
    assert campaign.science == 20
    assert campaign.alloys == 55
    assert "Survey complete: Asterion" in campaign.log[-1]


def test_colony_requires_survey_and_spends_resources() -> None:
    campaign = Campaign()
    campaign.perform_action("asterion")

    message = campaign.perform_action("asterion")

    assert "Colony founded" in message
    assert campaign.get_system("asterion").population == "1.2B"
    assert campaign.alloys == 33
    assert campaign.influence == 5
    assert campaign.get_system("asterion").owner == "Union"


def test_gateway_and_two_frontier_colonies_complete_objective() -> None:
    campaign = Campaign()
    campaign.perform_action("asterion")
    campaign.perform_action("asterion")
    campaign.perform_action("vesper")
    campaign.perform_action("vesper")
    campaign.perform_action("eidolon")
    campaign.perform_action("eidolon")

    assert campaign.gateway_studied
    assert campaign.objective_complete
    assert "Frontier secured" in campaign.objective


def test_union_owns_initial_colonies_and_starts_with_a_survey_fleet() -> None:
    campaign = Campaign()

    assert campaign.get_system("sol").owner == "Union"
    assert campaign.get_system("new-carthage").owner == "Union"
    assert len(campaign.fleets) == 1
    assert campaign.fleets[0].system_id == "sol"


def test_campaign_rejects_actions_without_resources() -> None:
    campaign = Campaign()
    campaign.science = 0

    with pytest.raises(ValueError, match="Not enough science"):
        campaign.perform_action("asterion")

    with pytest.raises(KeyError, match="Unknown star system"):
        campaign.perform_action("unknown")


def test_campaign_income_advances_only_with_simulated_time() -> None:
    campaign = Campaign()
    initial_alloys = campaign.alloys
    initial_date = campaign.date_label

    campaign.advance(10)

    expected_income = 10 * (0.12 + max(0, campaign.colonies - 1) * 0.08)
    assert campaign.alloys == pytest.approx(initial_alloys + expected_income)
    assert campaign.date_label != initial_date
    with pytest.raises(ValueError, match="cannot be negative"):
        campaign.advance(-1)


def test_each_system_contains_multiple_individual_objects() -> None:
    campaign = Campaign()

    assert len(campaign.systems) >= 16
    assert all(len(system.objects) >= 6 for system in campaign.systems[:16])
    assert all(
        sum(obj.kind in ("Planet", "Gas giant") for obj in system.objects) >= 3
        for system in campaign.systems
    )
    assert all(
        len({system_object.object_id for system_object in system.objects})
        == len(system.objects)
        for system in campaign.systems
    )


def test_object_survey_and_anomaly_investigation_are_separate_actions() -> None:
    campaign = Campaign()

    survey_message = campaign.perform_object_action("asterion", "deep-signal")
    assert "Anomaly detected" in survey_message
    assert campaign.get_object("asterion", "deep-signal").surveyed
    assert not campaign.get_object("asterion", "deep-signal").anomaly_resolved

    investigation_message = campaign.perform_object_action(
        "asterion",
        "deep-signal",
    )
    assert "Anomaly resolved" in investigation_message
    assert campaign.get_object("asterion", "deep-signal").anomaly_resolved


def test_surveyed_deposits_are_added_to_resource_stockpiles() -> None:
    campaign = Campaign(seed=512)
    belt = campaign.get_object("asterion", "asteroid-belt")
    initial_alloys = campaign.alloys
    initial_volatiles = campaign.volatiles
    expected_alloys = belt.resources.get("Alloys", 0)
    expected_volatiles = belt.resources.get("Volatiles", 0)

    campaign.perform_object_action("asterion", "asteroid-belt")

    assert campaign.alloys == initial_alloys + 2 + expected_alloys
    assert campaign.volatiles == initial_volatiles + expected_volatiles


def test_habitable_object_can_be_colonized_independently() -> None:
    campaign = Campaign()
    target = campaign.get_object("asterion", "frontier")
    target.surveyed = True
    campaign.get_system("asterion").surveyed = True

    message = campaign.perform_object_action("asterion", "frontier")

    assert "Colony founded" in message
    assert target.colonized
    assert campaign.get_system("asterion").colonized
    assert target.owner == "Union"
    assert campaign.get_system("asterion").owner == "Union"
    assert any("Colony founded" in event for event in target.history)


def test_planetary_data_includes_environment_gravity_and_population_capacity() -> None:
    campaign = Campaign(seed=941, size="large")

    for system in campaign.systems:
        planets = system.planets
        assert planets
        assert all(
            planet.mass_earth is not None
            and planet.radius_earth is not None
            and planet.gravity_earth == pytest.approx(
                planet.mass_earth / planet.radius_earth**2
            )
            for planet in planets
        )
        assert all(
            planet.climate != "Unknown"
            and planet.atmosphere != "Unknown"
            and planet.surface_conditions != "Unknown"
            and planet.orbit_period_days is not None
            for planet in planets
        )
        assert all(
            planet.population_capacity_billions > 0
            for planet in planets
            if planet.habitable
        )
        assert all(
            planet.population_capacity_billions == 0
            for planet in planets
            if not planet.habitable
        )

        for moon in system.moons:
            assert moon.parent_id in {planet.object_id for planet in planets}
            assert moon.orbit_distance_km is not None
            assert moon.orbit_period_days is not None
            assert moon.gravity_earth is not None


def test_initial_planet_ownership_and_history_match_colony_state() -> None:
    campaign = Campaign()
    earth = campaign.get_object("sol", "earth")
    uncolonized = campaign.get_object("asterion", "frontier")

    assert earth.owner == "Union"
    assert earth.history
    assert uncolonized.owner is None
    assert uncolonized.history == []


def test_planet_survey_is_recorded_in_planetary_history() -> None:
    campaign = Campaign()

    campaign.perform_object_action("asterion", "frontier")

    frontier = campaign.get_object("asterion", "frontier")
    assert frontier.surveyed
    assert any("Survey completed" in event for event in frontier.history)


def test_galaxy_generation_is_reproducible_from_seed() -> None:
    first = Campaign(seed=731)
    second = Campaign(seed=731)

    assert first.galaxy.name == second.galaxy.name
    assert first.galaxy.shape == second.galaxy.shape
    assert first.galaxy.routes == second.galaxy.routes
    assert [
        (system.system_id, system.x, system.y, system.star_type, system.world_type)
        for system in first.systems
    ] == [
        (system.system_id, system.x, system.y, system.star_type, system.world_type)
        for system in second.systems
    ]
    assert [
        [
            (
                obj.object_id,
                obj.name,
                obj.kind,
                obj.orbit,
                obj.world_type,
                obj.resources,
            )
            for obj in system.objects
        ]
        for system in first.systems
    ] == [
        [
            (
                obj.object_id,
                obj.name,
                obj.kind,
                obj.orbit,
                obj.world_type,
                obj.resources,
            )
            for obj in system.objects
        ]
        for system in second.systems
    ]


def test_different_seeds_generate_different_galaxies() -> None:
    first = Campaign(seed=731)
    second = Campaign(seed=732)

    assert [(system.x, system.y) for system in first.systems] != [
        (system.x, system.y) for system in second.systems
    ]


@pytest.mark.parametrize(
    ("size", "expected_systems"),
    (("small", 24), ("medium", 48), ("large", 80)),
)
def test_galaxy_size_controls_generated_star_count(
    size: str,
    expected_systems: int,
) -> None:
    campaign = Campaign(seed=88, size=size)

    assert len(campaign.systems) == expected_systems
    assert campaign.galaxy.size == size


@pytest.mark.parametrize("shape", ("spiral", "elliptical", "irregular"))
def test_galaxy_shape_is_stored_and_coordinates_are_bounded(shape: str) -> None:
    campaign = Campaign(seed=901, shape=shape)

    assert campaign.galaxy.shape == shape
    assert all(0.03 <= system.x <= 0.97 for system in campaign.systems)
    assert all(0.03 <= system.y <= 0.97 for system in campaign.systems)
    assert campaign.galaxy.nebulae
    system = campaign.get_system("asterion")
    x_light_years, y_light_years = campaign.galaxy.position_light_years(system)
    assert x_light_years == pytest.approx(
        (system.x - 0.5) * campaign.galaxy.diameter_light_years
    )
    vertical_scale = {"spiral": 0.72, "elliptical": 0.82, "irregular": 1.0}[shape]
    assert y_light_years == pytest.approx(
        (system.y - 0.5) * campaign.galaxy.diameter_light_years * vertical_scale
    )
    x_3d, y_3d, z_3d = campaign.galaxy.position_3d_light_years(system)
    assert (x_3d, y_3d) == pytest.approx((x_light_years, y_light_years))
    assert z_3d == pytest.approx(system.z * campaign.galaxy.diameter_light_years)


def test_galaxy_morphologies_generate_different_map_layouts() -> None:
    layouts = {
        shape: [
            (system.x, system.y)
            for system in Campaign(seed=901, shape=shape).systems
        ]
        for shape in ("spiral", "elliptical", "irregular")
    }

    assert len({tuple(layout) for layout in layouts.values()}) == 3


def test_generated_routes_connect_every_system_and_wormholes_are_paired() -> None:
    campaign = Campaign(seed=2480)
    connections = {system.system_id: set() for system in campaign.systems}
    for first, second in campaign.routes:
        connections[first].add(second)
        connections[second].add(first)

    reached = {"sol"}
    pending = ["sol"]
    while pending:
        for neighbor in connections[pending.pop()]:
            if neighbor not in reached:
                reached.add(neighbor)
                pending.append(neighbor)

    assert reached == set(connections)
    wormholes = [
        (system, obj)
        for system in campaign.systems
        for obj in system.objects
        if obj.kind == "Wormhole"
    ]
    assert len(wormholes) % 2 == 0
    for system, wormhole in wormholes:
        destination = campaign.get_system(wormhole.linked_system_id)
        matching = next(obj for obj in destination.objects if obj.kind == "Wormhole")
        assert matching.linked_system_id == system.system_id
        assert matching.object_id == wormhole.object_id


def test_generated_stars_and_planets_have_plausible_physical_properties() -> None:
    campaign = Campaign(seed=941, size="large")
    generated_systems = campaign.systems[16:]

    assert all(system.mass_solar > 0 for system in campaign.systems)
    assert all(0 < system.age_gyr <= 13.8 for system in campaign.systems)
    assert campaign.get_system("sol").mass_solar == 1
    assert campaign.get_system("sol").luminosity_solar == 1
    for system in generated_systems:
        worlds = [
            obj for obj in system.objects if obj.kind in ("Planet", "Gas giant")
        ]
        assert all(obj.mass_earth > 0 and obj.radius_earth > 0 for obj in worlds)
        orbits = [obj.orbit_au for obj in worlds]
        assert orbits == sorted(orbits)
        assert len({obj.name for obj in worlds}) == len(worlds)
        for world in worlds:
            if world.habitable:
                habitable_inner = 0.95 * system.total_luminosity_solar**0.5
                habitable_outer = 1.67 * system.total_luminosity_solar**0.5
                assert habitable_inner <= world.orbit_au <= habitable_outer
                largest_star = max(system.mass_solar, system.companion_mass_solar)
                assert largest_star <= 2.0
                assert 10 * largest_star**-2.5 >= 4
        if system.binary_separation_au is not None:
            assert all(
                world.orbit_au >= system.binary_separation_au * 2.5
                for world in worlds
            )


def test_real_galaxy_names_match_morphology_and_can_be_selected() -> None:
    campaign = Campaign(
        seed=3,
        galaxy_name="Large Magellanic Cloud",
        shape="irregular",
    )

    assert campaign.galaxy.name == "Large Magellanic Cloud"
    assert campaign.galaxy.morphology == "irregular"
    assert campaign.galaxy.diameter_light_years == 32_000

    with pytest.raises(ValueError, match="does not have spiral morphology"):
        Campaign(galaxy_name="Messier 87 (Virgo A)")


def test_stellar_types_are_weighted_toward_long_lived_red_dwarfs() -> None:
    campaign = Campaign(seed=42, size="large")
    generated_types = [
        system.star_type for system in campaign.systems[16:]
    ]

    assert generated_types.count("M-type") > len(generated_types) * 0.55
    assert all(system.star_type != "Unknown" for system in campaign.systems[16:])
    assert campaign.get_system("sol").age_gyr == 4.57
    assert campaign.get_system("sol").binary_separation_au is None


@pytest.mark.parametrize(
    ("settings", "message"),
    (
        ({"size": "giant"}, "Unknown galaxy size"),
        ({"shape": "ring"}, "Unknown galaxy shape"),
    ),
)
def test_galaxy_generation_rejects_unknown_settings(
    settings: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        Campaign(**settings)
