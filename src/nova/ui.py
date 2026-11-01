"""Small pygame UI toolkit used by the NOVA prototype."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pygame


Color = tuple[int, int, int]


@dataclass(frozen=True)
class Theme:
    background: Color = (5, 9, 20)
    panel: Color = (10, 20, 36)
    panel_alt: Color = (18, 33, 54)
    accent: Color = (67, 213, 208)
    text: Color = (217, 244, 255)
    muted: Color = (126, 164, 181)
    warning: Color = (255, 196, 107)

    @classmethod
    def accessible(cls) -> "Theme":
        return cls(
            background=(0, 0, 0),
            panel=(8, 8, 8),
            panel_alt=(32, 32, 32),
            accent=(255, 255, 0),
            text=(255, 255, 255),
            muted=(220, 220, 220),
            warning=(255, 180, 0),
        )


class FocusableWidget(Protocol):
    focused: bool

    def handle(self, event: pygame.event.Event) -> bool: ...


class FontManager:
    """Loads named fonts and caches scaled font instances."""

    def __init__(self, scale: float = 1.0) -> None:
        self.scale = 1.0
        self._paths: dict[str, Path | None] = {"default": None}
        self._cache: dict[tuple[str, int], pygame.font.Font] = {}
        self.set_scale(scale)

    def register(self, name: str, path: Path | None) -> None:
        if not name:
            raise ValueError("Font name cannot be empty")
        self._paths[name] = path
        self._cache = {
            key: font for key, font in self._cache.items() if key[0] != name
        }

    def set_scale(self, scale: float) -> None:
        if not 0.75 <= scale <= 1.75:
            raise ValueError("UI scale must be between 0.75 and 1.75")
        if scale != self.scale:
            self.scale = scale
            self._cache.clear()

    def get(self, size: int, name: str = "default") -> pygame.font.Font:
        if size < 1:
            raise ValueError("Font size must be greater than zero")
        if name not in self._paths:
            raise KeyError(f"Unknown font: {name}")
        scaled_size = max(1, round(size * self.scale))
        key = (name, scaled_size)
        if key not in self._cache:
            path = self._paths[name]
            self._cache[key] = pygame.font.Font(
                str(path) if path is not None else None,
                scaled_size,
            )
        return self._cache[key]


class Button:
    def __init__(
        self,
        rect: pygame.Rect,
        label: str,
        action: Callable[[], None],
        tooltip: str = "",
    ) -> None:
        self.rect = rect
        self.label = label
        self.action = action
        self.tooltip = tooltip
        self.hovered = False
        self.focused = False

    def handle(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        if (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.rect.collidepoint(event.pos)
        ):
            self.action()
            return True
        if (
            event.type == pygame.KEYDOWN
            and self.focused
            and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE)
        ):
            self.action()
            return True
        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, theme: Theme) -> None:
        selected = self.hovered or self.focused
        color = theme.accent if selected else theme.panel_alt
        pygame.draw.rect(surface, color, self.rect, border_radius=4)
        text_color = theme.background if selected else theme.text
        label = font.render(self.label, True, text_color)
        surface.blit(label, label.get_rect(center=self.rect.center))


class TabBar:
    def __init__(self, rect: pygame.Rect, tabs: Sequence[str]) -> None:
        self.rect = rect
        self.tabs = list(tabs)
        self.active = self.tabs[0] if self.tabs else ""
        self.focused = False

    def handle(self, event: pygame.event.Event) -> bool:
        if not self.tabs:
            return False
        if (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.rect.collidepoint(event.pos)
        ):
            index = min(
                len(self.tabs) - 1,
                (event.pos[0] - self.rect.x) * len(self.tabs) // self.rect.width,
            )
            self.active = self.tabs[index]
            return True
        if event.type == pygame.KEYDOWN and self.focused:
            current = self.tabs.index(self.active)
            if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                step = 1 if event.key == pygame.K_RIGHT else -1
                self.active = self.tabs[(current + step) % len(self.tabs)]
                return True
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                return True
        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, theme: Theme) -> None:
        if not self.tabs:
            return
        tab_width = self.rect.width // len(self.tabs)
        for index, tab in enumerate(self.tabs):
            rect = pygame.Rect(
                self.rect.x + index * tab_width,
                self.rect.y,
                tab_width if index < len(self.tabs) - 1 else self.rect.right - (self.rect.x + index * tab_width),
                self.rect.height,
            )
            active = tab == self.active
            pygame.draw.rect(surface, theme.accent if active else theme.panel_alt, rect)
            color = theme.background if active else theme.text
            label_text = {
                "GALAXY": "MAP",
                "DIPLOMACY": "DIPLO",
                "CHRONICLE": "LOG",
            }.get(tab, tab)
            label = font.render(label_text, True, color)
            surface.blit(label, label.get_rect(center=rect.center))
        if self.focused:
            pygame.draw.rect(surface, theme.warning, self.rect, 2)


class TextInput:
    def __init__(self, rect: pygame.Rect, placeholder: str) -> None:
        self.rect = rect
        self.placeholder = placeholder
        self.text = ""
        self.focused = False
        self.max_length = 80

    def handle(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.focused = self.rect.collidepoint(event.pos)
            return self.focused
        if self.focused and event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.focused = False
            elif event.unicode.isprintable() and len(self.text) < self.max_length:
                self.text += event.unicode
            return True
        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, theme: Theme) -> None:
        border = theme.accent if self.focused else theme.muted
        pygame.draw.rect(surface, theme.panel_alt, self.rect, border_radius=3)
        pygame.draw.rect(surface, border, self.rect, 2, border_radius=3)
        value = self.text or self.placeholder
        color = theme.text if self.text else theme.muted
        surface.blit(font.render(value, True, color), self.rect.move(8, 7).topleft)


class Dropdown:
    def __init__(self, rect: pygame.Rect, options: Sequence[str]) -> None:
        self.rect = rect
        self.options = list(options)
        self.selected = self.options[0] if self.options else ""
        self.open = False
        self.focused = False

    def handle(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.open = not self.open
                return True
            if self.open:
                for index, option in enumerate(self.options):
                    option_rect = self.rect.move(0, (index + 1) * self.rect.height)
                    if option_rect.collidepoint(event.pos):
                        self.selected = option
                        self.open = False
                        return True
                self.open = False
            self.focused = False
        if event.type == pygame.KEYDOWN and self.focused:
            if event.key == pygame.K_ESCAPE:
                self.open = False
                return True
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.open = not self.open
                return True
            if self.options and event.key in (pygame.K_UP, pygame.K_DOWN):
                current = self.options.index(self.selected)
                step = 1 if event.key == pygame.K_DOWN else -1
                self.selected = self.options[(current + step) % len(self.options)]
                return True
        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, theme: Theme) -> None:
        border = theme.accent if self.focused else theme.muted
        pygame.draw.rect(surface, theme.panel_alt, self.rect, border_radius=3)
        pygame.draw.rect(surface, border, self.rect, 2, border_radius=3)
        surface.blit(font.render(self.selected, True, theme.text), self.rect.move(8, 7).topleft)
        if self.open:
            for index, option in enumerate(self.options):
                rect = self.rect.move(0, (index + 1) * self.rect.height)
                pygame.draw.rect(surface, theme.panel, rect)
                pygame.draw.rect(surface, theme.muted, rect, 1)
                surface.blit(font.render(option, True, theme.text), rect.move(8, 7).topleft)


class ScrollPanel:
    def __init__(self, rect: pygame.Rect, rows: Sequence[str]) -> None:
        self.rect = rect
        self.rows = list(rows)
        self.offset = 0

    def handle(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEWHEEL:
            mouse_position = getattr(event, "pos", None)
            if mouse_position is None:
                mouse_position = pygame.mouse.get_pos()
            if self.rect.collidepoint(mouse_position):
                maximum = max(0, len(self.rows) * 24 - self.rect.height)
                self.offset = max(0, min(self.offset - event.y * 24, maximum))
                return True
        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, theme: Theme) -> None:
        old_clip = surface.get_clip()
        surface.set_clip(self.rect)
        for index, row in enumerate(self.rows):
            y = self.rect.y + index * 24 - self.offset
            surface.blit(font.render(row, True, theme.text), (self.rect.x + 8, y))
        surface.set_clip(old_clip)


class TableWidget:
    """A compact text table with sortable columns and selectable rows."""

    def __init__(
        self,
        rect: pygame.Rect,
        columns: Sequence[str],
        rows: Sequence[Sequence[str]],
        on_select: Callable[[tuple[str, ...]], None] | None = None,
    ) -> None:
        if not columns:
            raise ValueError("A table needs at least one column")
        if any(len(row) != len(columns) for row in rows):
            raise ValueError("Every table row must match the column count")
        self.rect = rect
        self.columns = list(columns)
        self.rows = [tuple(row) for row in rows]
        self.on_select = on_select
        self.sort_column: int | None = None
        self.sort_descending = False
        self.offset = 0
        self.row_height = 30
        self.header_height = 32
        self.focused = False

    def set_rows(self, rows: Sequence[Sequence[str]]) -> None:
        if any(len(row) != len(self.columns) for row in rows):
            raise ValueError("Every table row must match the column count")
        self.rows = [tuple(row) for row in rows]
        visible = max(1, (self.rect.height - self.header_height) // self.row_height)
        self.offset = min(self.offset, max(0, len(self.rows) - visible))
        if self.sort_column is not None:
            self.rows.sort(
                key=lambda row: row[self.sort_column].casefold(),
                reverse=self.sort_descending,
            )

    def _sort(self, column: int) -> None:
        if self.sort_column == column:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_column = column
            self.sort_descending = False
        self.rows.sort(
            key=lambda row: row[column].casefold(),
            reverse=self.sort_descending,
        )

    def handle(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEWHEEL:
            mouse_position = getattr(event, "pos", None)
            if mouse_position is None:
                mouse_position = pygame.mouse.get_pos()
            if self.rect.collidepoint(mouse_position):
                visible = max(1, (self.rect.height - self.header_height) // self.row_height)
                self.offset = max(0, min(self.offset - event.y, len(self.rows) - visible))
                return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.rect.collidepoint(event.pos):
                self.focused = False
                return False
            self.focused = True
            if event.pos[1] < self.rect.y + self.header_height:
                column = min(
                    len(self.columns) - 1,
                    (event.pos[0] - self.rect.x) * len(self.columns) // self.rect.width,
                )
                self._sort(column)
            else:
                row_index = (
                    (event.pos[1] - self.rect.y - self.header_height) // self.row_height
                    + self.offset
                )
                if 0 <= row_index < len(self.rows) and self.on_select is not None:
                    self.on_select(self.rows[row_index])
            return True
        if event.type == pygame.KEYDOWN and self.focused and self.rows:
            if event.key in (pygame.K_UP, pygame.K_DOWN):
                visible = max(1, (self.rect.height - self.header_height) // self.row_height)
                step = -1 if event.key == pygame.K_UP else 1
                self.offset = max(
                    0,
                    min(self.offset + step, max(0, len(self.rows) - visible)),
                )
                return True
        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, theme: Theme) -> None:
        pygame.draw.rect(surface, theme.panel, self.rect)
        pygame.draw.rect(surface, theme.accent if self.focused else theme.muted, self.rect, 1)
        column_width = self.rect.width // len(self.columns)
        for index, column in enumerate(self.columns):
            x = self.rect.x + index * column_width
            cell = pygame.Rect(x, self.rect.y, column_width, self.header_height)
            pygame.draw.rect(surface, theme.panel_alt, cell)
            label = column
            if index == self.sort_column:
                label += " v" if self.sort_descending else " ^"
            surface.blit(font.render(label, True, theme.accent), (x + 7, cell.y + 7))
        old_clip = surface.get_clip()
        surface.set_clip(self.rect)
        visible = max(0, (self.rect.height - self.header_height) // self.row_height)
        for visible_index, row in enumerate(self.rows[self.offset : self.offset + visible]):
            y = self.rect.y + self.header_height + visible_index * self.row_height
            if visible_index % 2:
                pygame.draw.rect(
                    surface,
                    theme.panel_alt,
                    (self.rect.x, y, self.rect.width, self.row_height),
                )
            for index, value in enumerate(row[: len(self.columns)]):
                x = self.rect.x + index * column_width
                surface.blit(font.render(value, True, theme.text), (x + 7, y + 7))
        surface.set_clip(old_clip)


class UIWindow:
    """A floating panel that can be dragged and resized with a mouse."""

    def __init__(
        self,
        rect: pygame.Rect,
        title: str,
        min_size: tuple[int, int] = (260, 240),
    ) -> None:
        self.rect = rect
        self.title = title
        self.min_size = min_size
        self.title_height = 34
        self.resizable = True
        self._dragging = False
        self._resizing = False
        self._last_mouse = (0, 0)

    def handle(self, event: pygame.event.Event, bounds: pygame.Rect) -> bool:
        resize_handle = pygame.Rect(
            self.rect.right - 18,
            self.rect.bottom - 18,
            18,
            18,
        )
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.resizable and resize_handle.collidepoint(event.pos):
                self._resizing = True
                self._last_mouse = event.pos
                return True
            title_bar = pygame.Rect(
                self.rect.x,
                self.rect.y,
                self.rect.width,
                self.title_height,
            )
            if title_bar.collidepoint(event.pos):
                self._dragging = True
                self._last_mouse = event.pos
                return True
        elif event.type == pygame.MOUSEMOTION and (self._dragging or self._resizing):
            dx, dy = event.pos[0] - self._last_mouse[0], event.pos[1] - self._last_mouse[1]
            if self._dragging:
                self.rect.x = min(
                    max(bounds.left, self.rect.x + dx),
                    bounds.right - self.rect.width,
                )
                self.rect.y = min(
                    max(bounds.top, self.rect.y + dy),
                    bounds.bottom - self.rect.height,
                )
            else:
                self.rect.width = min(
                    max(self.min_size[0], self.rect.width + dx),
                    bounds.right - self.rect.x,
                )
                self.rect.height = min(
                    max(self.min_size[1], self.rect.height + dy),
                    bounds.bottom - self.rect.y,
                )
            self._last_mouse = event.pos
            return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was_active = self._dragging or self._resizing
            self._dragging = False
            self._resizing = False
            return was_active
        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, theme: Theme) -> None:
        pygame.draw.rect(surface, theme.panel, self.rect, border_radius=5)
        title_rect = pygame.Rect(
            self.rect.x,
            self.rect.y,
            self.rect.width,
            self.title_height,
        )
        pygame.draw.rect(surface, theme.panel_alt, title_rect, border_radius=5)
        pygame.draw.rect(surface, theme.muted, self.rect, 1, border_radius=5)
        surface.blit(font.render(self.title, True, theme.accent), (self.rect.x + 12, self.rect.y + 8))
        if self.resizable:
            pygame.draw.line(
                surface,
                theme.muted,
                (self.rect.right - 12, self.rect.bottom - 4),
                (self.rect.right - 4, self.rect.bottom - 12),
                2,
            )


class WindowManager:
    """Keeps floating windows within the visible application area."""

    def __init__(self, bounds: pygame.Rect) -> None:
        self.bounds = bounds
        self.windows: list[UIWindow] = []

    def add(self, window: UIWindow) -> None:
        self.windows.append(window)
        self._constrain(window)

    def set_bounds(self, bounds: pygame.Rect) -> None:
        self.bounds = bounds
        for window in self.windows:
            self._constrain(window)

    def _constrain(self, window: UIWindow) -> None:
        window.rect.width = min(window.rect.width, self.bounds.width)
        window.rect.height = min(window.rect.height, self.bounds.height)
        window.rect.clamp_ip(self.bounds)

    def handle(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index in range(len(self.windows) - 1, -1, -1):
                window = self.windows[index]
                if window.rect.collidepoint(event.pos):
                    self.windows.append(self.windows.pop(index))
                    return window.handle(event, self.bounds)
        for window in reversed(self.windows):
            if window.handle(event, self.bounds):
                return True
        return False

    def draw(
        self,
        surface: pygame.Surface,
        font: pygame.font.Font,
        theme: Theme,
    ) -> None:
        for window in self.windows:
            window.draw(surface, font, theme)


class ModalDialog:
    """Blocking dialog with selectable actions."""

    def __init__(
        self,
        title: str,
        message: str,
        actions: dict[str, Callable[[], None]],
        bounds: pygame.Rect,
    ) -> None:
        self.title = title
        self.message = message
        self.actions = actions
        width = min(480, max(280, bounds.width - 32))
        height = 190
        self.rect = pygame.Rect(0, 0, width, height)
        self.rect.center = bounds.center

    def handle(self, event: pygame.event.Event) -> bool:
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return False
        button_width = min(130, (self.rect.width - 36) // max(1, len(self.actions)))
        gap = 10
        total_width = len(self.actions) * button_width + max(0, len(self.actions) - 1) * gap
        x = self.rect.centerx - total_width // 2
        y = self.rect.bottom - 54
        for label, action in self.actions.items():
            button = pygame.Rect(x, y, button_width, 36)
            if button.collidepoint(event.pos):
                action()
                return True
            x += button_width + gap
        return self.rect.collidepoint(event.pos)

    def draw(
        self,
        surface: pygame.Surface,
        font: pygame.font.Font,
        theme: Theme,
    ) -> None:
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))
        pygame.draw.rect(surface, theme.panel, self.rect, border_radius=6)
        pygame.draw.rect(surface, theme.accent, self.rect, 2, border_radius=6)
        surface.blit(font.render(self.title, True, theme.accent), (self.rect.x + 20, self.rect.y + 18))
        words = self.message.split()
        lines: list[str] = []
        line = ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if line and font.size(candidate)[0] > self.rect.width - 40:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
        for index, text in enumerate(lines[:3]):
            surface.blit(font.render(text, True, theme.text), (self.rect.x + 20, self.rect.y + 58 + index * 24))
        button_width = min(130, (self.rect.width - 36) // max(1, len(self.actions)))
        gap = 10
        total_width = len(self.actions) * button_width + max(0, len(self.actions) - 1) * gap
        x = self.rect.centerx - total_width // 2
        y = self.rect.bottom - 54
        for label in self.actions:
            button = pygame.Rect(x, y, button_width, 36)
            pygame.draw.rect(surface, theme.panel_alt, button, border_radius=4)
            text = font.render(label, True, theme.text)
            surface.blit(text, text.get_rect(center=button.center))
            x += button_width + gap


class UIManager:
    """Coordinates focus, accessibility, dialogs, and notifications."""

    def __init__(self, theme: Theme | None = None) -> None:
        self._theme = theme or Theme()
        self.high_contrast = False
        self.fonts = FontManager()
        self.notifications: list[Notification] = []
        self.tooltip: str | None = None
        self.modal: ModalDialog | None = None
        self.focusables: list[object] = []
        self._focus_index = -1

    @property
    def theme(self) -> Theme:
        return Theme.accessible() if self.high_contrast else self._theme

    def set_scale(self, scale: float) -> None:
        self.fonts.set_scale(scale)

    def set_focusables(self, widgets: Sequence[FocusableWidget]) -> None:
        self.focusables = list(widgets)
        self._focus_index = -1

    def focus_next(self) -> None:
        if not self.focusables:
            return
        for widget in self.focusables:
            widget.focused = False
        self._focus_index = (self._focus_index + 1) % len(self.focusables)
        self.focusables[self._focus_index].focused = True

    def handle_event(
        self,
        event: pygame.event.Event,
        widgets: Sequence[FocusableWidget],
    ) -> bool:
        if self.modal is not None:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.modal = None
                return True
            if self.modal.handle(event):
                self.modal = None
            return True

        if event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
            self.focus_next()
            return True
        if event.type == pygame.KEYDOWN:
            for widget in self.focusables:
                if widget.focused and widget.handle(event):
                    return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for widget in self.focusables:
                widget.focused = False
            self._focus_index = -1
        for widget in reversed(widgets):
            if widget.handle(event):
                if event.type == pygame.MOUSEBUTTONDOWN and widget in self.focusables:
                    self._focus_index = self.focusables.index(widget)
                    widget.focused = True
                return True
        return False

    def show_dialog(
        self,
        title: str,
        message: str,
        actions: dict[str, Callable[[], None]],
        bounds: pygame.Rect,
    ) -> None:
        if not actions:
            raise ValueError("A modal dialog needs at least one action")
        self.modal = ModalDialog(title, message, actions, bounds)

    def notify(self, message: str) -> None:
        self.notifications.append(Notification(message))

    def update(self, delta: float) -> None:
        for notification in self.notifications:
            notification.update(delta)
        self.notifications = [item for item in self.notifications if item.remaining > 0]

    def draw_overlays(
        self,
        surface: pygame.Surface,
        small_font: pygame.font.Font,
        font: pygame.font.Font,
    ) -> None:
        theme = self.theme
        for index, notification in enumerate(self.notifications):
            rect = pygame.Rect(20, 70 + index * 42, 300, 34)
            pygame.draw.rect(surface, theme.panel, rect, border_radius=4)
            surface.blit(small_font.render(notification.message, True, theme.text), (rect.x + 10, rect.y + 8))
        if self.tooltip:
            text = small_font.render(self.tooltip, True, theme.text)
            mouse_x, mouse_y = pygame.mouse.get_pos()
            box = text.get_rect(topleft=(mouse_x + 12, mouse_y + 12)).inflate(12, 8)
            box.clamp_ip(surface.get_rect())
            pygame.draw.rect(surface, theme.panel, box)
            surface.blit(text, (box.x + 6, box.y + 4))
        if self.modal is not None:
            self.modal.draw(surface, font, theme)


class Notification:
    def __init__(self, message: str, lifetime: float = 4.0) -> None:
        self.message = message
        self.remaining = lifetime

    def update(self, delta: float) -> None:
        self.remaining -= delta
