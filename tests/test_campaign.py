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


def test_species_choice_drives_colonist_biology() -> None:
    campaign = Campaign(player_species_id="auralith")
    colony = campaign.player_colonies[0]

    assert colony.species_id == "auralith"
    assert campaign.species_catalog[colony.species_id].lifespan_years == 240


def test_population_growth_uses_species_rate_and_planet_capacity() -> None:
    campaign = Campaign()
    colony = campaign.player_colonies[0]
    planet = campaign.get_object(colony.system_id, colony.planet_id)
    initial_population = colony.population_billions

    campaign.advance(365)

    assert colony.population_billions > initial_population
    assert colony.population_billions <= planet.population_capacity_billions
    assert colony.happiness > 0


def test_building_construction_spends_alloys_and_adds_production() -> None:
    campaign = Campaign()
    colony = campaign.player_colonies[0]
    initial_alloys = campaign.alloys
    initial_food = campaign.food

    campaign.build_building(colony.system_id, colony.planet_id, "hydroponics")

    assert campaign.alloys == initial_alloys - 12
    assert colony.construction == "hydroponics"
    campaign.advance(18)
    assert "hydroponics" in colony.buildings
    campaign.advance(1)
    assert campaign.food > initial_food


def test_research_unlocks_technology_and_gates_buildings() -> None:
    campaign = Campaign()
    colony = campaign.player_colonies[0]

    with pytest.raises(ValueError, match="Required technology"):
        campaign.build_building(colony.system_id, colony.planet_id, "fusion")
    campaign.build_building(colony.system_id, colony.planet_id, "research")
    campaign.advance(28)
    campaign.start_research("field-survey")
    campaign.advance(100)

    assert "field-survey" in campaign.researched_technologies
    assert campaign.start_research("fusion-power") == "Research begun: Controlled Fusion."
    campaign.advance(130)
    assert "fusion" in campaign.building_options()
    assert "shipyard" not in campaign.building_options()


def test_fleets_follow_routes_and_arrive_at_the_ordered_system() -> None:
    campaign = Campaign()
    fleet = campaign.fleets[0]

    campaign.move_fleet(fleet.fleet_id, "asterion")
    total_days = fleet.days_to_arrival
    previous = fleet.system_id
    for next_system in fleet.route:
        total_days += campaign._jump_duration(previous, next_system)
        previous = next_system
    campaign.advance(total_days + 1)

    assert fleet.system_id == "asterion"
    assert fleet.route == []


def test_fleet_position_changes_during_interstellar_travel() -> None:
    campaign = Campaign()
    fleet = campaign.fleets[0]
    campaign.move_fleet(fleet.fleet_id, "asterion")
    initial_position = campaign.fleet_position(fleet)

    campaign.advance(fleet.days_to_arrival / 2)

    assert campaign.fleet_position(fleet) != initial_position
    assert fleet.system_id == "sol"


def test_player_can_commission_fleets_with_a_valid_cost() -> None:
    campaign = Campaign()
    initial_alloys = campaign.alloys

    fleet = campaign.create_fleet("Second Survey Group")

    assert fleet.name == "Second Survey Group"
    assert fleet.ship_count > 0
    assert len(campaign.fleets) == 2
    assert campaign.alloys == initial_alloys - 35


def test_ai_empire_expands_deterministically() -> None:
    first = Campaign(seed=238)
    second = Campaign(seed=238)
    initial_systems = len(first.ai_empires[0].system_ids)

    first.advance(400)
    second.advance(400)

    assert len(first.ai_empires[0].system_ids) == initial_systems + 1
    assert first.ai_empires[0].system_ids == second.ai_empires[0].system_ids


def test_surveying_rival_space_establishes_first_contact() -> None:
    campaign = Campaign()
    relation = campaign.get_relation("veyra")

    message = campaign.perform_action("morrow")

    assert relation.first_contact
    assert "First contact established" in message
    assert relation.opinion == 0


def test_diplomatic_pacts_change_opinion_and_production() -> None:
    campaign = Campaign()
    campaign.perform_action("morrow")
    relation = campaign.get_relation("veyra")
    initial_energy = campaign.energy

    campaign.propose_treaty("veyra", "non_aggression")
    assert "non_aggression" in relation.treaties
    campaign.propose_treaty("veyra", "trade")
    campaign.propose_treaty("veyra", "research")
    campaign.advance(10)

    assert relation.opinion == 15
    assert campaign.energy > initial_energy
    assert campaign.research_points > 0


def test_treaty_requires_contact_and_prerequisites() -> None:
    campaign = Campaign()

    with pytest.raises(ValueError, match="First contact"):
        campaign.propose_treaty("veyra", "trade")
    campaign.perform_action("morrow")
    with pytest.raises(ValueError, match="non-aggression pact is required"):
        campaign.propose_treaty("veyra", "defensive_alliance")


def test_envoy_improves_opinion_with_influence_and_has_cooldown() -> None:
    campaign = Campaign()
    campaign.perform_action("morrow")
    initial_influence = campaign.influence

    campaign.send_envoy("veyra")

    assert campaign.influence == initial_influence - 1
    assert campaign.get_relation("veyra").opinion == 15
    with pytest.raises(ValueError, match="once per year"):
        campaign.send_envoy("veyra")


def test_active_agreements_must_be_broken_before_war() -> None:
    campaign = Campaign()
    campaign.perform_action("morrow")
    campaign.propose_treaty("veyra", "non_aggression")

    with pytest.raises(ValueError, match="Break active treaties"):
        campaign.declare_war("veyra")
    campaign.break_treaty("veyra", "non_aggression")

    assert campaign.declare_war("veyra").endswith("declared war on the Veyran Compact.")


def test_war_requires_contact_and_fleet_moves_capture_hostile_systems() -> None:
    campaign = Campaign()
    with pytest.raises(ValueError, match="First contact"):
        campaign.declare_war("veyra")
    campaign.perform_action("morrow")
    campaign.alloys = 100
    first = campaign.fleets[0]
    second = campaign.create_fleet("Second Squadron")
    campaign.declare_war("veyra")
    campaign.move_fleet(first.fleet_id, "morrow")
    campaign.move_fleet(second.fleet_id, "morrow")
    travel_days = max(
        sum(
            campaign._jump_duration(start, destination)
            for start, destination in zip(
                [fleet.system_id, *fleet.route[:-1]],
                fleet.route,
            )
        )
        for fleet in (first, second)
    )

    campaign.advance(travel_days + 1)

    assert campaign.get_system("morrow").owner == "Union"
    assert any("Battle of Morrow" in event for event in campaign.log)
    assert len(campaign.ai_empires[0].system_ids) == 0
    assert first.ship_count > 0 or second.ship_count > 0


def test_rival_fleet_retaliates_during_war() -> None:
    campaign = Campaign()
    campaign.perform_action("morrow")
    campaign.declare_war("veyra")

    campaign.advance(1)

    assert campaign.ai_fleets[0].route
    assert campaign.ai_fleets[0].destination_id in {
        system.system_id
        for system in campaign.systems
        if system.owner == "Union"
    }


def test_war_can_end_with_peace_after_system_is_captured() -> None:
    campaign = Campaign()
    campaign.perform_action("morrow")
    campaign.alloys = 100
    fleet = campaign.fleets[0]
    campaign.create_fleet("Second Squadron")
    campaign.declare_war("veyra")
    campaign.move_fleet(fleet.fleet_id, "morrow")
    relation = campaign.get_relation("veyra")
    message = campaign.negotiate_peace("veyra")

    assert "rejected" in message
    assert relation.at_war
    campaign.elapsed_days = 200
    message = campaign.negotiate_peace("veyra")

    assert "ceasefire" in message
    assert not relation.at_war


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


def test_player_cannot_colonize_a_rival_empire_system() -> None:
    campaign = Campaign()
    rival = campaign.get_system("morrow")
    target = next(planet for planet in rival.planets if planet.habitable)
    target.surveyed = True
    target.colonized = False

    with pytest.raises(ValueError, match="controlled by Veyran Compact"):
        campaign.perform_object_action(rival.system_id, target.object_id)


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
