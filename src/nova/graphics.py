"""Pygame window and the first interactive NOVA map presentation."""

import logging
import math

import pygame

from .application import Application
from .assets import AssetError, AssetManager
from .campaign import SystemObject
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
        self._active_tab = "GALAXY"
        self._galaxy_zoom = 1.02
        self._system_zoom = 0.92
        self._map_pan = pygame.Vector2()
        self._map_dragging = False
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
                continue
            if self.ui.modal is not None:
                self.ui.handle_event(event, self._widgets)
                continue
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                if self._map_rect().collidepoint(event.pos):
                    self._map_dragging = True
                    continue
            if event.type == pygame.MOUSEBUTTONUP and event.button == 3:
                self._map_dragging = False
                continue
            if event.type == pygame.MOUSEMOTION and self._map_dragging:
                if event.buttons[2]:
                    self._map_pan += pygame.Vector2(event.rel)
                    continue
                self._map_dragging = False
            if event.type == pygame.MOUSEWHEEL:
                mouse_position = getattr(event, "pos", pygame.mouse.get_pos())
                if self._map_rect().collidepoint(mouse_position):
                    if self.tabs is not None and self.tabs.active == "GALAXY":
                        self._galaxy_zoom = min(
                            1.5,
                            max(0.35, self._galaxy_zoom + event.y * 0.08),
                        )
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
                f"S:{campaign.science:.0f}  I:{campaign.influence:.0f}"
            )
            if width < 900
            else (
                f"FRONTIER  {campaign.date_label}    "
                f"ALLOYS {campaign.alloys:.0f}    "
                f"SCIENCE {campaign.science:.0f}    "
                f"INFLUENCE {campaign.influence:.0f}"
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

        map_target = "body" if self.tabs.active == "SYSTEM" else "star"
        help_text = (
            f"Click {map_target}  |  wheel zoom  |  SPACE pause"
            if self._map_rect().width < 500
            else (
                f"Click a {map_target} to inspect  |  wheel zoom  |  "
                "right-drag pan  |  TAB / ENTER to navigate  |  SPACE pause"
            )
        )
        help_font = self.ui.fonts.get(13) if width < 900 else small_font
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
            (112 if self.tabs is not None and self.tabs.active == "SYSTEM" else 52)
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
            self.ui.notify(f"Selected {system.name}")
            return
        system = self.application.campaign.get_system(self._selected_system)
        selected = next(obj for obj in system.objects if obj.name == row[0])
        self._selected_object = selected.object_id
        self.ui.notify(f"Selected {selected.name}")

    def _system_rows(self) -> list[tuple[str, str, str]]:
        return [
            (system.name, system.status, system.world_type)
            for system in self.application.campaign.systems
        ]

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
        bounds = self._map_rect()
        system = self.application.campaign.get_system(system_id)
        return (
            round(
                bounds.centerx
                + (system.x - 0.5) * bounds.width * self._galaxy_zoom
                + self._map_pan.x
            ),
            round(
                bounds.centery
                + (system.y - 0.5) * bounds.height * self._galaxy_zoom
                + self._map_pan.y
            ),
        )

    def _select_map_item(self, position: tuple[int, int]) -> bool:
        if self.tabs is not None and self.tabs.active == "SYSTEM":
            return self._select_system_object(position)
        nearest = min(
            self.application.campaign.systems,
            key=lambda system: pygame.Vector2(
                self._map_position(system.system_id)
            ).distance_squared_to(position),
        )
        if (
            pygame.Vector2(self._map_position(nearest.system_id)).distance_squared_to(position)
            > 30**2
        ):
            return False
        self._selected_system = nearest.system_id
        selected = next(
            (obj for obj in nearest.objects if obj.habitable or obj.kind == "Planet"),
            nearest.objects[0],
        )
        self._selected_object = selected.object_id
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
        for first_id, second_id in campaign.routes:
            pygame.draw.line(
                self.screen,
                theme.accent if self.ui.high_contrast else (72, 131, 157),
                self._map_position(first_id),
                self._map_position(second_id),
                2,
            )
        for system in campaign.systems:
            position = self._map_position(system.system_id)
            if system.colonized:
                color = theme.accent
            elif system.surveyed:
                color = theme.warning
            else:
                color = theme.muted
            radius = 9 if system.system_id == self._selected_system else 5
            pygame.draw.circle(self.screen, theme.panel_alt, position, radius + 6)
            pygame.draw.circle(self.screen, color, position, radius)
            if system.system_id == self._selected_system:
                pygame.draw.circle(self.screen, theme.text, position, radius + 4, 1)
            label = self.ui.fonts.get(13).render(system.name, True, theme.text)
            label_rect = label.get_rect(midleft=(position[0] + 11, position[1]))
            if label_rect.right > bounds.right:
                label_rect.midright = (position[0] - 11, position[1])
            self.screen.blit(label, label_rect)

        pygame.draw.rect(self.screen, theme.muted, bounds, 1)
        self._label(
            f"STELLAR SECTOR  /  {len(campaign.systems)} SYSTEMS  /  {self._galaxy_zoom:.1f}x",
            (bounds.x + 12, bounds.y + 8),
            self.ui.fonts.get(15),
            theme.muted,
        )

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
        pygame.draw.circle(self.screen, (48, 113, 144), image_center, 29)
        pygame.draw.circle(self.screen, (133, 203, 202), (image_center[0] - 8, image_center[1] - 8), 11)
        pygame.draw.circle(self.screen, theme.panel, (image_center[0] + 22, image_center[1] + 14), 28, 8)
        text_x = card.x + 100
        max_width = card.right - text_x - 8
        font = self.ui.fonts.get(16)
        self._label(system.name.upper(), (text_x, card.y + 8), font, theme.accent)
        self._label(
            f"OBJECTIVE: {self.application.campaign.objective}",
            (text_x, card.y + 29),
            self.ui.fonts.get(14),
            theme.warning,
        )
        for index, line in enumerate(
            self._wrap_text(font, system.description, max_width)[:2]
        ):
            self._label(line, (text_x, card.y + 52 + index * 18), font, theme.text)

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
                * system_object.orbit
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

        pygame.draw.circle(self.screen, (109, 81, 52), center, 26)
        pygame.draw.circle(self.screen, (255, 207, 123), center, 17)
        pygame.draw.circle(self.screen, (255, 244, 205), (center[0] - 5, center[1] - 5), 6)
        for system_object in system.objects:
            position = self._system_object_position(system_object.object_id)
            if system_object.kind == "Gateway":
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
            f"{system.star_type}  |  {system.world_type}  |  {system.status}",
            (left, y + 22),
            self.ui.fonts.get(15),
            theme.text,
        )
        if compact:
            objective_font = self.ui.fonts.get(13)
            for index, line in enumerate(
                self._wrap_text(
                    objective_font,
                    f"OBJECTIVE: {self.application.campaign.objective}",
                    self.systems.rect.width - 6,
                )[:2]
            ):
                self._label(
                    line,
                    (left, y + 44 + index * 15),
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
                    (left, y + 76 + index * 17),
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
