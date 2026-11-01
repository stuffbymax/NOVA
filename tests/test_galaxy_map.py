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


def test_clicking_a_star_opens_its_system(game_window: GameWindow) -> None:
    window = game_window
    position = window._map_position("asterion")

    assert window._select_map_item(position)
    assert window._selected_system == "asterion"
    assert window.tabs is not None
    assert window.tabs.active == "SYSTEM"
