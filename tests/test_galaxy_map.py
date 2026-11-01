from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pygame
import pytest

from nova.campaign import Campaign
from nova.config import Config
from nova.graphics import GameWindow


@pytest.fixture(params=((1280, 720), (800, 480)))
def game_window(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> Iterator[GameWindow]:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    screen = pygame.display.set_mode(request.param)
    campaign = Campaign(seed=2480)
    window = GameWindow(
        SimpleNamespace(campaign=campaign),
        Config(asset_path=Path(__file__).resolve().parents[1] / "assets"),
    )
    window.screen = screen
    window._bounds = screen.get_rect()
    window._bounds.y = 54
    window._bounds.height -= 54
    window._build_ui()
    yield window
    window.assets.clear()
    pygame.quit()


def test_galaxy_zoom_keeps_the_cursor_location_fixed(game_window: GameWindow) -> None:
    window = game_window
    window._galaxy_zoom = 0.9
    position = window._map_position("sol")

    window._zoom_galaxy_map(0.08, position)

    assert window._map_position("sol") == position
    assert window._galaxy_zoom == pytest.approx(0.98)


def test_galaxy_pan_is_clamped_and_map_draws(game_window: GameWindow) -> None:
    window = game_window
    window._galaxy_zoom = 1.3
    window._map_pan.update(10_000, -10_000)
    window._clamp_map_pan()
    bounds = window._map_rect()
    maximum_pan = pygame.Vector2(bounds.size) * ((1 - window._GALAXY_ZOOM_MIN) / 2)

    assert abs(window._map_pan.x) <= maximum_pan.x
    assert abs(window._map_pan.y) <= maximum_pan.y

    window._draw_galaxy_map()
    window._draw_map_card()


def test_clicking_a_star_selects_it_without_leaving_galaxy_map(
    game_window: GameWindow,
) -> None:
    window = game_window
    position = window._map_position("asterion")

    assert window._select_map_item(position)
    assert window._selected_system == "asterion"
    assert window.tabs is not None
    assert window.tabs.active == "GALAXY"
    window.application.campaign.get_object(
        window._selected_system,
        window._selected_object,
    )


def test_map_layer_controls_toggle_from_the_map(game_window: GameWindow) -> None:
    window = game_window
    assert window.screen is not None
    assert window.tabs is not None
    window._draw_galaxy_map()
    _, _, fog_button = next(
        entry
        for entry in window._map_layer_button_rects(window._map_rect())
        if entry[0] == "_fog_of_war"
    )
    pygame.event.clear()
    pygame.event.post(
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            button=1,
            pos=fog_button.center,
        )
    )

    window._handle_events()

    assert window._fog_of_war
    assert window.tabs.active == "GALAXY"


def test_galaxy_map_layers_render_and_fog_hides_unexplored_systems(
    game_window: GameWindow,
) -> None:
    window = game_window
    campaign = window.application.campaign
    window._show_borders = True
    window._show_fleets = True
    window._show_trade_routes = True
    window._show_resources = True
    window._show_sensors = True
    window._show_exploration = True

    trade_edges = window._trade_route_edges()
    assert trade_edges
    assert len(trade_edges) > 1
    assert trade_edges.issubset(
        {tuple(sorted(route)) for route in campaign.routes}
    )
    window._draw_galaxy_map()

    window._fog_of_war = True
    hidden = next(
        system
        for system in campaign.systems
        if not window._is_system_visible(system)
    )
    assert not window._select_map_item(window._map_position(hidden.system_id))
    assert campaign.fleets[0].system_id == "sol"


def test_territory_layer_draws_regions_for_owned_systems(
    game_window: GameWindow,
) -> None:
    window = game_window
    bounds = window._map_rect()
    polygons, borders = window._territory_geometry(bounds)

    assert polygons
    assert {owner for owner, _ in polygons} >= {"Union", "Veyran Compact"}
    assert borders
    assert window._owner_route_edges()["Union"]
    window._draw_territory_layer(bounds, window.application.campaign.systems)

    window.application.campaign.get_system("new-carthage").owner = "Sovereign Reach"
    polygons, _ = window._territory_geometry(bounds)
    assert {owner for owner, _ in polygons} == {
        "Union",
        "Sovereign Reach",
        "Veyran Compact",
    }
    window._draw_territory_layer(bounds, window.application.campaign.systems)


def test_territory_layer_can_be_toggled_with_p(game_window: GameWindow) -> None:
    window = game_window
    assert window._show_borders
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p, mod=0))

    window._handle_events()

    assert not window._show_borders


def test_fog_toggle_hides_unknown_selection_and_filters_system_list(
    game_window: GameWindow,
) -> None:
    window = game_window
    campaign = window.application.campaign
    hidden = next(
        system
        for system in campaign.systems
        if not system.surveyed and system.system_id not in window._sensor_system_ids()
    )
    window._selected_system = hidden.system_id
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_f, mod=0))

    window._handle_events()

    assert window._fog_of_war
    assert window._is_system_visible(
        campaign.get_system(window._selected_system)
    )
    campaign.get_object(window._selected_system, window._selected_object)
    assert window.systems is not None
    assert all(
        window._is_system_visible(
            next(system for system in campaign.systems if system.name == row[0])
        )
        for row in window.systems.rows
    )


def test_map_search_filters_and_centers_a_system(game_window: GameWindow) -> None:
    window = game_window
    assert window.search is not None
    assert window.dropdown is not None
    window.search.text = "Asterion"

    assert window._map_filter_matches(window.application.campaign.get_system("asterion"))
    assert not window._map_filter_matches(window.application.campaign.get_system("sol"))
    assert window._search_map()
    assert window._selected_system == "asterion"
    window.application.campaign.get_object(
        window._selected_system,
        window._selected_object,
    )

    window.search.text = ""
    window.dropdown.selected = "Colonized"
    assert window._map_filter_matches(window.application.campaign.get_system("sol"))
    assert not window._map_filter_matches(window.application.campaign.get_system("asterion"))


def test_map_bookmarks_can_be_added_removed_and_visited(
    game_window: GameWindow,
) -> None:
    window = game_window
    campaign = window.application.campaign
    window._selected_system = "asterion"

    window._toggle_map_bookmark()
    assert campaign.map_bookmarks == ["asterion"]

    window._selected_system = "sol"
    window._jump_to_next_bookmark()
    assert window._selected_system == "asterion"
    campaign.get_object(window._selected_system, window._selected_object)

    window._toggle_map_bookmark()
    assert campaign.map_bookmarks == []


def test_planet_management_and_history_views_render(game_window: GameWindow) -> None:
    window = game_window
    assert window.screen is not None
    assert window.systems is not None
    window.tabs.active = "SYSTEM"
    window._selected_system = "sol"
    window._selected_object = "earth"

    window._planet_view = "MANAGEMENT"
    window._draw_object_details(window.ui.fonts.get(18), compact=False)

    window._planet_view = "HISTORY"
    window._draw_object_details(window.ui.fonts.get(18), compact=False)

    window._planet_view = "DETAILS"
    window._draw_object_details(window.ui.fonts.get(18), compact=False)


def test_empire_screen_builds_and_renders_species_art(game_window: GameWindow) -> None:
    window = game_window
    assert window.tabs is not None
    assert window.dropdown is not None
    window.tabs.active = "EMPIRE"
    window._filter_content()
    window._layout_ui()

    window._draw_empire(window.ui.fonts.get(14), compact=False)
    window.dropdown.selected = "Hydroponics Bay"
    window._perform_selected_action()

    assert window.application.campaign.player_colonies[0].construction == "hydroponics"
    assert window.research_button is not None
    assert window.create_fleet_button is not None
    assert window.move_fleet_button is not None


def test_main_menu_renders_portraits_and_starts_selected_species(
    game_window: GameWindow,
) -> None:
    window = game_window
    clock = SimpleNamespace(
        pause=lambda: None,
        resume=lambda: None,
    )
    window.application.engine = SimpleNamespace(clock=clock)
    window.application.new_game = lambda species_id: setattr(
        window.application,
        "campaign",
        Campaign(player_species_id=species_id),
    )

    window._show_main_menu()
    window._selected_species_id = "auralith"
    window._draw()
    window._start_new_game()

    assert not window._menu_active
    assert window.application.campaign.player_species_id == "auralith"


def test_diplomacy_screen_explains_first_contact_and_offers_actions(
    game_window: GameWindow,
) -> None:
    window = game_window
    campaign = window.application.campaign
    assert window.tabs is not None
    assert window.dropdown is not None
    assert window.diplomatic_action is not None
    window.tabs.active = "DIPLOMACY"
    window._filter_content()
    assert window.dropdown.rect.height > 1
    assert window.diplomatic_action.rect.height > 1
    assert window.action_button is not None
    assert window.action_button.rect.height > 1
    window._draw_diplomacy(window.ui.fonts.get(14))

    assert window.diplomatic_action.options == [
        "First contact pending - survey their space"
    ]
    campaign.perform_action("morrow")
    window._draw_diplomacy(window.ui.fonts.get(14))

    assert "Send envoy" in window.diplomatic_action.options
    assert "Propose non-aggression pact" in window.diplomatic_action.options
    window.diplomatic_action.selected = "Propose non-aggression pact"
    window._perform_diplomatic_action()
    assert "non_aggression" in campaign.get_relation("veyra").treaties


def test_campaign_news_reaches_the_player_without_duplicate_action_alerts(
    game_window: GameWindow,
) -> None:
    window = game_window
    campaign = window.application.campaign

    campaign.perform_action("morrow")
    expected_messages = {
        event.split("  ", 1)[-1]
        for event in campaign.log[-2:]
    }
    window.ui.notify(campaign.log[-1].split("  ", 1)[-1])
    window._poll_campaign_news()
    assert {
        notification.message
        for notification in window.ui.notifications
    } == expected_messages

    window._poll_campaign_news()
    assert len(window.ui.notifications) == 2


def test_planet_management_and_history_keyboard_controls(
    game_window: GameWindow,
) -> None:
    window = game_window
    assert window.tabs is not None
    window.tabs.active = "SYSTEM"
    for key, expected in (
        (pygame.K_m, "MANAGEMENT"),
        (pygame.K_h, "HISTORY"),
        (pygame.K_d, "DETAILS"),
    ):
        pygame.event.clear()
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0))
        window._handle_events()
        assert window._planet_view == expected
