"""Pygame window and the first interactive NOVA map presentation."""

from collections import deque
import logging
import math

import pygame

from .application import Application
from .assets import AssetError, AssetManager
from .campaign import StarSystem, SystemObject
from .config import Config
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
        self._fullscreen = config.fullscreen
        self._windowed_size = (config.window_width, config.window_height)
        self._speed_index = 1
        self._selected_system = "sol"
        self._selected_object = "earth"
        self._planet_view = "DETAILS"
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
            self._running = True
            while self._running:
                self._handle_events()
                delta = self._clock.tick(60) / 1000.0
                self.application.update(delta)
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
                        setattr(self, layer, not getattr(self, layer))
                        if event.key == pygame.K_f:
                            if self._fog_of_war:
                                sensor_system_ids = self._sensor_system_ids()
                                selected = self.application.campaign.get_system(
                                    self._selected_system
                                )
                                if not self._is_system_visible(
                                    selected,
                                    sensor_system_ids,
                                ):
                                    self._selected_system = next(
                                        system.system_id
                                        for system in self.application.campaign.systems
                                        if self._is_system_visible(
                                            system,
                                            sensor_system_ids,
                                        )
                                    )
                                    self._set_selected_map_system(
                                        self._selected_system
                                    )
                            self._filter_content()
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
                and self._select_map_item(event.pos)
            ):
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
        if self.tabs is not None and self.tabs.active == "SYSTEM":
            self._draw_system_map()
        else:
            self._draw_galaxy_map()
            self._draw_map_card()

        pygame.draw.rect(self.screen, theme.panel, (0, 0, width, 54))
        font = self.ui.fonts.get(26)
        small_font = self.ui.fonts.get(18)
        self._label("NOVA", (22, 14), font, theme.accent)
        campaign = self.application.campaign
        resource_line = (
            (
                f"{campaign.date_label}  A:{campaign.alloys:.0f}  "
                f"S:{campaign.science:.0f}  I:{campaign.influence:.0f}  "
                f"V:{campaign.volatiles:.0f}"
            )
            if width < 900
            else (
                f"FRONTIER  {campaign.date_label}    "
                f"ALLOYS {campaign.alloys:.0f}    "
                f"SCIENCE {campaign.science:.0f}    "
                f"INFLUENCE {campaign.influence:.0f}    "
                f"VOLATILES {campaign.volatiles:.0f}"
            )
        )
        resource_font = small_font if width >= 900 else self.ui.fonts.get(14)
        self._label(resource_line, (120, 19), resource_font, theme.text)
        paused = self.application.engine.clock.paused
        status = "PAUSED" if paused else "LIVE"
        self._label(status, (width - 80, 19), small_font, theme.accent)

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
        self.tabs.draw(self.screen, small_font, theme)
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
        else:
            self._draw_chronicle(small_font)
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
        else:
            help_text = (
                "Click star  |  wheel zoom  |  right-drag pan  |  Home reset  |  "
                "P borders  T trade  R resources  S sensors  F fog  E explore  "
                "Ctrl+B bookmark  B next  Space pause"
            )
        help_font = self.ui.fonts.get(11) if self.tabs.active == "GALAXY" else (
            self.ui.fonts.get(13) if width < 900 else small_font
        )
        self._label(help_text, (18, height - 22), help_font, theme.muted)
        self.ui.draw_overlays(self.screen, small_font, small_font)

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
        self.tabs = TabBar(pygame.Rect(0, 0, 1, 1), ["GALAXY", "SYSTEM", "CHRONICLE"])
        self.search = TextInput(pygame.Rect(0, 0, 1, 1), "Search...")
        self.dropdown = Dropdown(
            pygame.Rect(0, 0, 1, 1),
            ["All", "Uncharted", "Surveyed", "Colonized"],
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
            self.action_button.rect = pygame.Rect(
                content_x,
                action_y,
                content_width,
                button_height,
            )
            log_y = self.tabs.rect.bottom + round(8 * scale)
            self.systems.rect = pygame.Rect(
                content_x,
                log_y,
                content_width,
                max(1, action_y - log_y - round(8 * scale)),
            )
            self.search.rect = pygame.Rect(0, 0, 1, 1)
            self.dropdown.rect = pygame.Rect(0, 0, 1, 1)
            return
        self.tabs.rect = pygame.Rect(
            content_x,
            rect.y + round(44 * scale),
            content_width,
            round(34 * scale),
        )
        self.search.rect = pygame.Rect(
            content_x,
            rect.y + round(86 * scale),
            content_width,
            round(34 * scale),
        )
        self.dropdown.rect = pygame.Rect(
            content_x,
            rect.y + round(128 * scale),
            content_width,
            round(34 * scale),
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
        self.action_button.rect = pygame.Rect(
            content_x,
            action_y,
            content_width,
            button_height,
        )
        table_y = self.dropdown.rect.bottom + round(8 * scale)
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
            self._configure_visible_widgets()
            self._layout_ui()
            self.dropdown.options = self._dropdown_options()
            self.dropdown.selected = self.dropdown.options[0]
        if self.tabs.active == "CHRONICLE":
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
        polygons, _ = self._territory_geometry(bounds)
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

    def _dropdown_options(self) -> list[str]:
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
                self.search,
                self.dropdown,
                self.systems,
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
        if self.tabs is not None:
            self.tabs.active = "SYSTEM"
            self._filter_content()
        return True

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
                pygame.draw.circle(self.screen, theme.text, position, radius + 6, 1)
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
                            self.ui.fonts.get(11),
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
            for fleet in campaign.fleets:
                if self._fog_of_war and fleet.system_id not in sensor_system_ids:
                    continue
                fleet_position = self._map_position(fleet.system_id)
                pygame.draw.polygon(
                    self.screen,
                    (110, 231, 245),
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
                        self.ui.fonts.get(11),
                        (110, 231, 245),
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
        self._label(
            (
                f"{campaign.galaxy.name.upper()}  /  "
                f"{campaign.galaxy.region_name.upper()}  /  "
                f"{campaign.galaxy.morphology.upper()}"
            ),
            (bounds.x + 12, bounds.y + 8),
            self.ui.fonts.get(14),
            theme.muted,
        )
        layer_status = " ".join(
            label
            for enabled, label in (
                (self._show_borders, "TERRITORY"),
                (self._show_fleets, "FLEET"),
                (self._show_trade_routes, "TRADE"),
                (self._show_resources, "RES"),
                (self._show_sensors, "SENSOR"),
                (self._fog_of_war, "FOG"),
                (self._show_exploration, "EXPLORE"),
            )
            if enabled
        )
        if self._selected_system in campaign.map_bookmarks:
            layer_status = f"{layer_status}  BOOKMARK" if layer_status else "BOOKMARK"
        ownership_status = (
            ", ".join(territory_owners) or "NONE"
            if self._show_borders
            else "HIDDEN"
        )
        self._label(
            f"OWNERSHIP: {ownership_status}  |  {layer_status}",
            (bounds.x + 12, bounds.y + 64),
            self.ui.fonts.get(11),
            theme.muted,
        )
        legend_y = bounds.y + 49
        legend_font = self.ui.fonts.get(12)
        legend = (
            (theme.muted, "OPEN"),
            (theme.warning, "SURVEYED"),
            (theme.accent, "COLONY"),
        )
        legend_x = bounds.x + 12
        legend_step = max(64, min(98, (bounds.width - 24) // len(legend)))
        for color, label_text in legend:
            pygame.draw.circle(self.screen, color, (legend_x + 5, legend_y + 6), 4, 1)
            self._label(label_text, (legend_x + 13, legend_y), legend_font, theme.muted)
            legend_x += legend_step
        self._label(
            (
                f"{len(visible_systems) if self._fog_of_war else len(campaign.systems)} "
                f"STARS  /  SEED {campaign.galaxy.seed}  /  "
                f"{campaign.galaxy.diameter_light_years:,} LY  /  {self._galaxy_zoom:.1f}x"
            ),
            (bounds.x + 12, bounds.y + 28),
            self.ui.fonts.get(13),
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
        pygame.draw.rect(self.screen, theme.panel, card, border_radius=5)
        pygame.draw.rect(self.screen, theme.muted, card, 1, border_radius=5)
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
            self.ui.fonts.get(14),
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

    def _label(
        self,
        text: str,
        position: tuple[int, int],
        font: pygame.font.Font,
        color: tuple[int, int, int],
    ) -> None:
        assert self.screen is not None
        self.screen.blit(font.render(text, True, color), position)
