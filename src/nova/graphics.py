"""Pygame window and the first interactive NOVA map presentation."""

import logging

import pygame

from .application import Application
from .assets import AssetError, AssetManager
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
    """Owns pygame resources and translates input into application updates."""

    _SYSTEMS = (
        ("Sol", "Colonised", "8.1B"),
        ("Asterion", "Unknown", "-"),
        ("Vesper", "Colonised", "2.4B"),
        ("Helios", "Unknown", "-"),
        ("New Carthage", "Colonised", "910M"),
    )
    _PANEL_DATA = {
        "SYSTEM": (
            ("SYSTEM", "STATUS", "POP."),
            _SYSTEMS,
            ("All systems", "Colonised", "Unknown"),
        ),
        "FLEETS": (
            ("FLEET", "ORDERS", "SHIPS"),
            (
                ("Sol Defense", "Patrolling", "12"),
                ("Frontier Group", "In transit", "4"),
                ("Survey Wing", "Surveying", "3"),
            ),
            ("All fleets", "Patrolling", "In transit", "Surveying"),
        ),
        "DIPLOMACY": (
            ("EMPIRE", "RELATION", "STATUS"),
            (
                ("Aurelian Union", "Allied", "Open borders"),
                ("Vesper Compact", "Neutral", "Trade"),
                ("Outer Reaches", "Rival", "Tense"),
            ),
            ("All empires", "Allied", "Neutral", "Rival"),
        ),
    }
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
        self._selected_system = "Sol"
        self._active_tab = "SYSTEM"
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
            background = self.assets.scaled("galaxy-background.svg", (width, height))
            self.screen.blit(background, (0, 0))
            system_size = min(height, 620)
            system = self.assets.scaled("star-system.svg", (system_size, system_size))
            self.screen.blit(
                system,
                (max(0, width // 2 - system.width // 2), 60),
            )
        except AssetError as error:
            logger.debug("Using generated map fallback: %s", error)

        pygame.draw.rect(self.screen, theme.panel, (0, 0, width, 54))
        font = self.ui.fonts.get(26)
        small_font = self.ui.fonts.get(18)
        self._label("NOVA", (22, 14), font, theme.accent)
        self._label("GALAXY MAP", (120, 18), small_font, theme.text)
        paused = self.application.engine.clock.paused
        status = "PAUSED" if paused else "SIMULATION RUNNING"
        self._label(status, (width - 270, 18), small_font, theme.accent)

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
        self.tabs.draw(self.screen, small_font, theme)
        self.search.draw(self.screen, small_font, theme)
        self.systems.draw(self.screen, small_font, theme)
        self.dropdown.draw(self.screen, small_font, theme)
        selected = f"SELECTED: {self._selected_system}"
        self._label(selected, self._selected_label_position(), small_font, theme.text)
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

        self._label(
            "TAB Focus   ENTER Activate   +/- UI scale   F1 Contrast   F11 Fullscreen",
            (18, height - 28),
            small_font,
            theme.muted,
        )
        self.ui.draw_overlays(self.screen, small_font, small_font)

    def _build_ui(self) -> None:
        assert self.screen is not None
        width, height = self.screen.get_size()
        scale = self.ui.fonts.scale
        panel_width = min(round(340 * scale), width - 32)
        panel_height = min(round(560 * scale), height - 90)
        panel = UIWindow(
            pygame.Rect(width - panel_width - 16, 70, panel_width, panel_height),
            "GALACTIC OVERVIEW",
            min_size=(min(300, width - 32), min(330, height - 70)),
        )
        self.overview = panel
        self.windows.add(panel)
        self.tabs = TabBar(pygame.Rect(0, 0, 1, 1), ["SYSTEM", "FLEETS", "DIPLOMACY"])
        self.search = TextInput(pygame.Rect(0, 0, 1, 1), "Search galaxy...")
        self.dropdown = Dropdown(
            pygame.Rect(0, 0, 1, 1),
            ["All systems", "Colonised", "Unknown"],
        )
        self.systems = TableWidget(
            pygame.Rect(0, 0, 1, 1),
            self._PANEL_DATA["SYSTEM"][0],
            self._SYSTEMS,
            on_select=self._select_system,
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
        self._widgets = [
            self.tabs,
            self.search,
            self.systems,
            self.dropdown,
            self.speed_button,
            self.pause_button,
            self.scale_down,
            self.scale_up,
            self.contrast_button,
        ]
        self._focusables = list(self._widgets)
        self.ui.set_focusables(self._focusables)
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
        selected_y = control_y - round(26 * scale)
        table_y = self.dropdown.rect.bottom + round(8 * scale)
        table_height = max(round(48 * scale), selected_y - table_y - round(26 * scale))
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
        if self.search is None or self.dropdown is None or self.systems is None:
            return
        if self.tabs is None:
            return
        columns, rows, options = self._PANEL_DATA[self.tabs.active]
        if self._active_tab != self.tabs.active:
            self._active_tab = self.tabs.active
            self.systems.columns = list(columns)
            self.dropdown.options = list(options)
            self.dropdown.selected = options[0]
            self._selected_system = self.tabs.active.title()
        query = self.search.text.casefold().strip()
        category = self.dropdown.selected
        filtered = [
            row
            for row in rows
            if (not query or query in " ".join(row).casefold())
            and (category == options[0] or row[1] == category)
        ]
        self.systems.set_rows(filtered)

    def _select_system(self, row: tuple[str, ...]) -> None:
        self._selected_system = row[0]
        self.ui.notify(f"Selected {row[0]}")

    def _selected_label_position(self) -> tuple[int, int]:
        assert self.overview is not None
        return (
            self.overview.rect.x + round(12 * self.ui.fonts.scale),
            self.speed_button.rect.y - round(24 * self.ui.fonts.scale),
        )

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
