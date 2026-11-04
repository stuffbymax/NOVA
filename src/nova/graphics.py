"""Pygame window and the first interactive NOVA map presentation."""

from collections import deque
import logging
import math
import random

import pygame

from .application import Application
from .assets import AssetError, AssetManager
from .campaign import Campaign, ColonyState, StarSystem, SystemObject
from .config import Config
from .persistence import SaveError
from .ui import (
    Button,
    Dropdown,
    FocusableWidget,
    TableWidget,
    TabBar,
    TextInput,
    Theme,
    UIManager,
    UIWindow,
    WindowManager,
)


logger = logging.getLogger(__name__)


class GameWindow:
    """Owns pygame resources and translates input into campaign actions."""

    _SPEEDS = (0.5, 1.0, 2.0, 4.0)
    _GALAXY_ZOOM_MIN = 0.35
    _GALAXY_ZOOM_MAX = 1.5

    def __init__(self, application: Application, config: Config) -> None:
        self.application = application
        self.config = config
        self.assets = AssetManager(config.asset_path)
        self.screen: pygame.Surface | None = None
        self._clock = pygame.time.Clock()
        self._running = False
        self._observed_campaign = application.campaign
        self._known_campaign_events = list(application.campaign.log)
        self._menu_active = False
        self._menu_message = ""
        self._selected_species_id = application.campaign.player_species_id
        self._selected_name_culture = "all"
        self._menu_buttons: list[Button] = []
        self._species_card_rects: dict[str, pygame.Rect] = {}
        self._name_culture_rect = pygame.Rect(0, 0, 1, 1)
        self._species_destination: Dropdown | None = None
        self._fullscreen = config.fullscreen
        self._windowed_size = (config.window_width, config.window_height)
        self._speed_index = 1
        self._selected_system = "sol"
        self._selected_object = "earth"
        self._planet_view = "DETAILS"
        self._species_selected_colony: tuple[str, str] | None = None
        self._active_tab = "GALAXY"
        self._galaxy_zoom = 0.9
        self._system_zoom = 0.92
        self._map_pan = pygame.Vector2()
        self._map_dragging = False
        self._show_borders = True
        self._show_fleets = True
        self._show_trade_routes = True
        self._show_resources = False
        self._show_sensors = False
        self._fog_of_war = False
        self._show_exploration = False
        self._territory_cache_key: tuple[object, ...] | None = None
        self._territory_polygons: list[
            tuple[str, tuple[tuple[float, float], ...]]
        ] = []
        self._territory_edges: list[
            tuple[str, tuple[float, float], tuple[float, float]]
        ] = []
        self._owner_route_cache_key: tuple[object, ...] | None = None
        self._owner_route_cache: dict[str, set[tuple[str, str]]] = {}
        self._nebula_cache: dict[
            tuple[tuple[int, int], tuple[int, int, int]], pygame.Surface
        ] = {}
        self._planet_illustration_cache: dict[
            tuple[str, str, str, tuple[int, int]], pygame.Surface
        ] = {}
        self._bounds = pygame.Rect(0, 0, config.window_width, config.window_height)
        self.ui = UIManager(Theme())
        self.windows = WindowManager(self._bounds)
        self.overview: UIWindow | None = None
        self.tabs: TabBar | None = None
        self.search: TextInput | None = None
        self.dropdown: Dropdown | None = None
        self.systems: TableWidget | None = None
        self.scale_down: Button | None = None
        self.scale_up: Button | None = None
        self.contrast_button: Button | None = None
        self.speed_button: Button | None = None
        self.pause_button: Button | None = None
        self.action_button: Button | None = None
        self.research_button: Button | None = None
        self.create_fleet_button: Button | None = None
        self.move_fleet_button: Button | None = None
        self.diplomatic_action: Dropdown | None = None
        self._widgets: list[FocusableWidget] = []
        self._focusables: list[FocusableWidget] = []

    def run(self) -> None:
        pygame.init()
        try:
            flags = pygame.FULLSCREEN if self._fullscreen else pygame.RESIZABLE
            self.screen = pygame.display.set_mode(
                (self.config.window_width, self.config.window_height),
                flags,
            )
            if not self._fullscreen:
                self._windowed_size = self.screen.get_size()
            pygame.display.set_caption("NOVA - Network for Orbital Ventures and Ascension")
            self._bounds = self.screen.get_rect()
            self._bounds.y = 54
            self._bounds.height -= 54
            self.windows = WindowManager(self._bounds)
            self._build_ui()
            self._show_main_menu()
            self._running = True
            while self._running:
                self._handle_events()
                delta = self._clock.tick(60) / 1000.0
                self.application.update(delta)
                self._poll_campaign_news()
                self.ui.update(delta)
                self._draw()
                pygame.display.flip()
        finally:
            self.assets.clear()
            pygame.quit()

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._running = False
                continue
            if event.type == pygame.VIDEORESIZE and not self._fullscreen:
                self._windowed_size = (max(640, event.w), max(360, event.h))
                self.screen = pygame.display.set_mode(
                    self._windowed_size,
                    pygame.RESIZABLE,
                )
                self._update_bounds()
                self._layout_ui()
                self._clamp_map_pan()
                self._nebula_cache.clear()
                self._layout_menu()
                continue
            if self._menu_active:
                self._handle_menu_event(event)
                continue
            if self.ui.modal is not None:
                self.ui.handle_event(event, self._widgets)
                continue
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                if (
                    self.tabs is not None
                    and self.tabs.active == "GALAXY"
                    and self._map_rect().collidepoint(event.pos)
                ):
                    self._map_dragging = True
                    continue
            if event.type == pygame.MOUSEBUTTONUP and event.button == 3:
                self._map_dragging = False
                continue
            if event.type == pygame.MOUSEMOTION and self._map_dragging:
                if event.buttons[2]:
                    self._map_pan += pygame.Vector2(event.rel)
                    self._clamp_map_pan()
                    continue
                self._map_dragging = False
            if event.type == pygame.MOUSEWHEEL:
                mouse_position = getattr(event, "pos", pygame.mouse.get_pos())
                if self._map_rect().collidepoint(mouse_position):
                    if self.tabs is not None and self.tabs.active == "GALAXY":
                        self._zoom_galaxy_map(event.y * 0.08, mouse_position)
                    else:
                        self._system_zoom = min(
                            1.35,
                            max(0.52, self._system_zoom + event.y * 0.08),
                        )
                    continue
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F5:
                    self._save_campaign()
                    continue
                if event.key == pygame.K_F9:
                    self._load_campaign()
                    continue
                if event.key == pygame.K_F10:
                    self._show_main_menu()
                    continue
                if event.key == pygame.K_ESCAPE:
                    self._show_exit_dialog()
                    continue
                if event.key == pygame.K_F11:
                    self._toggle_fullscreen()
                    continue
                if event.key == pygame.K_F1:
                    self._toggle_contrast()
                    continue
                if (
                    event.key in (pygame.K_RETURN, pygame.K_KP_ENTER)
                    and self.tabs is not None
                    and self.tabs.active == "GALAXY"
                    and self.search is not None
                    and self.search.focused
                    and self.search.text.strip()
                ):
                    self._search_map()
                    continue
                if (
                    self.tabs is not None
                    and self.tabs.active == "GALAXY"
                    and not self._text_input_focused()
                ):
                    if event.key == pygame.K_b and event.mod & pygame.KMOD_CTRL:
                        self._toggle_map_bookmark()
                        continue
                    if event.key == pygame.K_b:
                        self._jump_to_next_bookmark()
                        continue
                    map_layers = {
                        pygame.K_p: "_show_borders",
                        pygame.K_t: "_show_trade_routes",
                        pygame.K_r: "_show_resources",
                        pygame.K_s: "_show_sensors",
                        pygame.K_f: "_fog_of_war",
                        pygame.K_e: "_show_exploration",
                    }
                    layer = map_layers.get(event.key)
                    if layer is not None:
                        self._toggle_map_layer(layer)
                        continue
                if (
                    event.key == pygame.K_HOME
                    and self.tabs is not None
                    and not self._text_input_focused()
                ):
                    if self.tabs.active == "GALAXY":
                        self._galaxy_zoom = 0.9
                        self._map_pan.update(0, 0)
                    else:
                        self._system_zoom = 0.92
                    continue
                if event.key == pygame.K_TAB:
                    self.ui.handle_event(event, self._widgets)
                    continue
                focused_widget = next(
                    (
                        widget
                        for widget in self._focusables
                        if widget.focused
                    ),
                    None,
                )
                if focused_widget is not None and not isinstance(focused_widget, TextInput):
                    if self.ui.handle_event(event, self._widgets):
                        self._filter_content()
                        continue
                if self._text_input_focused():
                    self.ui.handle_event(event, self._widgets)
                    self._filter_content()
                    continue
                if (
                    self.tabs is not None
                    and self.tabs.active == "SYSTEM"
                    and event.key in (pygame.K_m, pygame.K_h, pygame.K_d)
                ):
                    self._planet_view = {
                        pygame.K_m: "MANAGEMENT",
                        pygame.K_h: "HISTORY",
                        pygame.K_d: "DETAILS",
                    }[event.key]
                    continue
                if event.key == pygame.K_SPACE:
                    self._toggle_pause()
                    continue
                if event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    self._change_scale(0.1)
                    continue
                if event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    self._change_scale(-0.1)
                    continue
                if event.key == pygame.K_BACKSPACE and self.tabs is not None:
                    self.tabs.active = "GALAXY"
                    self._filter_content()
                    continue

            if (
                event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
                and self._map_rect().collidepoint(event.pos)
            ):
                if self._handle_map_layer_click(event.pos):
                    continue
                if self._select_map_item(event.pos):
                    if self.search is not None:
                        self.search.focused = False
                    continue

            self.windows.handle(event)
            self._layout_ui()
            self.ui.handle_event(event, self._widgets)
            self._filter_content()
            self._update_tooltip()

    def _draw(self) -> None:
        assert self.screen is not None
        theme = self.ui.theme
        width, height = self.screen.get_size()
        self.screen.fill(theme.background)
        try:
            background = self._scaled_asset("galaxy-background.svg", (width, height))
            self.screen.blit(background, (0, 0))
        except AssetError as error:
            logger.debug("Galaxy background unavailable: %s", error)
        if self._menu_active:
            self._draw_main_menu()
            return
        if self.tabs is not None and self.tabs.active == "SYSTEM":
            self._draw_system_map()
        else:
            self._draw_galaxy_map()
            self._draw_map_card()

        campaign = self.application.campaign
        paused = self.application.engine.clock.paused
        self._draw_command_hud(width, campaign, paused)
        small_font = self.ui.fonts.get(18)

        self.windows.draw(self.screen, small_font, theme)
        assert self.tabs is not None
        assert self.search is not None
        assert self.dropdown is not None
        assert self.systems is not None
        assert self.speed_button is not None
        assert self.pause_button is not None
        assert self.scale_down is not None
        assert self.scale_up is not None
        assert self.contrast_button is not None
        assert self.action_button is not None
        tab_font = self.ui.fonts.get(14 if width < 900 else 16)
        self.tabs.draw(self.screen, tab_font, theme)
        if self.tabs.active == "GALAXY":
            compact = height < 560
            if not compact:
                self.search.draw(self.screen, small_font, theme)
                self.dropdown.draw(self.screen, small_font, theme)
                self.systems.draw(self.screen, small_font, theme)
            self._draw_system_details(small_font, compact)
        elif self.tabs.active == "SYSTEM":
            compact = height < 560
            if not compact:
                self.search.draw(self.screen, small_font, theme)
                self.dropdown.draw(self.screen, small_font, theme)
                self.systems.draw(self.screen, small_font, theme)
            self._draw_object_details(small_font, compact)
            self.action_button.label = campaign.object_action_label(
                self._selected_system,
                self._selected_object,
            )
            self.action_button.draw(self.screen, small_font, theme)
        elif self.tabs.active == "CHRONICLE":
            self._draw_chronicle(small_font)
        elif self.tabs.active == "DIPLOMACY":
            self._draw_diplomacy(small_font)
            self.action_button.label = "CONFIRM DIPLOMATIC ACTION"
            self.action_button.draw(self.screen, small_font, theme)
        elif self.tabs.active == "SPECIES":
            self._draw_species(small_font, height < 560)
            self.action_button.label = "APPLY SPECIES ACTION"
            self.action_button.draw(self.screen, small_font, theme)
        else:
            self._draw_empire(small_font, height < 560)
            self.action_button.label = "BUILD SELECTED"
            self.action_button.draw(self.screen, small_font, theme)
            assert self.research_button is not None
            assert self.create_fleet_button is not None
            assert self.move_fleet_button is not None
            self.research_button.label = self._research_button_label()
            self.research_button.draw(self.screen, small_font, theme)
            self.create_fleet_button.draw(self.screen, small_font, theme)
            self.move_fleet_button.draw(self.screen, small_font, theme)
        self.speed_button.label = f"SPEED {self._speed_label()}"
        self.pause_button.label = "RESUME" if paused else "PAUSE"
        self.contrast_button.label = "HC ON" if self.ui.high_contrast else "HC OFF"
        for button in (
            self.speed_button,
            self.pause_button,
            self.scale_down,
            self.scale_up,
            self.contrast_button,
        ):
            button.draw(self.screen, small_font, theme)

        if self.tabs.active == "SYSTEM":
            help_text = (
                "Click body  |  M manage  H history  D details  |  BACKSPACE galaxy"
            )
        elif self.tabs.active == "EMPIRE":
            help_text = (
                "Choose a building above  |  build  |  research  |  commission or move fleets  |  "
                "F5 save  F9 load  F10 menu"
            )
        elif self.tabs.active == "DIPLOMACY":
            help_text = (
                "Survey rival territory to establish contact  |  negotiate, form pacts, "
                "or declare war  |  fleets engage hostile systems"
            )
        elif self.tabs.active == "SPECIES":
            help_text = (
                "Select a colony and species action  |  Xenobiology unlocks engineering "
                "and synthetic conversion  |  N changes naming culture in new game"
            )
        elif self.tabs.active == "CHRONICLE":
            help_text = "Empire history  |  F5 save  F9 load  F10 menu"
        else:
            help_text = (
                "Click star  |  wheel zoom  |  right-drag pan  |  Home reset  |  "
                "P borders  T trade  R resources  S sensors  F fog  E explore  "
                "Ctrl+B bookmark  B next  Space pause  F5 save  F9 load  F10 menu"
            )
        help_font = self.ui.fonts.get(13) if self.tabs.active == "GALAXY" else (
            self.ui.fonts.get(13) if width < 900 else small_font
        )
        self._label(help_text, (18, height - 22), help_font, theme.muted)
        self.ui.draw_overlays(self.screen, small_font, small_font)

    def _draw_command_hud(
        self,
        width: int,
        campaign: Campaign,
        paused: bool,
    ) -> None:
        assert self.screen is not None
        theme = self.ui.theme
        bar = pygame.Rect(0, 0, width, 54)
        pygame.draw.rect(self.screen, (4, 10, 20), bar)
        pygame.draw.line(self.screen, (41, 79, 98), (0, 53), (width, 53), 1)

        crest = pygame.Rect(14, 8, 36, 36)
        pygame.draw.rect(self.screen, theme.panel_alt, crest, border_radius=5)
        pygame.draw.rect(self.screen, theme.accent, crest, 1, border_radius=5)
        self._label("N", (26, 13), self.ui.fonts.get(23), theme.accent)
        self._label("NOVA", (58, 15), self.ui.fonts.get(20), theme.text)

        resources = (
            ("ALLOYS", campaign.alloys, (221, 165, 92)),
            ("SCIENCE", campaign.science, (113, 204, 235)),
            ("INFLUENCE", campaign.influence, (196, 146, 230)),
            ("VOLATILES", campaign.volatiles, (228, 119, 105)),
            ("ENERGY", campaign.energy, (243, 211, 105)),
            ("FOOD", campaign.food, (129, 211, 133)),
        )
        start_x = 122
        reserved_right = 184
        resource_width = max(42, (width - start_x - reserved_right) // len(resources))
        compact_labels = width < 900
        for index, (name, value, color) in enumerate(resources):
            x = start_x + index * resource_width
            pygame.draw.line(
                self.screen,
                (31, 51, 68),
                (x - 8, 10),
                (x - 8, 44),
                1,
            )
            pygame.draw.circle(self.screen, color, (x, 19), 3)
            label = name[:4] if compact_labels else name
            self._label(
                label,
                (x + 8, 12),
                self.ui.fonts.get(12 if compact_labels else 13),
                theme.muted,
            )
            self._label(
                f"{value:,.0f}",
                (x + 8, 26),
                self.ui.fonts.get(15 if compact_labels else 16),
                color,
            )

        date_x = width - 178
        pygame.draw.line(
            self.screen,
            (31, 51, 68),
            (date_x - 12, 10),
            (date_x - 12, 44),
            1,
        )
        self._label(
            campaign.date_label,
            (date_x, 11),
            self.ui.fonts.get(14),
            theme.text,
        )
        status_color = theme.warning if paused else theme.accent
        pygame.draw.circle(self.screen, status_color, (date_x + 5, 37), 3)
        self._label(
            "PAUSED" if paused else "RUNNING",
            (date_x + 14, 30),
            self.ui.fonts.get(12),
            status_color,
        )

    def _poll_campaign_news(self) -> None:
        campaign = self.application.campaign
        if campaign is not self._observed_campaign:
            self._observed_campaign = campaign
            self._known_campaign_events = list(campaign.log)
            return
        events = campaign.log
        previous = (
            self._known_campaign_events[-1]
            if self._known_campaign_events
            else None
        )
        if previous in events:
            new_events = events[events.index(previous) + 1 :]
        else:
            new_events = events
        self._known_campaign_events = list(events)
        for event in new_events[-3:]:
            message = event.split("  ", 1)[-1]
            if not any(
                notification.message == message
                for notification in self.ui.notifications
            ):
                self.ui.notify(message)

    def _show_main_menu(self) -> None:
        self._menu_active = True
        self.application.engine.clock.pause()
        self._menu_buttons = [
            Button(pygame.Rect(0, 0, 1, 1), "NEW GAME", self._start_new_game),
            Button(pygame.Rect(0, 0, 1, 1), "CONTINUE", self._continue_game),
            Button(pygame.Rect(0, 0, 1, 1), "LOAD QUICK SAVE", self._load_campaign),
            Button(pygame.Rect(0, 0, 1, 1), "QUIT", lambda: setattr(self, "_running", False)),
        ]
        self._layout_menu()

    def _layout_menu(self) -> None:
        if self.screen is None or not self._menu_buttons:
            return
        width, height = self.screen.get_size()
        margin = 24
        gap = 10
        button_height = 42
        button_width = (width - 2 * margin - 3 * gap) // 4
        first_y = height - button_height - 22
        for index, button in enumerate(self._menu_buttons):
            button.rect = pygame.Rect(
                margin + index * (button_width + gap),
                first_y,
                button_width,
                button_height,
            )
        card_gap = 12
        species_ids = list(self.application.campaign.species_catalog)
        columns = min(4, len(species_ids))
        card_width = (
            width - 2 * margin - card_gap * (columns - 1)
        ) // columns
        card_top = max(138, height // 4)
        card_height = min(252, max(150, first_y - card_top - 28))
        self._species_card_rects = {
            species_id: pygame.Rect(
                margin + (index % columns) * (card_width + card_gap),
                card_top,
                card_width,
                card_height,
            )
            for index, species_id in enumerate(species_ids)
        }
        self._name_culture_rect = pygame.Rect(
            max(margin, width - margin - min(250, width // 3)),
            card_top - 38,
            min(250, width // 3),
            30,
        )

    def _handle_menu_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self._running:
                self._menu_active = False
                self.application.engine.clock.resume()
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_n:
            self._cycle_name_culture()
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._name_culture_rect.collidepoint(event.pos):
                self._cycle_name_culture()
                return
            for species_id, rect in self._species_card_rects.items():
                if rect.collidepoint(event.pos):
                    self._selected_species_id = species_id
                    profile = self.application.campaign.species_catalog[species_id]
                    if self._selected_name_culture not in self._menu_name_cultures(
                        profile.name_cultures
                    ):
                        self._selected_name_culture = "all"
                    return
        for button in self._menu_buttons:
            if button.handle(event):
                return

    def _cycle_name_culture(self) -> None:
        profile = self.application.campaign.species_catalog[
            self._selected_species_id
        ]
        cultures = self._menu_name_cultures(profile.name_cultures)
        current = (
            self._selected_name_culture
            if self._selected_name_culture in cultures
            else "all"
        )
        index = cultures.index(current)
        self._selected_name_culture = cultures[(index + 1) % len(cultures)]

    @staticmethod
    def _menu_name_cultures(cultures: tuple[str, ...]) -> tuple[str, ...]:
        hierarchical = tuple(culture for culture in cultures if "/" in culture)
        if hierarchical:
            return ("all", *sorted(hierarchical))
        return cultures

    def _draw_main_menu(self) -> None:
        assert self.screen is not None
        width, height = self.screen.get_size()
        theme = self.ui.theme
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        overlay.fill((3, 10, 21, 210))
        self.screen.blit(overlay, (0, 0))
        self._label("NOVA", (24, 18), self.ui.fonts.get(42), theme.accent)
        self._label(
            "NETWORK FOR ORBITAL VENTURES AND ASCENSION",
            (28, 62),
            self.ui.fonts.get(13),
            theme.muted,
        )
        self._label(
            "CHOOSE YOUR SPECIES",
            (24, next(iter(self._species_card_rects.values())).y - 27),
            self.ui.fonts.get(14),
            theme.warning,
        )
        pygame.draw.rect(
            self.screen,
            theme.panel_alt,
            self._name_culture_rect,
            border_radius=4,
        )
        pygame.draw.rect(
            self.screen,
            theme.accent,
            self._name_culture_rect,
            1,
            border_radius=4,
        )
        culture = self._selected_name_culture.rsplit("/", 1)[-1].title()
        culture_label = self.ui.fonts.get(13).render(
            f"NAMES: {culture}  (N)",
            True,
            theme.text,
        )
        self.screen.blit(
            culture_label,
            culture_label.get_rect(center=self._name_culture_rect.center),
        )
        for species_id, rect in self._species_card_rects.items():
            profile = self.application.campaign.species_catalog[species_id]
            selected = species_id == self._selected_species_id
            pygame.draw.rect(self.screen, theme.panel, rect, border_radius=8)
            pygame.draw.rect(
                self.screen,
                theme.accent if selected else theme.muted,
                rect,
                2 if selected else 1,
                border_radius=8,
            )
            portrait_size = min(rect.width - 18, rect.height - 82)
            portrait = self._scaled_asset(profile.portrait, (portrait_size, portrait_size))
            self.screen.blit(portrait, (rect.centerx - portrait_size // 2, rect.y + 8))
            self._label(
                profile.name,
                (rect.x + 10, rect.y + portrait_size + 14),
                self.ui.fonts.get(18),
                theme.text,
            )
            self._label(
                f"LIFESPAN {profile.lifespan_years} YEARS",
                (rect.x + 10, rect.y + portrait_size + 38),
                self.ui.fonts.get(12),
                theme.muted,
            )
            traits = ", ".join(profile.traits)
            for index, line in enumerate(
                self._wrap_text(self.ui.fonts.get(12), traits, rect.width - 20)[:2]
            ):
                self._label(
                    line,
                    (rect.x + 10, rect.y + portrait_size + 55 + index * 15),
                    self.ui.fonts.get(12),
                    theme.warning,
                )
        for button in self._menu_buttons:
            button.draw(self.screen, self.ui.fonts.get(13), theme)
        if self._menu_message:
            self._label(
                self._menu_message,
                (self._menu_buttons[0].rect.x, self._menu_buttons[0].rect.y - 20),
                self.ui.fonts.get(14),
                theme.warning,
            )

    def _start_new_game(self) -> None:
        self.application.new_game(
            self._selected_species_id,
            name_culture=self._selected_name_culture,
        )
        self._selected_system = "sol"
        self._selected_object = "earth"
        self._planet_view = "DETAILS"
        self._species_selected_colony = None
        self._menu_active = False
        self._menu_message = ""
        if self.tabs is not None:
            self.tabs.active = "GALAXY"
        self.application.engine.clock.resume()
        self._filter_content()
        self.ui.notify("New frontier campaign started")

    def _continue_game(self) -> None:
        self._menu_active = False
        self.application.engine.clock.resume()

    def _save_campaign(self) -> None:
        try:
            self.application.save_game()
        except SaveError as error:
            self._menu_message = str(error)
            self.ui.notify(str(error))
            return
        self._menu_message = "Quick save complete"
        self.ui.notify("Campaign saved")

    def _load_campaign(self) -> None:
        try:
            self.application.load_game()
        except SaveError as error:
            self._menu_message = str(error)
            self.ui.notify(str(error))
            return
        self._selected_system = "sol"
        self._selected_object = "earth"
        self._planet_view = "DETAILS"
        self._menu_message = ""
        self._menu_active = False
        self.application.engine.clock.resume()
        self._filter_content()
        self.ui.notify("Campaign loaded")

    def _build_ui(self) -> None:
        assert self.screen is not None
        width, height = self.screen.get_size()
        scale = self.ui.fonts.scale
        panel_width = min(round(360 * scale), width - 32)
        panel_top = 60 if height < 560 else 70
        panel_height = min(round(560 * scale), height - panel_top - 10)
        panel = UIWindow(
            pygame.Rect(width - panel_width - 16, panel_top, panel_width, panel_height),
            "FRONTIER COMMAND",
            min_size=(min(300, width - 32), min(330, height - 70)),
        )
        self.overview = panel
        self.windows.add(panel)
        self.tabs = TabBar(
            pygame.Rect(0, 0, 1, 1),
            ["GALAXY", "SYSTEM", "EMPIRE", "SPECIES", "DIPLOMACY", "CHRONICLE"],
        )
        self.search = TextInput(pygame.Rect(0, 0, 1, 1), "Search...")
        self.dropdown = Dropdown(
            pygame.Rect(0, 0, 1, 1),
            ["All", "Uncharted", "Surveyed", "Colonized"],
        )
        self._species_destination = Dropdown(
            pygame.Rect(0, 0, 1, 1),
            [],
        )
        self.diplomatic_action = Dropdown(
            pygame.Rect(0, 0, 1, 1),
            ["First contact pending"],
        )
        self.systems = TableWidget(
            pygame.Rect(0, 0, 1, 1),
            ["SYSTEM", "STATUS", "WORLD"],
            self._system_rows(),
            on_select=self._select_system,
        )
        self.action_button = Button(
            pygame.Rect(0, 0, 1, 1),
            "",
            self._perform_selected_action,
            "Carry out the available action in this system",
        )
        self.research_button = Button(
            pygame.Rect(0, 0, 1, 1),
            "START RESEARCH",
            self._start_next_research,
            "Begin the next available technology",
        )
        self.create_fleet_button = Button(
            pygame.Rect(0, 0, 1, 1),
            "NEW FLEET",
            self._create_fleet,
            "Commission a new fleet for 35 alloys",
        )
        self.move_fleet_button = Button(
            pygame.Rect(0, 0, 1, 1),
            "MOVE FLEET",
            self._move_fleet_to_selection,
            "Send an idle fleet along a navigable route to the selected system",
        )
        self.scale_down = Button(
            pygame.Rect(0, 0, 1, 1),
            "A-",
            lambda: self._change_scale(-0.1),
            "Reduce interface size",
        )
        self.scale_up = Button(
            pygame.Rect(0, 0, 1, 1),
            "A+",
            lambda: self._change_scale(0.1),
            "Increase interface size",
        )
        self.contrast_button = Button(
            pygame.Rect(0, 0, 1, 1),
            "CONTRAST OFF",
            self._toggle_contrast,
            "Toggle high-contrast colors",
        )
        self.speed_button = Button(
            pygame.Rect(0, 0, 1, 1),
            "SPEED 1x",
            self._cycle_speed,
            "Cycle simulation speed",
        )
        self.pause_button = Button(
            pygame.Rect(0, 0, 1, 1),
            "PAUSE",
            self._toggle_pause,
            "Pause or resume the simulation",
        )
        self._configure_visible_widgets()
        self._layout_ui()
        self._filter_content()

    def _layout_ui(self) -> None:
        if self.screen is None or self.overview is None:
            return
        scale = self.ui.fonts.scale
        rect = self.overview.rect
        margin = round(12 * scale)
        content_x = rect.x + margin
        content_width = rect.width - margin * 2
        if self.screen.get_height() < 560:
            button_height = round(30 * scale)
            gap = round(5 * scale)
            self.tabs.rect = pygame.Rect(
                content_x,
                rect.y + round(38 * scale),
                content_width,
                round(28 * scale),
            )
            bottom_row_y = rect.bottom - button_height - round(6 * scale)
            self.scale_down.rect = pygame.Rect(
                content_x,
                bottom_row_y,
                content_width // 3,
                button_height,
            )
            self.scale_up.rect = pygame.Rect(
                content_x + content_width // 3,
                bottom_row_y,
                content_width // 3,
                button_height,
            )
            self.contrast_button.rect = pygame.Rect(
                content_x + (content_width // 3) * 2,
                bottom_row_y,
                content_width - (content_width // 3) * 2,
                button_height,
            )
            control_y = bottom_row_y - button_height - gap
            speed_width = round(content_width * 0.55)
            self.speed_button.rect = pygame.Rect(
                content_x,
                control_y,
                speed_width,
                button_height,
            )
            self.pause_button.rect = pygame.Rect(
                content_x + speed_width + gap,
                control_y,
                content_width - speed_width - gap,
                button_height,
            )
            action_y = control_y - button_height - gap
            assert self.action_button is not None
            if self.tabs is not None and self.tabs.active == "EMPIRE":
                half_width = (content_width - gap) // 2
                fleet_y = action_y - button_height - gap
                self.action_button.rect = pygame.Rect(
                    content_x, action_y, half_width, button_height
                )
                assert self.research_button is not None
                assert self.create_fleet_button is not None
                assert self.move_fleet_button is not None
                self.research_button.rect = pygame.Rect(
                    content_x + half_width + gap,
                    action_y,
                    content_width - half_width - gap,
                    button_height,
                )
                self.create_fleet_button.rect = pygame.Rect(
                    content_x, fleet_y, half_width, button_height
                )
                self.move_fleet_button.rect = pygame.Rect(
                    content_x + half_width + gap,
                    fleet_y,
                    content_width - half_width - gap,
                    button_height,
                )
                action_y = fleet_y
            else:
                self.action_button.rect = pygame.Rect(
                    content_x, action_y, content_width, button_height
                )
                for button in (
                    self.research_button,
                    self.create_fleet_button,
                    self.move_fleet_button,
                ):
                    if button is not None:
                        button.rect = pygame.Rect(0, 0, 1, 1)
            log_y = self.tabs.rect.bottom + round(8 * scale)
            self.systems.rect = pygame.Rect(
                content_x,
                log_y,
                content_width,
                max(1, action_y - log_y - round(8 * scale)),
            )
            self.search.rect = pygame.Rect(0, 0, 1, 1)
            self.dropdown.rect = (
                pygame.Rect(
                    content_x,
                    self.tabs.rect.bottom + round(8 * scale),
                    content_width,
                    round(30 * scale),
                )
                if self.tabs is not None
                and self.tabs.active in ("EMPIRE", "DIPLOMACY", "SPECIES")
                else pygame.Rect(0, 0, 1, 1)
            )
            assert self.diplomatic_action is not None
            self.diplomatic_action.rect = (
                pygame.Rect(
                    content_x,
                    self.dropdown.rect.bottom + gap,
                    content_width,
                    round(30 * scale),
                )
                if self.tabs is not None and self.tabs.active == "DIPLOMACY"
                else pygame.Rect(0, 0, 1, 1)
            )
            assert self._species_destination is not None
            self._species_destination.rect = (
                pygame.Rect(
                    content_x,
                    self.dropdown.rect.bottom + gap,
                    content_width,
                    round(30 * scale),
                )
                if self.tabs is not None and self.tabs.active == "SPECIES"
                else pygame.Rect(0, 0, 1, 1)
            )
            if self.tabs is not None and self.tabs.active == "DIPLOMACY":
                self.systems.rect.y = self.diplomatic_action.rect.bottom + gap
                self.systems.rect.height = max(
                    1,
                    action_y - self.systems.rect.y - round(8 * scale),
                )
            elif self.tabs is not None and self.tabs.active == "SPECIES":
                self.systems.rect.y = self._species_destination.rect.bottom + gap
                self.systems.rect.height = max(
                    1,
                    action_y - self.systems.rect.y - round(8 * scale),
                )
            return
        self.tabs.rect = pygame.Rect(
            content_x,
            rect.y + round(44 * scale),
            content_width,
            round(34 * scale),
        )
        self.search.rect = (
            pygame.Rect(
                content_x,
                rect.y + round(86 * scale),
                content_width,
                round(34 * scale),
            )
            if self.tabs is None
            or self.tabs.active not in ("EMPIRE", "DIPLOMACY", "SYSTEM", "SPECIES")
            else pygame.Rect(0, 0, 1, 1)
        )
        self.dropdown.rect = pygame.Rect(
            content_x,
            rect.y
            + round(
                (
                    86
                    if self.tabs is not None
                    and self.tabs.active in (
                        "EMPIRE",
                        "DIPLOMACY",
                        "SYSTEM",
                        "SPECIES",
                    )
                    else 128
                )
                * scale
            ),
            content_width,
            round(34 * scale),
        )
        assert self.diplomatic_action is not None
        self.diplomatic_action.rect = (
            pygame.Rect(
                content_x,
                self.dropdown.rect.bottom + round(6 * scale),
                content_width,
                round(34 * scale),
            )
            if self.tabs is not None and self.tabs.active == "DIPLOMACY"
            else pygame.Rect(0, 0, 1, 1)
        )
        assert self._species_destination is not None
        self._species_destination.rect = (
            pygame.Rect(
                content_x,
                self.dropdown.rect.bottom + round(6 * scale),
                content_width,
                round(34 * scale),
            )
            if self.tabs is not None and self.tabs.active == "SPECIES"
            else pygame.Rect(0, 0, 1, 1)
        )
        bottom_row_y = rect.bottom - round(61 * scale)
        button_height = round(34 * scale)
        gap = round(6 * scale)
        accessibility_width = (content_width - 2 * gap) // 3
        self.scale_down.rect = pygame.Rect(
            content_x,
            bottom_row_y,
            accessibility_width,
            button_height,
        )
        self.scale_up.rect = pygame.Rect(
            content_x + accessibility_width + gap,
            bottom_row_y,
            accessibility_width,
            button_height,
        )
        self.contrast_button.rect = pygame.Rect(
            content_x + (accessibility_width + gap) * 2,
            bottom_row_y,
            content_width - (accessibility_width + gap) * 2,
            button_height,
        )
        control_y = bottom_row_y - button_height - gap
        speed_width = round(content_width * 0.55)
        self.speed_button.rect = pygame.Rect(
            content_x,
            control_y,
            speed_width,
            button_height,
        )
        self.pause_button.rect = pygame.Rect(
            content_x + speed_width + gap,
            control_y,
            content_width - speed_width - gap,
            button_height,
        )
        action_y = control_y - button_height - gap
        assert self.action_button is not None
        if self.tabs is not None and self.tabs.active == "EMPIRE":
            half_width = (content_width - gap) // 2
            fleet_y = action_y - button_height - gap
            self.action_button.rect = pygame.Rect(
                content_x, action_y, half_width, button_height
            )
            assert self.research_button is not None
            assert self.create_fleet_button is not None
            assert self.move_fleet_button is not None
            self.research_button.rect = pygame.Rect(
                content_x + half_width + gap,
                action_y,
                content_width - half_width - gap,
                button_height,
            )
            self.create_fleet_button.rect = pygame.Rect(
                content_x, fleet_y, half_width, button_height
            )
            self.move_fleet_button.rect = pygame.Rect(
                content_x + half_width + gap,
                fleet_y,
                content_width - half_width - gap,
                button_height,
            )
            action_y = fleet_y
        else:
            self.action_button.rect = pygame.Rect(
                content_x, action_y, content_width, button_height
            )
            for button in (
                self.research_button,
                self.create_fleet_button,
                self.move_fleet_button,
            ):
                if button is not None:
                    button.rect = pygame.Rect(0, 0, 1, 1)
        table_y = (
            self.diplomatic_action.rect.bottom + round(8 * scale)
            if self.tabs is not None and self.tabs.active == "DIPLOMACY"
            else self._species_destination.rect.bottom + round(8 * scale)
            if self.tabs is not None and self.tabs.active == "SPECIES"
            else self.dropdown.rect.bottom + round(8 * scale)
        )
        reserved_details_height = round(
            (
                300
                if self.tabs is not None
                and self.tabs.active == "SYSTEM"
                and self._planet_view == "HISTORY"
                else 210
                if self.tabs is not None
                and self.tabs.active == "SYSTEM"
                and self._planet_view == "MANAGEMENT"
                else 220
                if self.tabs is not None
                and self.tabs.active == "SYSTEM"
                else 160
                if self.tabs is not None
                and self.tabs.active == "SPECIES"
                else 72
            )
            * scale
        )
        table_height = max(
            round(48 * scale),
            action_y - table_y - reserved_details_height,
        )
        self.systems.rect = pygame.Rect(
            content_x,
            table_y,
            content_width,
            table_height,
        )

    def _update_bounds(self) -> None:
        assert self.screen is not None
        self._bounds = self.screen.get_rect()
        self._bounds.y = 54
        self._bounds.height = max(0, self._bounds.height - 54)
        self.windows.set_bounds(self._bounds)

    def _filter_content(self) -> None:
        if (
            self.search is None
            or self.dropdown is None
            or self.systems is None
            or self.tabs is None
        ):
            return
        if self._active_tab != self.tabs.active:
            self._active_tab = self.tabs.active
            self.search.focused = False
            self.systems.columns = {
                "GALAXY": ["SYSTEM", "STATUS", "WORLD"],
                "SYSTEM": ["BODY", "TYPE", "WORLD"],
                "SPECIES": ["COLONY", "SPECIES", "POPULATION"],
            }.get(self.tabs.active, ["SYSTEM", "STATUS", "WORLD"])
            self._configure_visible_widgets()
            self._layout_ui()
            self.dropdown.options = self._dropdown_options()
            if self.dropdown.options:
                self.dropdown.selected = self.dropdown.options[0]
            if self.diplomatic_action is not None:
                self.diplomatic_action.options = self._diplomatic_action_options()
                if self.diplomatic_action.options:
                    self.diplomatic_action.selected = self.diplomatic_action.options[0]
        if self.tabs.active == "CHRONICLE":
            return
        if self.tabs.active == "EMPIRE":
            return
        if self.tabs.active == "DIPLOMACY":
            return
        if self.tabs.active == "SPECIES":
            self._ensure_species_colony_selection()
            self.systems.set_rows(self._species_colony_rows())
            self._refresh_species_destinations()
            return
        query = self.search.text.casefold().strip()
        category = self.dropdown.selected
        sensor_system_ids = (
            self._sensor_system_ids()
            if self.tabs.active == "GALAXY" and self._fog_of_war
            else set()
        )
        rows = (
            self._system_rows()
            if self.tabs.active == "GALAXY"
            else self._object_rows()
        )
        filtered = [
            row
            for row in rows
            if (not query or query in " ".join(row).casefold())
            and (category == "All" or row[1] == category)
            and (
                self.tabs.active != "GALAXY"
                or not self._fog_of_war
                or self._is_system_visible(
                    next(
                        system
                        for system in self.application.campaign.systems
                        if system.name == row[0]
                    ),
                    sensor_system_ids,
                )
            )
        ]
        self.systems.set_rows(filtered)

    def _select_system(self, row: tuple[str, ...]) -> None:
        if self.tabs is None:
            return
        if self.tabs.active == "SPECIES":
            colony = next(
                (
                    colony
                    for colony in self.application.campaign.player_colonies
                    if self._species_colony_label(colony) == row[0]
                ),
                None,
            )
            if colony is not None:
                self._species_selected_colony = (
                    colony.system_id,
                    colony.planet_id,
                )
                self._refresh_species_destinations()
                self.ui.notify(
                    f"Selected {self._species_colony_label(colony)}"
                )
            return
        if self.tabs.active == "GALAXY":
            system = next(
                entry for entry in self.application.campaign.systems if entry.name == row[0]
            )
            self._selected_system = system.system_id
            selected = next(
                (obj for obj in system.objects if obj.habitable or obj.kind == "Planet"),
                system.objects[0],
            )
            self._selected_object = selected.object_id
            self._planet_view = "DETAILS"
            self.ui.notify(f"Selected {system.name}")
            return
        system = self.application.campaign.get_system(self._selected_system)
        selected = next(obj for obj in system.objects if obj.name == row[0])
        self._selected_object = selected.object_id
        self._planet_view = "DETAILS"
        self.ui.notify(f"Selected {selected.name}")

    def _system_rows(self) -> list[tuple[str, str, str]]:
        return [
            (system.name, system.status, system.world_type)
            for system in self.application.campaign.systems
        ]

    def _sensor_system_ids(self) -> set[str]:
        campaign = self.application.campaign
        owned_ids = {
            system.system_id
            for system in campaign.systems
            if system.owner == "Union"
        }
        sensor_ids = set(owned_ids)
        for first_id, second_id in campaign.routes:
            if first_id in owned_ids:
                sensor_ids.add(second_id)
            if second_id in owned_ids:
                sensor_ids.add(first_id)
        return sensor_ids

    def _is_system_visible(
        self,
        system: StarSystem,
        sensor_system_ids: set[str] | None = None,
    ) -> bool:
        return (
            not self._fog_of_war
            or system.surveyed
            or system.system_id
            in (
                sensor_system_ids
                if sensor_system_ids is not None
                else self._sensor_system_ids()
            )
        )

    def _map_filter_matches(self, system: StarSystem) -> bool:
        if self.search is not None:
            query = self.search.text.casefold().strip()
            if query and query not in (
                f"{system.name} {system.status} {system.world_type} {system.system_id}"
            ).casefold():
                return False
        if (
            self.dropdown is not None
            and self.dropdown.selected not in ("", "All", system.status)
        ):
            return False
        return True

    def _trade_route_edges(self) -> set[tuple[str, str]]:
        return self._owner_route_edges().get("Union", set())

    def _owner_route_edges(self) -> dict[str, set[tuple[str, str]]]:
        campaign = self.application.campaign
        key: tuple[object, ...] = (
            campaign.routes,
            tuple((system.system_id, system.owner) for system in campaign.systems),
        )
        if key == self._owner_route_cache_key:
            return self._owner_route_cache
        adjacency: dict[str, list[str]] = {
            system.system_id: [] for system in campaign.systems
        }
        for first_id, second_id in campaign.routes:
            adjacency[first_id].append(second_id)
            adjacency[second_id].append(first_id)
        owned_by: dict[str, list[str]] = {}
        for system in campaign.systems:
            if system.owner is not None:
                owned_by.setdefault(system.owner, []).append(system.system_id)
        route_edges: dict[str, set[tuple[str, str]]] = {}
        for owner, owned in owned_by.items():
            trade_edges: set[tuple[str, str]] = set()
            for source_index, source_id in enumerate(owned):
                previous: dict[str, str | None] = {source_id: None}
                frontier = deque([source_id])
                while frontier:
                    current_id = frontier.popleft()
                    for neighbor_id in adjacency[current_id]:
                        if neighbor_id not in previous:
                            previous[neighbor_id] = current_id
                            frontier.append(neighbor_id)
                for target_id in owned[source_index + 1 :]:
                    if target_id not in previous:
                        continue
                    current_id = target_id
                    while previous[current_id] is not None:
                        parent_id = previous[current_id]
                        assert parent_id is not None
                        trade_edges.add(tuple(sorted((parent_id, current_id))))
                        current_id = parent_id
            route_edges[owner] = trade_edges
        self._owner_route_cache_key = key
        self._owner_route_cache = route_edges
        return self._owner_route_cache

    def _territory_geometry(
        self,
        bounds: pygame.Rect,
    ) -> tuple[
        list[tuple[str, tuple[tuple[float, float], ...]]],
        list[tuple[str, tuple[float, float], tuple[float, float]]],
    ]:
        systems = self.application.campaign.systems
        key: tuple[object, ...] = (
            bounds.size,
            tuple(
                (system.system_id, system.x, system.y, system.owner)
                for system in systems
            ),
        )
        if key == self._territory_cache_key:
            return self._territory_polygons, self._territory_edges

        sites = [
            (
                system,
                (system.x - 0.5) * bounds.width,
                (system.y - 0.5) * bounds.height,
            )
            for system in systems
        ]
        polygons: list[tuple[str, tuple[tuple[float, float], ...]]] = []
        edge_owners: dict[
            tuple[tuple[float, float], tuple[float, float]],
            list[str],
        ] = {}
        for system, site_x, site_y in sites:
            if system.owner is None:
                continue
            polygon: list[tuple[float, float]] = [
                (-bounds.width / 2, -bounds.height / 2),
                (bounds.width / 2, -bounds.height / 2),
                (bounds.width / 2, bounds.height / 2),
                (-bounds.width / 2, bounds.height / 2),
            ]
            for other, other_x, other_y in sites:
                if other.system_id == system.system_id:
                    continue
                a = 2 * (other_x - site_x)
                b = 2 * (other_y - site_y)
                limit = other_x**2 + other_y**2 - site_x**2 - site_y**2
                clipped: list[tuple[float, float]] = []
                if not polygon:
                    break
                previous = polygon[-1]
                previous_value = a * previous[0] + b * previous[1] - limit
                for current in polygon:
                    current_value = a * current[0] + b * current[1] - limit
                    previous_inside = previous_value <= 1e-7
                    current_inside = current_value <= 1e-7
                    if previous_inside != current_inside:
                        fraction = previous_value / (previous_value - current_value)
                        clipped.append(
                            (
                                previous[0] + (current[0] - previous[0]) * fraction,
                                previous[1] + (current[1] - previous[1]) * fraction,
                            )
                        )
                    if current_inside:
                        clipped.append(current)
                    previous = current
                    previous_value = current_value
                polygon = clipped
            if len(polygon) < 3:
                continue
            polygons.append((system.owner, tuple(polygon)))
            for index, first in enumerate(polygon):
                second = polygon[(index + 1) % len(polygon)]
                normalized_first = (round(first[0], 3), round(first[1], 3))
                normalized_second = (round(second[0], 3), round(second[1], 3))
                edge_key = tuple(sorted((normalized_first, normalized_second)))
                edge_owners.setdefault(edge_key, []).append(system.owner)

        borders = [
            (owners[0], edge[0], edge[1])
            for edge, owners in edge_owners.items()
            if len(owners) == 1 or len(set(owners)) > 1
        ]
        self._territory_cache_key = key
        self._territory_polygons = polygons
        self._territory_edges = borders
        return polygons, borders

    def _owner_color(
        self,
        owner: str,
        owners: list[str],
    ) -> tuple[int, int, int]:
        if owner == "Union":
            return (222, 169, 79)
        palette = (
            (92, 161, 219),
            (180, 111, 201),
            (79, 181, 139),
            (212, 108, 108),
        )
        other_owners = sorted(entry for entry in owners if entry != "Union")
        return palette[other_owners.index(owner) % len(palette)]

    def _draw_territory_layer(
        self,
        bounds: pygame.Rect,
        systems: list[StarSystem],
    ) -> None:
        assert self.screen is not None
        polygons, borders = self._territory_geometry(bounds)
        if not polygons:
            return
        owners = sorted({system.owner for system in systems if system.owner})
        route_edges = self._owner_route_edges()
        corridor_width = max(
            28,
            round(min(bounds.size) * 0.08 * self._galaxy_zoom),
        )
        for owner, polygon in polygons:
            overlay = pygame.Surface(bounds.size, pygame.SRCALPHA)
            points = [
                (
                    round(bounds.width / 2 + x * self._galaxy_zoom + self._map_pan.x),
                    round(bounds.height / 2 + y * self._galaxy_zoom + self._map_pan.y),
                )
                for x, y in polygon
            ]
            pygame.draw.polygon(
                overlay,
                (*self._owner_color(owner, owners), 42),
                points,
            )
            self.screen.blit(overlay, bounds.topleft)

        for owner in owners:
            overlay = pygame.Surface(bounds.size, pygame.SRCALPHA)
            color = self._owner_color(owner, owners)
            owner_systems = [
                system for system in systems if system.owner == owner
            ]
            for system in owner_systems:
                position = self._map_position(system.system_id)
                center = position[0] - bounds.x, position[1] - bounds.y
                pygame.draw.circle(
                    overlay,
                    (*color, 42),
                    center,
                    corridor_width // 2,
                )
            for first_id, second_id in route_edges.get(owner, set()):
                start = self._map_position(first_id)
                end = self._map_position(second_id)
                start = start[0] - bounds.x, start[1] - bounds.y
                end = end[0] - bounds.x, end[1] - bounds.y
                pygame.draw.line(
                    overlay,
                    (*color, 42),
                    start,
                    end,
                    corridor_width,
                )
                pygame.draw.circle(
                    overlay,
                    (*color, 42),
                    start,
                    corridor_width // 2,
                )
                pygame.draw.circle(
                    overlay,
                    (*color, 42),
                    end,
                    corridor_width // 2,
                )
            self.screen.blit(overlay, bounds.topleft)
            outline = pygame.mask.from_surface(overlay, 1).outline(every=3)
            if len(outline) > 2:
                outline = [(x + bounds.x, y + bounds.y) for x, y in outline]
                pygame.draw.lines(
                    self.screen,
                    (9, 13, 23),
                    True,
                    outline,
                    8,
                )
                pygame.draw.lines(self.screen, color, True, outline, 5)

        for owner, start, end in borders:
            color = self._owner_color(owner, owners)
            screen_start = (
                round(bounds.centerx + start[0] * self._galaxy_zoom + self._map_pan.x),
                round(bounds.centery + start[1] * self._galaxy_zoom + self._map_pan.y),
            )
            screen_end = (
                round(bounds.centerx + end[0] * self._galaxy_zoom + self._map_pan.x),
                round(bounds.centery + end[1] * self._galaxy_zoom + self._map_pan.y),
            )
            pygame.draw.line(self.screen, (8, 12, 22), screen_start, screen_end, 5)
            pygame.draw.line(self.screen, color, screen_start, screen_end, 2)

        for owner in owners:
            owned_systems = [
                system for system in systems if system.owner == owner
            ]
            center = (
                round(
                    sum(self._map_position(system.system_id)[0] for system in owned_systems)
                    / len(owned_systems)
                ),
                round(
                    sum(self._map_position(system.system_id)[1] for system in owned_systems)
                    / len(owned_systems)
                ),
            )
            label = self.ui.fonts.get(18).render(
                owner.upper(),
                True,
                self._owner_color(owner, owners),
            )
            label_rect = label.get_rect(center=center)
            shadow = self.ui.fonts.get(18).render(owner.upper(), True, (10, 13, 20))
            self.screen.blit(shadow, label_rect.move(2, 2))
            self.screen.blit(label, label_rect)

    def _toggle_map_bookmark(self) -> None:
        bookmarks = self.application.campaign.map_bookmarks
        if self._selected_system in bookmarks:
            bookmarks.remove(self._selected_system)
            self.ui.notify("Bookmark removed")
        else:
            bookmarks.append(self._selected_system)
            self.ui.notify("System bookmarked")

    def _set_selected_map_system(self, system_id: str) -> None:
        system = self.application.campaign.get_system(system_id)
        self._selected_system = system_id
        self._planet_view = "DETAILS"
        selected = next(
            (obj for obj in system.objects if obj.habitable or obj.kind == "Planet"),
            system.objects[0],
        )
        self._selected_object = selected.object_id

    def _center_map_on(self, system_id: str) -> None:
        position = self._map_position(system_id)
        bounds = self._map_rect()
        self._map_pan += pygame.Vector2(bounds.center) - pygame.Vector2(position)
        self._clamp_map_pan()

    def _jump_to_next_bookmark(self) -> None:
        bookmarks = self.application.campaign.map_bookmarks
        visible_bookmarks = [
            system_id
            for system_id in bookmarks
            if self._is_system_visible(
                self.application.campaign.get_system(system_id)
            )
        ]
        if not visible_bookmarks:
            self.ui.notify("No map bookmarks")
            return
        current_index = (
            visible_bookmarks.index(self._selected_system)
            if self._selected_system in visible_bookmarks
            else -1
        )
        self._set_selected_map_system(
            visible_bookmarks[(current_index + 1) % len(visible_bookmarks)]
        )
        self._center_map_on(self._selected_system)

    def _search_map(self) -> bool:
        assert self.search is not None
        query = self.search.text.casefold().strip()
        sensor_system_ids = (
            self._sensor_system_ids() if self._fog_of_war else set()
        )
        matches = [
            system
            for system in self.application.campaign.systems
            if (
                query in system.name.casefold()
                or query in system.system_id.casefold()
            )
            and self._map_filter_matches(system)
            and self._is_system_visible(system, sensor_system_ids)
        ]
        if not matches:
            self.ui.notify(f"No system matches '{self.search.text.strip()}'")
            return False
        system = min(
            matches,
            key=lambda entry: (
                entry.name.casefold() != query,
                not entry.name.casefold().startswith(query),
                entry.name.casefold(),
            ),
        )
        self._set_selected_map_system(system.system_id)
        self._center_map_on(system.system_id)
        self.search.focused = False
        self.ui.notify(f"Located {system.name}")
        return True

    def _object_rows(self) -> list[tuple[str, str, str]]:
        system = self.application.campaign.get_system(self._selected_system)
        return [(obj.name, obj.kind, obj.world_type) for obj in system.objects]

    def _species_colony_label(self, colony: ColonyState) -> str:
        system = self.application.campaign.get_system(colony.system_id)
        planet = self.application.campaign.get_object(
            colony.system_id,
            colony.planet_id,
        )
        return f"{system.name} / {planet.name}"

    def _species_colony_rows(self) -> list[tuple[str, str, str]]:
        campaign = self.application.campaign
        rows = []
        for colony in sorted(
            campaign.player_colonies,
            key=lambda item: (
                campaign.get_system(item.system_id).name.casefold(),
                campaign.get_object(item.system_id, item.planet_id).name.casefold(),
            ),
        ):
            species = campaign.species_catalog[colony.species_id]
            rows.append(
                (
                    self._species_colony_label(colony),
                    species.name,
                    f"{colony.population_billions:.2f}B",
                )
            )
        return rows

    def _ensure_species_colony_selection(self) -> None:
        campaign = self.application.campaign
        selected = self._species_selected_colony
        if selected is not None:
            colony = campaign.colony_states.get(
                campaign.colony_key(*selected)
            )
            if colony is not None and colony in campaign.player_colonies:
                return
        colony = next(iter(campaign.player_colonies), None)
        self._species_selected_colony = (
            (colony.system_id, colony.planet_id)
            if colony is not None
            else None
        )

    def _selected_species_colony(self) -> ColonyState | None:
        self._ensure_species_colony_selection()
        if self._species_selected_colony is None:
            return None
        return self.application.campaign.colony_states.get(
            self.application.campaign.colony_key(
                *self._species_selected_colony
            )
        )

    def _refresh_species_destinations(self) -> None:
        if self._species_destination is None:
            return
        campaign = self.application.campaign
        source = self._selected_species_colony()
        destinations = (
            []
            if source is None
            else [
                colony
                for colony in campaign.player_colonies
                if colony is not source and colony.species_id == source.species_id
            ]
        )
        self._species_destination.options = (
            [self._species_colony_label(colony) for colony in destinations]
            or ["No matching colony"]
        )
        if self._species_destination.selected not in self._species_destination.options:
            self._species_destination.selected = self._species_destination.options[0]

    def _dropdown_options(self) -> list[str]:
        if self.tabs is not None and self.tabs.active == "DIPLOMACY":
            return [empire.name for empire in self.application.campaign.ai_empires]
        if self.tabs is not None and self.tabs.active == "SPECIES":
            return [
                "Citizen rights",
                "Resident rights",
                "Restricted rights",
                "Climate adaptation",
                "Enhanced growth",
                "Extended lifespan",
                "Synthetic conversion",
                "Migrate population",
            ]
        if self.tabs is not None and self.tabs.active == "EMPIRE":
            campaign = self.application.campaign
            return [
                campaign.game_content.buildings[building_id].name
                for building_id in campaign.building_options()
            ]
        if self.tabs is not None and self.tabs.active == "SYSTEM":
            kinds = dict.fromkeys(
                obj.kind
                for obj in self.application.campaign.get_system(
                    self._selected_system
                ).objects
            )
            return ["All", *kinds]
        return [
            "All",
            *dict.fromkeys(system.status for system in self.application.campaign.systems),
        ]

    def _diplomatic_action_options(self) -> list[str]:
        if self.tabs is None or self.tabs.active != "DIPLOMACY":
            return ["First contact pending"]
        campaign = self.application.campaign
        empire = next(
            (
                item
                for item in campaign.ai_empires
                if self.dropdown is not None
                and item.name == self.dropdown.selected
            ),
            campaign.ai_empires[0] if campaign.ai_empires else None,
        )
        if empire is None:
            return ["No known civilizations"]
        relation = campaign.get_relation(empire.empire_id)
        if not relation.first_contact:
            return ["First contact pending - survey their space"]
        actions = ["Send envoy"]
        treaty_labels = {
            "non_aggression": "Non-aggression pact",
            "trade": "Trade agreement",
            "research": "Research agreement",
            "defensive_alliance": "Defensive alliance",
        }
        for treaty_id, treaty_name in treaty_labels.items():
            if treaty_id not in relation.treaties and (
                treaty_id != "defensive_alliance"
                or "non_aggression" in relation.treaties
            ):
                actions.append(f"Propose {treaty_name.lower()}")
        actions.extend(
            f"Break {treaty_labels[treaty_id]}"
            for treaty_id in relation.treaties
        )
        if relation.at_war:
            actions.append("Negotiate peace")
        else:
            actions.append("Declare war")
        return actions

    def _configure_visible_widgets(self) -> None:
        assert self.tabs is not None
        assert self.search is not None
        assert self.dropdown is not None
        assert self.systems is not None
        assert self.action_button is not None
        assert self.speed_button is not None
        assert self.pause_button is not None
        assert self.scale_down is not None
        assert self.scale_up is not None
        assert self.contrast_button is not None
        common: list[FocusableWidget] = [
            self.tabs,
            self.speed_button,
            self.pause_button,
            self.scale_down,
            self.scale_up,
            self.contrast_button,
        ]
        compact = self.screen is not None and self.screen.get_height() < 560
        if self.tabs.active == "GALAXY" and compact:
            self._widgets = [self.tabs, *common[1:]]
        elif self.tabs.active == "GALAXY":
            self._widgets = [
                self.tabs,
                self.search,
                self.dropdown,
                self.systems,
                *common[1:],
            ]
        elif self.tabs.active == "SYSTEM" and compact:
            self._widgets = [self.tabs, self.action_button, *common[1:]]
        elif self.tabs.active == "SYSTEM":
            self._widgets = [
                self.tabs,
                self.dropdown,
                self.systems,
                self.action_button,
                *common[1:],
            ]
        elif self.tabs.active == "EMPIRE":
            assert self.research_button is not None
            assert self.create_fleet_button is not None
            assert self.move_fleet_button is not None
            self._widgets = [
                self.tabs,
                self.dropdown,
                self.action_button,
                self.research_button,
                self.create_fleet_button,
                self.move_fleet_button,
                *common[1:],
            ]
        elif self.tabs.active == "SPECIES":
            assert self._species_destination is not None
            self._widgets = [
                self.tabs,
                self.dropdown,
                self._species_destination,
                self.systems,
                self.action_button,
                *common[1:],
            ]
        elif self.tabs.active == "DIPLOMACY":
            assert self.diplomatic_action is not None
            self._widgets = [
                self.tabs,
                self.dropdown,
                self.diplomatic_action,
                self.action_button,
                *common[1:],
            ]
        else:
            self._widgets = common
        self._focusables = list(self._widgets)
        self.ui.set_focusables(self._focusables)

    def _map_rect(self) -> pygame.Rect:
        assert self.screen is not None
        panel_left = (
            self.overview.rect.left
            if self.overview is not None
            else self.screen.get_width() - 360
        )
        return pygame.Rect(
            16,
            66,
            max(1, panel_left - 30),
            max(
                1,
                self.screen.get_height()
                - (160 if self.screen.get_height() < 560 else 120),
            ),
        )

    def _map_position(self, system_id: str) -> tuple[int, int]:
        system = self.application.campaign.get_system(system_id)
        return self._galaxy_position(system.x, system.y)

    def _galaxy_position(self, x: float, y: float) -> tuple[int, int]:
        bounds = self._map_rect()
        return (
            round(
                bounds.centerx
                + (x - 0.5) * bounds.width * self._galaxy_zoom
                + self._map_pan.x
            ),
            round(
                bounds.centery
                + (y - 0.5) * bounds.height * self._galaxy_zoom
                + self._map_pan.y
            ),
        )

    def _zoom_galaxy_map(
        self,
        amount: float,
        anchor: tuple[int, int],
    ) -> None:
        old_zoom = self._galaxy_zoom
        new_zoom = min(
            self._GALAXY_ZOOM_MAX,
            max(self._GALAXY_ZOOM_MIN, old_zoom + amount),
        )
        if new_zoom == old_zoom:
            return
        bounds = self._map_rect()
        anchor_offset = pygame.Vector2(anchor) - pygame.Vector2(bounds.center)
        world_offset = (anchor_offset - self._map_pan) / old_zoom
        self._galaxy_zoom = new_zoom
        self._map_pan = anchor_offset - world_offset * new_zoom
        self._clamp_map_pan()

    def _clamp_map_pan(self) -> None:
        bounds = self._map_rect()
        pan_limit = (1.0 - self._GALAXY_ZOOM_MIN) / 2
        max_x = bounds.width * pan_limit
        max_y = bounds.height * pan_limit
        self._map_pan.x = min(max_x, max(-max_x, self._map_pan.x))
        self._map_pan.y = min(max_y, max(-max_y, self._map_pan.y))

    def _select_map_item(self, position: tuple[int, int]) -> bool:
        if self.tabs is not None and self.tabs.active == "SYSTEM":
            return self._select_system_object(position)
        sensor_system_ids = (
            self._sensor_system_ids() if self._fog_of_war else set()
        )
        candidates = [
            system
            for system in self.application.campaign.systems
            if self._map_filter_matches(system)
            and self._is_system_visible(system, sensor_system_ids)
        ]
        if not candidates:
            return False
        nearest = min(
            candidates,
            key=lambda system: pygame.Vector2(
                self._map_position(system.system_id)
            ).distance_squared_to(position),
        )
        if (
            pygame.Vector2(self._map_position(nearest.system_id)).distance_squared_to(position)
            > 30**2
        ):
            return False
        self._set_selected_map_system(nearest.system_id)
        return True

    def _map_layer_options(self) -> tuple[tuple[str, str], ...]:
        return (
            ("_show_borders", "OWNERS"),
            ("_show_fleets", "FLEETS"),
            ("_show_trade_routes", "TRADE"),
            ("_show_resources", "RES"),
            ("_show_sensors", "SENSE"),
            ("_fog_of_war", "FOG"),
            ("_show_exploration", "EXPLORE"),
        )

    def _map_layer_button_rects(
        self,
        bounds: pygame.Rect,
    ) -> list[tuple[str, str, pygame.Rect]]:
        options = self._map_layer_options()
        columns = 4
        gap = 6
        x = bounds.x + 12
        first_row_y = bounds.y + 48
        height = 26
        available_width = max(1, bounds.width - 24 - gap * (columns - 1))
        button_width = available_width // columns
        return [
            (
                attribute,
                label,
                pygame.Rect(
                    x + (index % columns) * (button_width + gap),
                    first_row_y + (index // columns) * (height + gap),
                    button_width
                    if index % columns < columns - 1
                    else bounds.right - 12 - (x + (index % columns) * (button_width + gap)),
                    height,
                ),
            )
            for index, (attribute, label) in enumerate(options)
        ]

    def _toggle_map_layer(self, attribute: str) -> None:
        setattr(self, attribute, not getattr(self, attribute))
        if attribute != "_fog_of_war":
            return
        if self._fog_of_war:
            sensor_system_ids = self._sensor_system_ids()
            selected = self.application.campaign.get_system(self._selected_system)
            if not self._is_system_visible(selected, sensor_system_ids):
                self._selected_system = next(
                    system.system_id
                    for system in self.application.campaign.systems
                    if self._is_system_visible(system, sensor_system_ids)
                )
                self._set_selected_map_system(self._selected_system)
        self._filter_content()

    def _handle_map_layer_click(self, position: tuple[int, int]) -> bool:
        if self.tabs is None or self.tabs.active != "GALAXY":
            return False
        for attribute, _, rect in self._map_layer_button_rects(self._map_rect()):
            if rect.collidepoint(position):
                self._toggle_map_layer(attribute)
                return True
        return False

    def _draw_map_layer_controls(self, bounds: pygame.Rect) -> None:
        assert self.screen is not None
        theme = self.ui.theme
        font = self.ui.fonts.get(12)
        for attribute, label, rect in self._map_layer_button_rects(bounds):
            active = getattr(self, attribute)
            surface = pygame.Surface(rect.size, pygame.SRCALPHA)
            fill = (*theme.accent, 48) if active else (5, 11, 22, 210)
            pygame.draw.rect(surface, fill, surface.get_rect(), border_radius=3)
            self.screen.blit(surface, rect.topleft)
            border = theme.accent if active else (64, 82, 105)
            pygame.draw.rect(self.screen, border, rect, 1, border_radius=3)
            color = theme.accent if active else theme.muted
            rendered = font.render(label, True, color)
            self.screen.blit(rendered, rendered.get_rect(center=rect.center))

    def _scaled_asset(self, name: str, size: tuple[int, int]) -> pygame.Surface:
        return self.assets.scaled(name, size)

    def _draw_galaxy_map(self) -> None:
        assert self.screen is not None
        bounds = self._map_rect()
        campaign = self.application.campaign
        theme = self.ui.theme
        territory_owners = sorted(
            {system.owner for system in campaign.systems if system.owner is not None}
        )
        sensor_system_ids = self._sensor_system_ids()
        visible_systems = [
            system
            for system in campaign.systems
            if self._is_system_visible(system, sensor_system_ids)
        ]
        trade_route_edges = (
            self._trade_route_edges() if self._show_trade_routes else set()
        )
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(bounds)
        nebula_colors = (
            (49, 124, 174),
            (112, 82, 166),
            (44, 131, 146),
        )
        for index, nebula in enumerate(campaign.galaxy.nebulae):
            if self._fog_of_war and not any(
                math.dist((system.x, system.y), (nebula.x, nebula.y))
                <= nebula.radius
                for system in visible_systems
            ):
                continue
            position = self._galaxy_position(nebula.x, nebula.y)
            size = (
                max(24, round(nebula.radius * bounds.width * 2.8)),
                max(20, round(nebula.radius * bounds.height * 2.2)),
            )
            color = nebula_colors[index % len(nebula_colors)]
            cache_key = size, color
            cloud = self._nebula_cache.get(cache_key)
            if cloud is None:
                cloud = pygame.Surface(size, pygame.SRCALPHA)
                for scale, alpha in ((1.0, 7), (0.72, 10), (0.42, 14)):
                    rect = pygame.Rect(0, 0, *size)
                    rect.inflate_ip(
                        -round(size[0] * (1 - scale)),
                        -round(size[1] * (1 - scale)),
                    )
                    rect.center = (size[0] // 2, size[1] // 2)
                    pygame.draw.ellipse(cloud, (*color, alpha), rect)
                self._nebula_cache[cache_key] = cloud
            self.screen.blit(cloud, cloud.get_rect(center=position))

        if self._show_borders:
            self._draw_territory_layer(bounds, campaign.systems)

        connections: set[str] = set()
        for first_id, second_id in campaign.routes:
            if first_id == self._selected_system:
                connections.add(second_id)
            elif second_id == self._selected_system:
                connections.add(first_id)
        for first_id, second_id in campaign.routes:
            selected_route = self._selected_system in (first_id, second_id)
            first = campaign.get_system(first_id)
            second = campaign.get_system(second_id)
            if (
                not self._is_system_visible(first, sensor_system_ids)
                or not self._is_system_visible(second, sensor_system_ids)
                or not self._map_filter_matches(first)
                or not self._map_filter_matches(second)
            ):
                continue
            if selected_route:
                route_color = (87, 205, 220)
            elif first.colonized or second.colonized:
                route_color = (56, 117, 125)
            else:
                route_color = (50, 79, 105)
            pygame.draw.line(
                self.screen,
                theme.accent if selected_route and self.ui.high_contrast else route_color,
                self._map_position(first_id),
                self._map_position(second_id),
                2 if selected_route else 1,
            )
            if (
                self._show_trade_routes
                and tuple(sorted((first_id, second_id))) in trade_route_edges
            ):
                pygame.draw.line(
                    self.screen,
                    (241, 195, 91),
                    self._map_position(first_id),
                    self._map_position(second_id),
                    2,
                )
        label_candidates: list[tuple[int, StarSystem, tuple[int, int]]] = []
        for system in campaign.systems:
            if (
                not self._is_system_visible(system, sensor_system_ids)
                or not self._map_filter_matches(system)
            ):
                continue
            position = self._map_position(system.system_id)
            status_color = (
                theme.accent
                if system.colonized
                else theme.warning
                if system.surveyed
                else theme.muted
            )
            radius = 8 if system.system_id == self._selected_system else 5
            pygame.draw.circle(self.screen, status_color, position, radius + 3, 1)
            if self._show_sensors and system.system_id in sensor_system_ids:
                pygame.draw.circle(self.screen, (78, 196, 228), position, radius + 7, 1)
            if self._show_exploration and system.surveyed:
                pygame.draw.circle(self.screen, (104, 223, 157), position, radius + 5, 2)
            system_kinds = {obj.kind for obj in system.objects}
            if "Gateway" in system_kinds:
                pygame.draw.circle(self.screen, (255, 207, 123), position, radius + 6, 1)
            elif "Wormhole" in system_kinds:
                pygame.draw.circle(self.screen, (89, 217, 226), position, radius + 6, 1)
            elif "Anomaly" in system_kinds:
                pygame.draw.circle(self.screen, (197, 142, 255), position, radius + 6, 1)
            if system.star_type in ("Black hole", "Neutron star"):
                pygame.draw.circle(self.screen, (183, 142, 255), position, radius + 3, 2)
                pygame.draw.circle(
                    self.screen,
                    (9, 8, 18) if system.star_type == "Black hole" else (196, 223, 255),
                    position,
                    radius,
                )
            else:
                star_color = self._star_color(system.star_type, status_color)
                pygame.draw.circle(self.screen, star_color, position, radius)
                if system.companion_star_type is not None:
                    pygame.draw.circle(
                        self.screen,
                        self._star_color(system.companion_star_type, theme.warning),
                        (position[0] + radius, position[1] - radius),
                        max(2, radius // 2),
                    )
            if system.system_id == self._selected_system:
                pygame.draw.circle(
                    self.screen,
                    (25, 115, 137),
                    position,
                    radius + 12,
                    1,
                )
                pygame.draw.circle(
                    self.screen,
                    theme.text,
                    position,
                    radius + 7,
                    1,
                )
                pygame.draw.line(
                    self.screen,
                    (114, 216, 226),
                    (position[0] - radius - 5, position[1]),
                    (position[0] + radius + 5, position[1]),
                    1,
                )
                pygame.draw.line(
                    self.screen,
                    (114, 216, 226),
                    (position[0], position[1] - radius - 5),
                    (position[0], position[1] + radius + 5),
                    1,
                )
            if system.system_id in campaign.map_bookmarks:
                pygame.draw.circle(self.screen, (255, 220, 112), position, radius + 13, 1)
            if self._show_resources and system.surveyed:
                resources = sum(
                    amount
                    for obj in system.objects
                    if obj.surveyed
                    for amount in obj.resources.values()
                )
                if resources:
                    marker = (position[0] + 8, position[1] - 8)
                    pygame.draw.circle(self.screen, (255, 203, 100), marker, 3)
                    if self._galaxy_zoom >= 0.62:
                        self._label(
                            f"R{resources}",
                            (marker[0] + 4, marker[1] - 6),
                            self.ui.fonts.get(12),
                            (255, 203, 100),
                        )
            label_priority = (
                0
                if system.system_id == self._selected_system
                else 1
                if system.colonized
                else 2
                if system.surveyed
                else 3
                if system.system_id in connections
                else 4
            )
            if label_priority < 4 or self._galaxy_zoom >= 0.82:
                label_candidates.append((label_priority, system, position))

        if self._show_fleets:
            for fleet in campaign.all_fleets:
                if fleet.ship_count <= 0:
                    continue
                if (
                    self._fog_of_war
                    and fleet.system_id not in sensor_system_ids
                    and (not fleet.route or fleet.route[0] not in sensor_system_ids)
                ):
                    continue
                fleet_position = self._galaxy_position(
                    *campaign.fleet_position(fleet)
                )
                pygame.draw.polygon(
                    self.screen,
                    (110, 231, 245)
                    if fleet.owner_id == "union"
                    else (255, 123, 111),
                    (
                        (fleet_position[0], fleet_position[1] - 9),
                        (fleet_position[0] + 7, fleet_position[1] + 6),
                        (fleet_position[0] - 7, fleet_position[1] + 6),
                    ),
                )
                if self._galaxy_zoom >= 0.62:
                    self._label(
                        fleet.name,
                        (fleet_position[0] + 10, fleet_position[1] - 6),
                        self.ui.fonts.get(12),
                        (110, 231, 245)
                        if fleet.owner_id == "union"
                        else (255, 123, 111),
                    )

        label_font = self.ui.fonts.get(13)
        occupied_labels: list[pygame.Rect] = []
        for _, system, position in sorted(
            label_candidates,
            key=lambda candidate: (
                candidate[0],
                candidate[1].name,
            ),
        ):
            if (
                self._galaxy_zoom < 0.62
                and system.system_id != self._selected_system
                and not system.surveyed
                and not system.colonized
            ):
                continue
            label = label_font.render(
                system.name,
                True,
                theme.accent if system.system_id == self._selected_system else theme.text,
            )
            label_rect = label.get_rect(midleft=(position[0] + 11, position[1]))
            if label_rect.right > bounds.right:
                label_rect.midright = (position[0] - 11, position[1])
            if (
                system.system_id != self._selected_system
                and any(label_rect.colliderect(existing) for existing in occupied_labels)
            ):
                continue
            self.screen.blit(label, label_rect)
            occupied_labels.append(label_rect)

        self.screen.set_clip(previous_clip)
        pygame.draw.rect(self.screen, theme.muted, bounds, 1)
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(bounds)
        header = pygame.Surface((max(1, bounds.width - 8), 136), pygame.SRCALPHA)
        pygame.draw.rect(
            header,
            (5, 11, 22, 220),
            header.get_rect(),
            border_radius=5,
        )
        self.screen.blit(header, (bounds.x + 4, bounds.y + 4))
        self._label(
            (
                f"{campaign.galaxy.name.upper()}  /  "
                f"{campaign.galaxy.region_name.upper()}  /  "
                f"{campaign.galaxy.morphology.upper()}"
            ),
            (bounds.x + 12, bounds.y + 8),
            self.ui.fonts.get(14),
            theme.text,
        )
        self._label(
            (
                f"{len(visible_systems) if self._fog_of_war else len(campaign.systems)} "
                f"STARS  /  SEED {campaign.galaxy.seed}  /  "
                f"{campaign.galaxy.diameter_light_years:,} LY  /  {self._galaxy_zoom:.1f}x"
            ),
            (bounds.x + 12, bounds.y + 28),
            self.ui.fonts.get(14),
            theme.muted,
        )
        self._draw_map_layer_controls(bounds)
        legend_y = bounds.y + 111
        legend_x = bounds.x + 12
        if self._show_borders:
            for owner in territory_owners:
                color = self._owner_color(owner, territory_owners)
                pygame.draw.circle(self.screen, color, (legend_x + 4, legend_y + 5), 3)
                self._label(
                    owner.upper(),
                    (legend_x + 12, legend_y),
                    self.ui.fonts.get(12),
                    theme.muted,
                )
                legend_x += self.ui.fonts.get(12).size(owner.upper())[0] + 26
                if legend_x > bounds.right - 72:
                    break
        else:
            self._label(
                "POLITICAL BORDERS HIDDEN",
                (legend_x, legend_y),
                self.ui.fonts.get(12),
                theme.muted,
            )
        self.screen.set_clip(previous_clip)

    def _draw_map_card(self) -> None:
        assert self.screen is not None
        bounds = self._map_rect()
        if bounds.height < 340:
            return
        theme = self.ui.theme
        card = pygame.Rect(bounds.x + 8, bounds.bottom - 106, bounds.width - 16, 96)
        pygame.draw.rect(self.screen, (5, 12, 24), card, border_radius=5)
        pygame.draw.rect(self.screen, (53, 89, 112), card, 1, border_radius=5)
        pygame.draw.line(
            self.screen,
            theme.accent,
            (card.x + 2, card.y + 10),
            (card.x + 2, card.bottom - 10),
            2,
        )
        system = self.application.campaign.get_system(self._selected_system)
        image_center = (card.x + 54, card.centery)
        pygame.draw.circle(self.screen, (48, 113, 144), image_center, 29, 1)
        pygame.draw.circle(
            self.screen,
            self._star_color(system.star_type, theme.accent),
            image_center,
            9,
        )
        if system.companion_star_type is not None:
            pygame.draw.circle(
                self.screen,
                self._star_color(system.companion_star_type, theme.warning),
                (image_center[0] + 13, image_center[1] + 6),
                5,
            )
        text_x = card.x + 100
        max_width = card.right - text_x - 8
        font = self.ui.fonts.get(16)
        status_color = (
            theme.accent
            if system.colonized
            else theme.warning
            if system.surveyed
            else theme.muted
        )
        self._label(
            system.name.upper(),
            (text_x, card.y + 7),
            font,
            theme.accent,
        )
        self._label(
            (
                f"{system.status.upper()}  |  {system.star_type}  |  "
                f"{system.mass_solar:.2f} M_sun  |  "
                f"{system.owner.upper() if system.owner else 'UNCLAIMED'}"
            ),
            (text_x, card.y + 27),
            self.ui.fonts.get(12),
            status_color,
        )
        description_font = self.ui.fonts.get(14)
        description = self._wrap_text(
            description_font,
            system.description,
            max_width,
        )
        if description:
            self._label(description[0], (text_x, card.y + 50), description_font, theme.text)
        objective_font = self.ui.fonts.get(13)
        objective = self._wrap_text(
            objective_font,
            (
                f"{'BOOKMARKED  |  ' if system.system_id in self.application.campaign.map_bookmarks else ''}"
                f"OBJECTIVE: {self.application.campaign.objective}"
            ),
            max_width,
        )
        if objective:
            self._label(objective[0], (text_x, card.y + 70), objective_font, theme.warning)

    def _system_object_position(self, object_id: str) -> tuple[int, int]:
        bounds = self._map_rect()
        system = self.application.campaign.get_system(self._selected_system)
        system_object = self.application.campaign.get_object(
            self._selected_system,
            object_id,
        )
        if system_object.parent_id is not None:
            parent_x, parent_y = self._system_object_position(system_object.parent_id)
            parent = self.application.campaign.get_object(
                self._selected_system,
                system_object.parent_id,
            )
            parent_index = system.objects.index(parent)
            angle = parent_index * 2.4 + self.application.campaign.elapsed_days * 0.0005
            moon_distance = max(14, parent.size * 2.1)
            return (
                round(parent_x + math.cos(angle) * moon_distance),
                round(parent_y + math.sin(angle) * moon_distance),
            )
        if system_object.kind == "Asteroid belt":
            orbit_radius = (
                min(bounds.width, bounds.height)
                * 0.43
                * self._system_zoom
                * min(0.94, system_object.orbit)
            )
            return (round(bounds.centerx + orbit_radius), bounds.centery)
        index = system.objects.index(system_object)
        angle = index * 2.399 + self.application.campaign.elapsed_days * 0.00015
        orbit_radius = (
            min(bounds.width, bounds.height)
            * 0.43
            * self._system_zoom
            * system_object.orbit
        )
        return (
            round(bounds.centerx + math.cos(angle) * orbit_radius),
            round(bounds.centery + math.sin(angle) * orbit_radius),
        )

    def _draw_system_map(self) -> None:
        assert self.screen is not None
        bounds = self._map_rect()
        system = self.application.campaign.get_system(self._selected_system)
        theme = self.ui.theme
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(bounds)
        center = bounds.center
        base_radius = min(bounds.width, bounds.height) * 0.43 * self._system_zoom
        for system_object in system.objects:
            if system_object.parent_id is not None:
                continue
            orbit_radius = base_radius * system_object.orbit
            pygame.draw.circle(
                self.screen,
                (47, 76, 105),
                center,
                max(1, round(orbit_radius)),
                1,
            )
            if system_object.kind == "Asteroid belt":
                for rock_index in range(88):
                    angle = rock_index * math.tau / 88
                    radius = orbit_radius + math.sin(rock_index * 12.1) * 3
                    rock = (
                        round(center[0] + math.cos(angle) * radius),
                        round(center[1] + math.sin(angle) * radius),
                    )
                    pygame.draw.circle(
                        self.screen,
                        (144, 129, 106),
                        rock,
                        1 + rock_index % 2,
                    )

        if system.star_type == "Black hole":
            pygame.draw.ellipse(
                self.screen,
                (230, 129, 87),
                pygame.Rect(center[0] - 30, center[1] - 12, 60, 24),
                3,
            )
            pygame.draw.circle(self.screen, (5, 6, 14), center, 15)
        elif system.star_type == "Neutron star":
            pygame.draw.circle(self.screen, (138, 197, 255), center, 20)
            pygame.draw.circle(self.screen, (228, 245, 255), center, 9)
            pygame.draw.line(
                self.screen,
                (149, 210, 255),
                (center[0] - 33, center[1] - 22),
                (center[0] + 33, center[1] + 22),
                2,
            )
        else:
            star_color = self._star_color(system.star_type, (255, 207, 123))
            if system.companion_star_type is None:
                pygame.draw.circle(self.screen, (109, 81, 52), center, 26)
                pygame.draw.circle(self.screen, star_color, center, 17)
                pygame.draw.circle(self.screen, (255, 250, 230), (center[0] - 5, center[1] - 5), 6)
            else:
                companion_type = system.companion_star_type
                assert companion_type is not None
                for star_position, star_type in (
                    ((center[0] - 9, center[1]), system.star_type),
                    ((center[0] + 9, center[1]), companion_type),
                ):
                    pygame.draw.circle(self.screen, (109, 81, 52), star_position, 18)
                    pygame.draw.circle(
                        self.screen,
                        self._star_color(star_type, (255, 207, 123)),
                        star_position,
                        12,
                    )
        for system_object in system.objects:
            position = self._system_object_position(system_object.object_id)
            if system_object.kind == "Wormhole":
                pygame.draw.ellipse(
                    self.screen,
                    (84, 209, 218),
                    pygame.Rect(position[0] - 13, position[1] - 8, 26, 16),
                    3,
                )
                pygame.draw.ellipse(
                    self.screen,
                    (173, 135, 243),
                    pygame.Rect(position[0] - 8, position[1] - 13, 16, 26),
                    2,
                )
            elif system_object.kind == "Gateway":
                try:
                    gateway_art = self._scaled_asset(
                        "Anomalies/ancient gateway.jpg",
                        (48, 32),
                    )
                except AssetError as error:
                    logger.debug("Gateway illustration unavailable: %s", error)
                else:
                    self.screen.blit(gateway_art, gateway_art.get_rect(center=position))
                pygame.draw.circle(self.screen, (120, 213, 227), position, 18, 3)
                pygame.draw.circle(self.screen, (183, 142, 255), position, 11, 2)
            elif system_object.kind == "Anomaly":
                pygame.draw.polygon(
                    self.screen,
                    theme.warning if not system_object.surveyed else theme.accent,
                    [
                        (position[0], position[1] - 10),
                        (position[0] + 9, position[1]),
                        (position[0], position[1] + 10),
                        (position[0] - 9, position[1]),
                    ],
                )
            elif system_object.kind != "Asteroid belt":
                color = self._planet_color(system_object)
                pygame.draw.circle(self.screen, (12, 19, 34), position, system_object.size + 5)
                pygame.draw.circle(self.screen, color, position, system_object.size)
                pygame.draw.circle(
                    self.screen,
                    (min(255, color[0] + 50), min(255, color[1] + 50), min(255, color[2] + 50)),
                    (position[0] - max(1, system_object.size // 3), position[1] - max(1, system_object.size // 3)),
                    max(2, system_object.size // 3),
                )
                if system_object.kind == "Gas giant":
                    pygame.draw.ellipse(
                        self.screen,
                        (191, 176, 150),
                        pygame.Rect(position[0] - 23, position[1] - 6, 46, 12),
                        2,
                    )
            if system_object.object_id == self._selected_object:
                pygame.draw.circle(self.screen, theme.text, position, system_object.size + 8, 1)
            label = self.ui.fonts.get(14).render(system_object.name, True, theme.text)
            label_rect = label.get_rect(midleft=(position[0] + 12, position[1]))
            if label_rect.right > bounds.right:
                label_rect.midright = (position[0] - 12, position[1])
            self.screen.blit(label, label_rect)
        pygame.draw.rect(self.screen, theme.muted, bounds, 1)
        title = self.ui.fonts.get(16).render(
            f"{system.name.upper()} SYSTEM  /  {len(system.objects)} ORBITAL OBJECTS",
            True,
            theme.muted,
        )
        self.screen.blit(title, (bounds.x + 12, bounds.y + 8))
        zoom_label = self.ui.fonts.get(14).render(
            f"ORBITAL SCALE {self._system_zoom:.1f}x  |  WHEEL TO ZOOM",
            True,
            theme.muted,
        )
        self.screen.blit(zoom_label, (bounds.x + 12, bounds.bottom - 24))
        self.screen.set_clip(previous_clip)

    @staticmethod
    def _planet_color(system_object: SystemObject) -> tuple[int, int, int]:
        world = system_object.world_type.casefold()
        if "ocean" in world:
            return (42, 119, 161)
        if "jungle" in world or "temperate" in world:
            return (57, 134, 83)
        if "desert" in world or "arid" in world:
            return (194, 139, 77)
        if "arctic" in world or "icy" in world:
            return (139, 203, 218)
        if "volcanic" in world or "scorched" in world:
            return (176, 76, 56)
        if "gas" in world:
            return (186, 152, 108)
        return (115, 123, 151)

    @staticmethod
    def _star_color(
        star_type: str,
        fallback: tuple[int, int, int],
    ) -> tuple[int, int, int]:
        return {
            "M-type": (255, 145, 105),
            "K-type": (255, 190, 125),
            "G-type": (255, 220, 150),
            "F-type": (255, 239, 207),
            "A-type": (190, 218, 255),
            "B-type": (133, 176, 255),
            "O-type": (128, 156, 255),
            "White dwarf": (213, 230, 255),
            "Neutron star": (147, 204, 255),
            "Black hole": (20, 17, 35),
        }.get(star_type, fallback)

    def _select_system_object(self, position: tuple[int, int]) -> bool:
        system = self.application.campaign.get_system(self._selected_system)
        closest = min(
            system.objects,
            key=lambda obj: pygame.Vector2(
                self._system_object_position(obj.object_id)
            ).distance_squared_to(position),
        )
        if (
            pygame.Vector2(
                self._system_object_position(closest.object_id)
            ).distance_squared_to(position)
            > 24**2
        ):
            return False
        self._selected_object = closest.object_id
        self._planet_view = "DETAILS"
        self._filter_content()
        return True

    def _draw_system_details(self, font: pygame.font.Font, compact: bool) -> None:
        assert self.screen is not None
        assert self.systems is not None
        system = self.application.campaign.get_system(self._selected_system)
        theme = self.ui.theme
        left = self.systems.rect.x + 2
        y = self.systems.rect.y + 4 if compact else self.systems.rect.bottom + 5
        self._label(
            f"{system.name.upper()}  /  {system.status.upper()}",
            (left, y),
            font,
            theme.accent,
        )
        self._label(
            (
                f"{system.star_type}  |  {system.mass_solar:.2f} M_sun  |  "
                f"{system.age_gyr:.1f} Gyr  |  {system.status}"
            ),
            (left, y + 22),
            self.ui.fonts.get(15),
            theme.text,
        )
        if system.companion_star_type is not None:
            self._label(
                (
                    f"BINARY: {system.companion_star_type} companion at "
                    f"{system.binary_separation_au:.2f} AU"
                ),
                (left, y + 42),
                self.ui.fonts.get(13),
                theme.warning,
            )
        if compact:
            objective_font = self.ui.fonts.get(13)
            objective_y = y + 44 + (18 if system.companion_star_type else 0)
            for index, line in enumerate(
                self._wrap_text(
                    objective_font,
                    f"OBJECTIVE: {self.application.campaign.objective}",
                    self.systems.rect.width - 6,
                )[:2]
            ):
                self._label(
                    line,
                    (left, objective_y + index * 15),
                    objective_font,
                    theme.warning,
                )
            description = self._wrap_text(
                self.ui.fonts.get(14),
                system.description,
                self.systems.rect.width - 6,
            )
            for index, line in enumerate(description[:2]):
                self._label(
                    line,
                    (left, objective_y + 32 + index * 17),
                    self.ui.fonts.get(14),
                    theme.text,
                )

    def _draw_object_details(self, font: pygame.font.Font, compact: bool) -> None:
        assert self.screen is not None
        assert self.systems is not None
        system_object = self.application.campaign.get_object(
            self._selected_system,
            self._selected_object,
        )
        theme = self.ui.theme
        left = self.systems.rect.x + 2
        y = self.systems.rect.y + 4 if compact else self.systems.rect.bottom + 5
        is_planet = system_object.is_planet or system_object.kind == "Moon"
        if is_planet and self._planet_view == "MANAGEMENT":
            self._draw_planet_management(system_object, font, left, y)
            return
        if is_planet and self._planet_view == "HISTORY":
            self._draw_planet_history(system_object, font, left, y, compact)
            return
        if is_planet and system_object.surveyed:
            self._draw_planet_dossier(system_object, left, y, compact)
            return
        self._label(
            "M MANAGEMENT  |  H HISTORY  |  D DETAILS",
            (left, y),
            self.ui.fonts.get(12),
            theme.muted,
        )
        y += 18
        status = (
            "COLONIZED"
            if system_object.colonized
            else "SURVEYED"
            if system_object.surveyed
            else "UNSURVEYED"
        )
        self._label(
            f"{system_object.name.upper()}  /  {status}",
            (left, y),
            font,
            theme.accent,
        )
        self._label(
            f"{system_object.kind}  |  {system_object.world_type}",
            (left, y + 22),
            self.ui.fonts.get(15),
            theme.text,
        )
        description_font = self.ui.fonts.get(14)
        lines = self._wrap_text(
            description_font,
            system_object.description,
            self.systems.rect.width - 6,
        )
        for index, line in enumerate(lines[:3]):
            self._label(
                line,
                (left, y + 43 + index * 17),
                description_font,
                theme.text,
            )
        detail_y = y + 96
        if system_object.orbit_distance_km is not None:
            physical_data = (
                f"ORBIT {system_object.orbit_distance_km:,.0f} km from parent"
            )
            if system_object.orbit_period_days is not None:
                physical_data += f"  |  PERIOD {system_object.orbit_period_days:.1f} days"
            if system_object.parent_id is not None:
                parent = self.application.campaign.get_object(
                    self._selected_system,
                    system_object.parent_id,
                )
                physical_data += f"  |  PARENT {parent.name}"
            self._label(physical_data, (left, detail_y), description_font, theme.warning)
            detail_y += 17
        elif system_object.orbit_au is not None:
            physical_data = f"ORBIT {system_object.orbit_au:.2f} AU"
            if system_object.mass_earth is not None:
                physical_data += f"  |  MASS {system_object.mass_earth:.1f} M_earth"
            if system_object.radius_earth is not None:
                physical_data += f"  |  RADIUS {system_object.radius_earth:.1f} R_earth"
            if system_object.gravity_earth is not None:
                physical_data += f"  |  GRAVITY {system_object.gravity_earth:.2f} g"
            if system_object.orbit_period_days is not None:
                physical_data += f"  |  YEAR {system_object.orbit_period_days:.1f} d"
            for index, line in enumerate(
                self._wrap_text(
                    description_font,
                    physical_data,
                    self.systems.rect.width - 6,
                )[:2]
            ):
                self._label(line, (left, detail_y), description_font, theme.warning)
                detail_y += 17
        if is_planet:
            environment = (
                f"CLIMATE {system_object.climate}  |  "
                f"ATMOSPHERE {system_object.atmosphere}"
            )
            for line in self._wrap_text(
                description_font,
                environment,
                self.systems.rect.width - 6,
            )[:2]:
                self._label(line, (left, detail_y), description_font, theme.text)
                detail_y += 17
        if system_object.surveyed and system_object.resources:
            deposits = "DEPOSITS: " + "  ".join(
                f"{name} {amount}"
                for name, amount in system_object.resources.items()
            )
            for line in self._wrap_text(
                description_font,
                deposits,
                self.systems.rect.width - 6,
            )[:2]:
                self._label(line, (left, detail_y), description_font, theme.warning)
                detail_y += 17

    def _draw_planet_dossier(
        self,
        planet: SystemObject,
        left: int,
        y: int,
        compact: bool,
    ) -> None:
        assert self.screen is not None
        assert self.systems is not None
        theme = self.ui.theme
        width = self.systems.rect.width - 6
        self._label(
            "M MANAGEMENT  |  H HISTORY  |  D PLANET DETAILS",
            (left, y),
            self.ui.fonts.get(11 if compact else 12),
            theme.muted,
        )

        image_size = 52 if compact else 64
        image_rect = pygame.Rect(left, y + 22, image_size, image_size)
        self._draw_planet_illustration(planet, image_rect)
        text_left = image_rect.right + 10
        self._label(
            planet.name.upper(),
            (text_left, y + 24),
            self.ui.fonts.get(14 if compact else 16),
            theme.accent,
        )
        self._label(
            f"{planet.world_type.upper()}  /  {planet.kind.upper()}",
            (text_left, y + 45),
            self.ui.fonts.get(10 if compact else 11),
            theme.text,
        )
        self._label(
            (
                f"COLONY  {planet.owner or 'NONE'}"
                if planet.colonized
                else "SURVEY COMPLETE  /  NO SETTLEMENT"
            ),
            (text_left, y + 63),
            self.ui.fonts.get(10 if compact else 11),
            theme.warning if planet.colonized else theme.muted,
        )
        if planet.orbit_au is not None and not compact:
            self._label(
                f"ORBIT  {planet.orbit_au:.2f} AU",
                (text_left, y + 80),
                self.ui.fonts.get(10 if compact else 11),
                theme.muted,
            )

        details_y = image_rect.bottom + 5
        gap = 8
        column_width = max(1, (width - gap) // 2)
        population = planet.population if planet.colonized else "Unsettled"
        capacity = (
            f"{planet.population_capacity_billions:.1f}B"
            if planet.population_capacity_billions > 0
            else "Not suitable"
        )
        stats = (
            ("POPULATION", population),
            ("CAPACITY", capacity),
            ("CLIMATE", planet.climate),
            (
                "HABITABILITY",
                "Habitable" if planet.habitable else "Hostile",
            ),
            (
                "GRAVITY",
                f"{planet.gravity_earth:.2f} g"
                if planet.gravity_earth is not None
                else "Unknown",
            ),
            ("ATMOSPHERE", planet.atmosphere),
        )
        if compact:
            stats = stats[:4]
        row_height = 27 if compact else 25
        row_gap = 3 if compact else 2
        for index, (label, value) in enumerate(stats):
            column = index % 2
            row = index // 2
            rect = pygame.Rect(
                left + column * (column_width + gap),
                details_y + row * (row_height + row_gap),
                column_width,
                row_height,
            )
            pygame.draw.rect(self.screen, theme.panel_alt, rect, border_radius=3)
            pygame.draw.rect(self.screen, (47, 76, 98), rect, 1, border_radius=3)
            self._label(
                label,
                (rect.x + 6, rect.y + 3),
                self.ui.fonts.get(12),
                theme.muted,
            )
            self._label(
                value,
                (rect.x + 6, rect.y + 13),
                self.ui.fonts.get(12),
                theme.text if label not in ("POPULATION", "HABITABILITY") else theme.accent,
            )

        rows = (len(stats) + 1) // 2
        terrain_y = details_y + rows * (row_height + row_gap) + 1
        self._label(
            "TERRAIN",
            (left, terrain_y),
            self.ui.fonts.get(12),
            theme.muted,
        )
        terrain_lines = self._wrap_text(
            self.ui.fonts.get(12),
            planet.surface_conditions,
            width,
        )
        for index, line in enumerate(terrain_lines[:1] if compact else terrain_lines[:2]):
            self._label(
                line,
                (left, terrain_y + 14 + index * 14),
                self.ui.fonts.get(12),
                theme.text,
            )
        if planet.surveyed and planet.resources:
            deposits = "DEPOSITS  " + "  /  ".join(
                f"{name} {amount}" for name, amount in planet.resources.items()
            )
            deposit_y = terrain_y + (27 if compact else 40)
            self._label(
                deposits,
                (left, deposit_y),
                self.ui.fonts.get(12),
                theme.warning,
            )

    def _draw_planet_illustration(
        self,
        planet: SystemObject,
        rect: pygame.Rect,
    ) -> None:
        assert self.screen is not None
        key = (
            self._selected_system,
            planet.object_id,
            planet.world_type,
            rect.size,
        )
        illustration = self._planet_illustration_cache.get(key)
        if illustration is not None:
            self.screen.blit(illustration, rect.topleft)
            return

        illustration = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(illustration, (5, 11, 22), illustration.get_rect(), border_radius=5)
        pygame.draw.rect(illustration, (45, 80, 105), illustration.get_rect(), 1, border_radius=5)
        center = rect.center
        center = center[0] - rect.x, center[1] - rect.y
        radius = max(12, min(rect.width, rect.height) // 2 - 9)
        seed_key = f"{self._selected_system}:{planet.object_id}"
        seed = sum((index + 1) * ord(char) for index, char in enumerate(seed_key))
        rng = random.Random(seed)
        base_color = self._planet_color(planet)
        orb = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        orb_center = (radius, radius)
        pygame.draw.circle(orb, base_color, orb_center, radius)

        features = pygame.Surface(orb.get_size(), pygame.SRCALPHA)
        world = planet.world_type.casefold()
        if "gas" in world:
            band_colors = ((223, 185, 133, 180), (124, 96, 75, 170), (238, 210, 164, 170))
            for index, band_y in enumerate(range(8, radius * 2, max(8, radius // 3))):
                band = pygame.Rect(
                    -radius // 2,
                    band_y,
                    radius * 3,
                    max(3, radius // 5),
                )
                pygame.draw.ellipse(
                    features,
                    band_colors[index % len(band_colors)],
                    band,
                )
        else:
            terrain_color = (
                (72, 151, 92)
                if any(kind in world for kind in ("temperate", "jungle"))
                else (184, 145, 87)
                if any(kind in world for kind in ("desert", "arid"))
                else (205, 225, 228)
                if any(kind in world for kind in ("arctic", "ice", "frozen"))
                else (91, 104, 119)
                if any(kind in world for kind in ("barren", "airless"))
                else (108, 128, 74)
                if "toxic" in world
                else (165, 77, 54)
                if any(kind in world for kind in ("volcanic", "scorched"))
                else (65, 145, 92)
            )
            for _ in range(8):
                feature_center = (
                    rng.randrange(-radius // 2, radius * 2 + radius // 2),
                    rng.randrange(-radius // 3, radius * 2 + radius // 3),
                )
                feature_radius = rng.randrange(max(3, radius // 7), max(5, radius // 2))
                points = []
                for point_index in range(8):
                    angle = point_index * math.tau / 8
                    scale = rng.uniform(0.65, 1.15)
                    points.append(
                        (
                            round(feature_center[0] + math.cos(angle) * feature_radius * scale),
                            round(feature_center[1] + math.sin(angle) * feature_radius * scale),
                        )
                    )
                pygame.draw.polygon(features, (*terrain_color, 190), points)
            if "ocean" in world or "temperate" in world or "jungle" in world:
                for _ in range(4):
                    cloud_center = (
                        rng.randrange(radius * 2),
                        rng.randrange(radius * 2),
                    )
                    pygame.draw.ellipse(
                        features,
                        (205, 225, 232, 65),
                        pygame.Rect(*cloud_center, radius // 2 + 3, max(2, radius // 7)),
                    )
            elif any(kind in world for kind in ("arctic", "ice", "frozen")):
                pygame.draw.ellipse(
                    features,
                    (231, 244, 241, 220),
                    pygame.Rect(radius // 2, 1, radius, max(5, radius // 3)),
                )
                pygame.draw.ellipse(
                    features,
                    (231, 244, 241, 210),
                    pygame.Rect(radius // 2, radius * 2 - radius // 3, radius, radius // 3),
                )
            elif any(kind in world for kind in ("volcanic", "scorched")):
                for _ in range(4):
                    point = (rng.randrange(radius * 2), rng.randrange(radius * 2))
                    pygame.draw.circle(features, (255, 170, 72, 210), point, max(2, radius // 10))
                    pygame.draw.circle(features, (59, 38, 38, 220), point, max(1, radius // 16))

        mask = pygame.mask.from_surface(orb)
        mask_surface = mask.to_surface(
            setcolor=(255, 255, 255, 255),
            unsetcolor=(0, 0, 0, 0),
        )
        features.blit(mask_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        orb.blit(features, (0, 0))
        shadow = pygame.Surface(orb.get_size(), pygame.SRCALPHA)
        pygame.draw.ellipse(
            shadow,
            (4, 8, 20, 118),
            pygame.Rect(radius, -radius // 3, radius * 2, radius * 8 // 3),
        )
        shadow.blit(mask_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        orb.blit(shadow, (0, 0))

        if "gas" in world:
            pygame.draw.ellipse(
                illustration,
                (184, 154, 119),
                pygame.Rect(center[0] - radius - 5, center[1] - radius // 3, radius * 2 + 10, radius * 2 // 3),
                2,
            )
        pygame.draw.circle(
            illustration,
            (69, 154, 184),
            center,
            radius + 3,
            1,
        )
        illustration.blit(orb, (center[0] - radius, center[1] - radius))
        self._planet_illustration_cache[key] = illustration
        self.screen.blit(illustration, rect.topleft)

    def _draw_planet_management(
        self,
        planet: SystemObject,
        font: pygame.font.Font,
        left: int,
        y: int,
    ) -> None:
        assert self.systems is not None
        campaign = self.application.campaign
        system = campaign.get_system(self._selected_system)
        theme = self.ui.theme
        self._label(
            f"PLANET MANAGEMENT  |  {planet.name.upper()}",
            (left, y),
            font,
            theme.accent,
        )
        self._label(
            "M MANAGEMENT  |  H HISTORY  |  D DETAILS",
            (left, y + 20),
            self.ui.fonts.get(12),
            theme.muted,
        )
        population = planet.population if planet.colonized else "No settlement"
        capacity = (
            f"{planet.population_capacity_billions:.1f}B"
            if planet.population_capacity_billions
            else "Not suitable for settlement"
        )
        data = (
            f"OWNER: {planet.owner or 'Unclaimed'}",
            f"POPULATION: {population}  |  CAPACITY: {capacity}",
            f"HABITABILITY: {'Habitable' if planet.habitable else 'Hostile'}",
            (
                f"CLIMATE: {planet.climate}  |  "
                f"GRAVITY: {planet.gravity_earth:.2f} g"
                if planet.gravity_earth is not None
                else f"CLIMATE: {planet.climate}"
            ),
            f"ATMOSPHERE: {planet.atmosphere}",
            f"SURFACE: {planet.surface_conditions}",
            (
                "SYSTEM CONTROL: "
                f"{system.owner or 'Unclaimed'}"
            ),
        )
        for index, line in enumerate(data):
            self._label(
                line,
                (left, y + 44 + index * 19),
                self.ui.fonts.get(13),
                theme.text if index != 1 else theme.warning,
            )
        if planet.resources:
            deposits = "RESOURCES: " + ", ".join(
                f"{name} {amount}" for name, amount in planet.resources.items()
            )
            self._label(
                deposits,
                (left, y + 44 + len(data) * 19),
                self.ui.fonts.get(13),
                theme.warning,
            )

    def _draw_planet_history(
        self,
        planet: SystemObject,
        font: pygame.font.Font,
        left: int,
        y: int,
        compact: bool,
    ) -> None:
        assert self.systems is not None
        theme = self.ui.theme
        self._label(
            f"PLANETARY HISTORY  |  {planet.name.upper()}",
            (left, y),
            font,
            theme.accent,
        )
        self._label(
            "M MANAGEMENT  |  H HISTORY  |  D DETAILS",
            (left, y + 20),
            self.ui.fonts.get(12),
            theme.muted,
        )
        entries = list(reversed(planet.history)) or ["No recorded planetary events."]
        available_height = (
            self.systems.rect.height
            if compact
            else (
                self.action_button.rect.top - y
                if self.action_button is not None
                else self.systems.rect.height
            )
        )
        max_entries = max(1, (available_height - 48) // 35)
        for index, entry in enumerate(entries[:max_entries]):
            wrapped = self._wrap_text(
                self.ui.fonts.get(13),
                entry,
                self.systems.rect.width - 8,
            )
            for line_index, line in enumerate(wrapped[:2]):
                self._label(
                    line,
                    (left, y + 44 + index * 35 + line_index * 16),
                    self.ui.fonts.get(13),
                    theme.text,
                )

    def _draw_chronicle(self, font: pygame.font.Font) -> None:
        assert self.screen is not None
        assert self.systems is not None
        theme = self.ui.theme
        rect = self.systems.rect
        pygame.draw.rect(self.screen, theme.panel, rect)
        pygame.draw.rect(self.screen, theme.muted, rect, 1)
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(rect)
        y = rect.y + 10
        for entry in reversed(self.application.campaign.log):
            for line in self._wrap_text(font, entry, rect.width - 18):
                if y + font.get_linesize() > rect.bottom:
                    break
                self._label(line, (rect.x + 9, y), font, theme.text)
                y += font.get_linesize() + 5
            y += 6
            if y >= rect.bottom:
                break
        self.screen.set_clip(previous_clip)

    def _draw_diplomacy(self, font: pygame.font.Font) -> None:
        assert self.screen is not None
        assert self.systems is not None
        assert self.dropdown is not None
        assert self.diplomatic_action is not None
        campaign = self.application.campaign
        empire = next(
            (
                item
                for item in campaign.ai_empires
                if item.name == self.dropdown.selected
            ),
            campaign.ai_empires[0] if campaign.ai_empires else None,
        )
        self.diplomatic_action.options = self._diplomatic_action_options()
        if self.diplomatic_action.options and (
            self.diplomatic_action.selected not in self.diplomatic_action.options
        ):
            self.diplomatic_action.selected = self.diplomatic_action.options[0]
        self.dropdown.draw(self.screen, self.ui.fonts.get(13), self.ui.theme)
        self.diplomatic_action.draw(
            self.screen,
            self.ui.fonts.get(13),
            self.ui.theme,
        )
        if empire is None:
            return
        profile = campaign.species_catalog[empire.species_id]
        relation = campaign.get_relation(empire.empire_id)
        rect = self.systems.rect
        theme = self.ui.theme
        x = rect.x + 3
        y = rect.y + 7
        emblem_width = min(128, rect.width - 6)
        emblem = self._scaled_asset(
            f"civilizations/{empire.species_id}.svg",
            (emblem_width, 64),
        )
        self.screen.blit(emblem, (x, y))
        y += 72
        status = (
            "AT WAR"
            if relation.at_war
            else "CONTACT ESTABLISHED"
            if relation.first_contact
            else "NO ESTABLISHED CONTACT"
        )
        self._label(
            f"{empire.name.upper()}  /  {status}",
            (x, y),
            self.ui.fonts.get(17),
            theme.warning if relation.at_war else theme.accent,
        )
        y += 24
        self._label(
            f"Species: {profile.name}  |  {', '.join(profile.classification)}",
            (x, y),
            font,
            theme.text,
        )
        y += 21
        if not relation.first_contact:
            homeworlds = ", ".join(
                campaign.get_system(system_id).name
                for system_id in empire.system_ids
            )
            paragraphs = [
                f"Untranslated transmissions detected near {homeworlds}.",
                "Survey a rival-held star system to establish first contact and open diplomatic channels.",
                (
                    "Fleet strength: "
                    f"{sum(fleet.ship_count for fleet in campaign.ai_fleets if fleet.owner_id == empire.empire_id)} ships."
                ),
            ]
        else:
            treaty_names = {
                "non_aggression": "Non-aggression",
                "trade": "Trade",
                "research": "Research",
                "defensive_alliance": "Defensive alliance",
            }
            treaties = ", ".join(
                treaty_names[treaty] for treaty in relation.treaties
            ) or "None"
            war_status = (
                f"War duration: {campaign.elapsed_days - (relation.war_started_day or 0):.0f} days."
                if relation.at_war
                else "Peace is holding."
            )
            known_systems = ", ".join(
                campaign.get_system(system_id).name
                for system_id in empire.system_ids
            )
            paragraphs = [
                f"Opinion: {relation.opinion:+d}  |  Trust: {relation.trust}/100",
                f"Active agreements: {treaties}.",
                war_status,
                f"Known territory: {known_systems}.",
                (
                    "Trade agreements improve energy income; research agreements "
                    "increase research output."
                ),
                (
                    "Wartime fleets fight when they enter hostile systems. "
                    "Victory transfers system control."
                ),
            ]
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(rect)
        for paragraph in paragraphs:
            for line in self._wrap_text(font, paragraph, rect.width - 10):
                if y + font.get_linesize() >= rect.bottom:
                    break
                self._label(line, (x, y), font, theme.text)
                y += font.get_linesize() + 4
            y += 8
        self.screen.set_clip(previous_clip)

    def _draw_empire(self, font: pygame.font.Font, compact: bool) -> None:
        assert self.screen is not None
        assert self.overview is not None
        assert self.dropdown is not None
        campaign = self.application.campaign
        theme = self.ui.theme
        rect = self.overview.rect
        image_size = 50 if compact else 60
        x = rect.x + 14
        y = self.dropdown.rect.bottom + 10
        species = campaign.species_catalog[campaign.player_species_id]
        portrait = self._scaled_asset(species.portrait, (image_size, image_size))
        emblem = self._scaled_asset("civilizations/union.svg", (image_size, 30))
        self.screen.blit(portrait, (x, y))
        self.screen.blit(emblem, (x + image_size + 8, y + 4))
        self._label(
            f"UNION  |  {species.name}",
            (x + image_size + 8, y + 38),
            self.ui.fonts.get(14),
            theme.accent,
        )
        self._label(
            f"LIFESPAN {species.lifespan_years} YEARS  |  {', '.join(species.traits)}",
            (x + image_size + 8, y + 56),
            self.ui.fonts.get(12),
            theme.text,
        )
        y += image_size + 12
        current_technology = (
            campaign.game_content.technologies[campaign.active_technology]
            if campaign.active_technology is not None
            else None
        )
        lines = [
            (
                f"COLONIES {campaign.colonies}  |  "
                f"POPULATION {campaign.player_population_billions:.2f}B  |  "
                f"SPECIES {species.name}"
            ),
            (
                f"STOCKPILES  A {campaign.alloys:.0f}  S {campaign.science:.0f}  "
                f"E {campaign.energy:.0f}  F {campaign.food:.0f}  "
                f"V {campaign.volatiles:.0f}"
            ),
            (
                f"RESEARCH  {current_technology.name} "
                f"{campaign.research_progress:.0f}/{current_technology.cost:.0f}"
                if current_technology
                else f"RESEARCH POINTS {campaign.research_points:.1f}  |  No active project"
            ),
        ]
        for colony in campaign.player_colonies:
            system = campaign.get_system(colony.system_id)
            planet = campaign.get_object(colony.system_id, colony.planet_id)
            buildings = ", ".join(
                campaign.game_content.buildings[item].name
                for item in colony.buildings
            ) or "No buildings"
            if colony.construction:
                building = campaign.game_content.buildings[colony.construction].name
                buildings += f"  |  Building {building} ({colony.construction_days_remaining:.0f}d)"
            lines.append(
                f"{system.name} / {planet.name}: {colony.population_billions:.2f}B "
                f"| {colony.happiness:.0%} approval | {buildings}"
            )
        for fleet in campaign.all_fleets:
            if fleet.ship_count <= 0:
                continue
            destination = (
                f" -> {campaign.get_system(fleet.destination_id).name}"
                if fleet.destination_id
                else " | idle"
            )
            lines.append(
                f"FLEET {fleet.name}: {fleet.ship_count} ships at "
                f"{campaign.get_system(fleet.system_id).name}{destination}"
            )
        rival_emblems: dict[str, str] = {}
        for empire in campaign.ai_empires:
            profile = campaign.species_catalog[empire.species_id]
            rival_emblems[empire.name] = f"civilizations/{empire.species_id}.svg"
            lines.append(
                f"RIVAL {empire.name} ({profile.name})  |  "
                f"{len(empire.system_ids)} systems"
            )
        content_bottom = min(
            self.create_fleet_button.rect.y
            if self.create_fleet_button is not None
            else rect.bottom,
            rect.bottom - 8,
        )
        old_clip = self.screen.get_clip()
        self.screen.set_clip(pygame.Rect(x, y, rect.width - 26, max(1, content_bottom - y)))
        for index, line in enumerate(lines):
            line_x = x
            line_y = y + index * 36
            if line.startswith("RIVAL "):
                empire_name = line.split("(", 1)[0].removeprefix("RIVAL ").strip()
                emblem_path = rival_emblems.get(empire_name)
                if emblem_path:
                    emblem = self._scaled_asset(emblem_path, (32, 16))
                    self.screen.blit(emblem, (x, line_y + 2))
                    line_x += 38
            wrapped = self._wrap_text(font, line, rect.width - 30 - (line_x - x))
            for line_index, text in enumerate(wrapped[:2]):
                text_y = line_y + line_index * 16
                color = theme.warning if line.startswith("RIVAL") else theme.text
                self._label(text, (line_x, text_y), self.ui.fonts.get(12), color)
        self.screen.set_clip(old_clip)
        self.dropdown.options = self._dropdown_options()
        if self.dropdown.options and self.dropdown.selected not in self.dropdown.options:
            self.dropdown.selected = self.dropdown.options[0]
        self.dropdown.draw(self.screen, self.ui.fonts.get(13), theme)

    def _draw_species(self, font: pygame.font.Font, compact: bool) -> None:
        assert self.screen is not None
        assert self.overview is not None
        assert self.dropdown is not None
        assert self.systems is not None
        assert self._species_destination is not None
        campaign = self.application.campaign
        theme = self.ui.theme
        self.systems.draw(self.screen, font, theme)
        self.dropdown.options = self._dropdown_options()
        if self.dropdown.options and self.dropdown.selected not in self.dropdown.options:
            self.dropdown.selected = self.dropdown.options[0]
        self.dropdown.draw(self.screen, font, theme)
        self._refresh_species_destinations()
        self._species_destination.draw(self.screen, font, theme)
        if compact:
            return

        colony = self._selected_species_colony()
        if colony is None:
            return
        species = campaign.species_catalog[colony.species_id]
        planet = campaign.get_object(colony.system_id, colony.planet_id)
        system = campaign.get_system(colony.system_id)
        rights = campaign.species_rights.get(species.species_id, "resident")
        x = self.systems.rect.x + 2
        y = self.systems.rect.bottom + 8
        image_size = 44
        portrait = self._scaled_asset(species.portrait, (image_size, image_size))
        self.screen.blit(portrait, (x, y))
        self._label(
            f"{species.name}  |  {rights.title()}",
            (x + image_size + 8, y + 2),
            self.ui.fonts.get(15),
            theme.accent,
        )
        self._label(
            f"{system.name} / {planet.name}  |  {colony.population_billions:.2f}B",
            (x + image_size + 8, y + 23),
            self.ui.fonts.get(12),
            theme.text,
        )
        climate_status = (
            "Adapted"
            if planet.climate in species.preferred_climates
            else f"Evolution {colony.evolution_progress:.0%}"
        )
        lines = [
            f"Lifespan {species.lifespan_years} years  |  Growth {species.annual_growth_rate:.1%}",
            f"Climate {planet.climate}  |  {climate_status}",
            f"Needs: {', '.join(species.needs)}",
            f"Traits: {', '.join(species.traits)}",
        ]
        line_y = y + image_size + 7
        max_width = self.overview.rect.width - 30
        for line in lines:
            wrapped = self._wrap_text(self.ui.fonts.get(12), line, max_width)
            for text in wrapped:
                self._label(text, (x, line_y), self.ui.fonts.get(12), theme.text)
                line_y += 16

    def _research_button_label(self) -> str:
        campaign = self.application.campaign
        if campaign.active_technology is None:
            return "START RESEARCH"
        technology = campaign.game_content.technologies[campaign.active_technology]
        percent = min(100, round(campaign.research_progress / technology.cost * 100))
        return f"RESEARCH {percent}%"

    def _selected_colony(self) -> tuple[str, str]:
        campaign = self.application.campaign
        system = campaign.get_system(self._selected_system)
        selected = campaign.colony_states.get(
            campaign.colony_key(system.system_id, self._selected_object)
        )
        if selected is not None and system.owner == "Union":
            return selected.system_id, selected.planet_id
        if campaign.player_colonies:
            colony = campaign.player_colonies[0]
            return colony.system_id, colony.planet_id
        raise ValueError("Found a colony before ordering construction")

    def _start_next_research(self) -> None:
        campaign = self.application.campaign
        if campaign.active_technology is not None:
            self.ui.notify("A research project is already active")
            return
        available = campaign.available_technologies()
        if not available:
            self.ui.notify("All available technologies have been researched")
            return
        try:
            message = campaign.start_research(available[0])
        except ValueError as error:
            self.ui.notify(str(error))
            return
        self.ui.notify(message)

    def _create_fleet(self) -> None:
        try:
            fleet = self.application.campaign.create_fleet()
        except ValueError as error:
            self.ui.notify(str(error))
            return
        self.ui.notify(f"Commissioned {fleet.name}")

    def _move_fleet_to_selection(self) -> None:
        campaign = self.application.campaign
        fleet = next((item for item in campaign.fleets if not item.route), None)
        if fleet is None:
            self.ui.notify("No idle fleet is available")
            return
        try:
            message = campaign.move_fleet(fleet.fleet_id, self._selected_system)
        except (KeyError, ValueError) as error:
            self.ui.notify(str(error))
            return
        self.ui.notify(message)

    @staticmethod
    def _wrap_text(font: pygame.font.Font, text: str, max_width: int) -> list[str]:
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and font.size(candidate)[0] > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines

    def _perform_selected_action(self) -> None:
        if self.tabs is not None and self.tabs.active == "DIPLOMACY":
            self._perform_diplomatic_action()
            return
        if self.tabs is not None and self.tabs.active == "SPECIES":
            self._perform_species_action()
            return
        if self.tabs is not None and self.tabs.active == "EMPIRE":
            assert self.dropdown is not None
            campaign = self.application.campaign
            building = next(
                (
                    definition
                    for definition in campaign.game_content.buildings.values()
                    if definition.name == self.dropdown.selected
                ),
                None,
            )
            if building is None:
                self.ui.notify("Select an available building")
                return
            try:
                system_id, planet_id = self._selected_colony()
                message = campaign.build_building(
                    system_id,
                    planet_id,
                    building.building_id,
                )
            except (KeyError, ValueError) as error:
                self.ui.notify(str(error))
                return
            self.ui.notify(message)
            return
        try:
            if self.tabs is not None and self.tabs.active == "SYSTEM":
                message = self.application.campaign.perform_object_action(
                    self._selected_system,
                    self._selected_object,
                )
            else:
                message = self.application.campaign.perform_action(self._selected_system)
        except ValueError as error:
            self.ui.notify(str(error))
            return
        self.ui.notify(message)
        self._filter_content()

    def _perform_species_action(self) -> None:
        assert self.dropdown is not None
        assert self._species_destination is not None
        campaign = self.application.campaign
        colony = self._selected_species_colony()
        if colony is None:
            self.ui.notify("Found a colony before managing species")
            return
        action = self.dropdown.selected
        rights_actions = {
            "Citizen rights": "citizen",
            "Resident rights": "resident",
            "Restricted rights": "restricted",
        }
        engineering_actions = {
            "Climate adaptation": "climate-adaptation",
            "Enhanced growth": "enhanced-growth",
            "Extended lifespan": "extended-lifespan",
        }
        try:
            if action in rights_actions:
                message = campaign.set_species_rights(
                    colony.species_id,
                    rights_actions[action],
                )
            elif action in engineering_actions:
                message = campaign.engineer_species(
                    colony.system_id,
                    colony.planet_id,
                    engineering_actions[action],
                )
            elif action == "Synthetic conversion":
                message = campaign.synthesize_species(
                    colony.system_id,
                    colony.planet_id,
                )
            elif action == "Migrate population":
                target = next(
                    (
                        item
                        for item in campaign.player_colonies
                        if self._species_colony_label(item)
                        == self._species_destination.selected
                    ),
                    None,
                )
                if target is None:
                    self.ui.notify("Choose a matching destination colony")
                    return
                message = campaign.migrate_population(
                    colony.system_id,
                    colony.planet_id,
                    target.system_id,
                    target.planet_id,
                )
            else:
                self.ui.notify("Select a species action")
                return
        except (KeyError, ValueError) as error:
            self.ui.notify(str(error))
            return
        self._filter_content()
        self.ui.notify(message)

    def _perform_diplomatic_action(self) -> None:
        assert self.dropdown is not None
        assert self.diplomatic_action is not None
        campaign = self.application.campaign
        empire = next(
            (
                item
                for item in campaign.ai_empires
                if item.name == self.dropdown.selected
            ),
            None,
        )
        if empire is None:
            self.ui.notify("No civilization is available for diplomacy")
            return
        action = self.diplomatic_action.selected
        treaty_ids = {
            "Propose non-aggression pact": "non_aggression",
            "Propose trade agreement": "trade",
            "Propose research agreement": "research",
            "Propose defensive alliance": "defensive_alliance",
        }
        break_ids = {
            f"Break {label}": treaty_id
            for treaty_id, label in (
                ("non_aggression", "Non-aggression pact"),
                ("trade", "Trade agreement"),
                ("research", "Research agreement"),
                ("defensive_alliance", "Defensive alliance"),
            )
        }
        try:
            if action == "Send envoy":
                message = campaign.send_envoy(empire.empire_id)
            elif action in treaty_ids:
                message = campaign.propose_treaty(
                    empire.empire_id,
                    treaty_ids[action],
                )
            elif action in break_ids:
                message = campaign.break_treaty(
                    empire.empire_id,
                    break_ids[action],
                )
            elif action == "Declare war":
                message = campaign.declare_war(empire.empire_id)
            elif action == "Negotiate peace":
                message = campaign.negotiate_peace(empire.empire_id)
            else:
                self.ui.notify("Survey rival territory to establish first contact")
                return
        except (KeyError, ValueError) as error:
            self.ui.notify(str(error))
            return
        self.diplomatic_action.options = self._diplomatic_action_options()
        if self.diplomatic_action.options:
            self.diplomatic_action.selected = self.diplomatic_action.options[0]
        self.ui.notify(message)

    def _text_input_focused(self) -> bool:
        return self.search is not None and self.search.focused

    def _update_tooltip(self) -> None:
        self.ui.tooltip = next(
            (
                widget.tooltip
                for widget in self._widgets
                if isinstance(widget, Button)
                and widget.hovered
                and widget.tooltip
            ),
            None,
        )

    def _toggle_pause(self) -> None:
        clock = self.application.engine.clock
        if clock.paused:
            clock.resume()
            self.ui.notify("Simulation resumed")
        else:
            clock.pause()
            self.ui.notify("Simulation paused")

    def _toggle_contrast(self) -> None:
        self.ui.high_contrast = not self.ui.high_contrast
        self.ui.notify(
            "High-contrast mode enabled"
            if self.ui.high_contrast
            else "High-contrast mode disabled"
        )

    def _change_scale(self, amount: float) -> None:
        scale = min(1.75, max(0.75, round(self.ui.fonts.scale + amount, 2)))
        if scale != self.ui.fonts.scale:
            self.ui.set_scale(scale)
            self._layout_ui()
            self.ui.notify(f"Interface scale {round(scale * 100)}%")

    def _cycle_speed(self) -> None:
        self._speed_index = (self._speed_index + 1) % len(self._SPEEDS)
        speed = self._SPEEDS[self._speed_index]
        self.application.engine.clock.set_speed(speed)
        self.ui.notify(f"Simulation speed {self._speed_label()}")

    def _speed_label(self) -> str:
        speed = self._SPEEDS[self._speed_index]
        return f"{speed:g}x"

    def _show_exit_dialog(self) -> None:
        self.ui.show_dialog(
            "Exit NOVA?",
            "The application will close.",
            {
                "Exit": lambda: setattr(self, "_running", False),
                "Cancel": lambda: None,
            },
            self.screen.get_rect() if self.screen is not None else self._bounds,
        )

    def _toggle_fullscreen(self) -> None:
        if self.screen is None:
            return
        if self._fullscreen:
            self._fullscreen = False
            size = self._windowed_size
            flags = pygame.RESIZABLE
        else:
            self._windowed_size = self.screen.get_size()
            self._fullscreen = True
            info = pygame.display.Info()
            size = (info.current_w, info.current_h)
            flags = pygame.FULLSCREEN
        self.screen = pygame.display.set_mode(size, flags)
        self._update_bounds()
        self._layout_ui()
        self._layout_menu()

    def _label(
        self,
        text: str,
        position: tuple[int, int],
        font: pygame.font.Font,
        color: tuple[int, int, int],
    ) -> None:
        assert self.screen is not None
        self.screen.blit(font.render(text, True, color), position)
