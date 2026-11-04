import pygame
import pytest

from nova.ui import Button, TableWidget, TabBar, Theme, UIManager, UIWindow, WindowManager


def test_table_sorts_columns_and_selects_rows() -> None:
    selected: list[tuple[str, ...]] = []
    table = TableWidget(
        pygame.Rect(0, 0, 300, 120),
        ["Name", "Status"],
        [("Vesper", "Colony"), ("Asterion", "Unknown")],
        on_select=selected.append,
    )

    table.handle(
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            {"button": 1, "pos": (10, 10)},
        )
    )
    assert table.rows[0][0] == "Asterion"

    table.handle(
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            {"button": 1, "pos": (10, 40)},
        )
    )
    assert selected == [("Asterion", "Unknown")]


def test_table_rejects_rows_with_wrong_column_count() -> None:
    with pytest.raises(ValueError, match="match the column count"):
        TableWidget(pygame.Rect(0, 0, 100, 100), ["Name"], [("A", "B")])


def test_window_can_be_dragged_and_resized_inside_bounds() -> None:
    bounds = pygame.Rect(0, 0, 800, 600)
    window = UIWindow(pygame.Rect(100, 100, 300, 300), "Overview")
    manager = WindowManager(bounds)
    manager.add(window)

    manager.handle(
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            {"button": 1, "pos": (120, 115)},
        )
    )
    manager.handle(
        pygame.event.Event(
            pygame.MOUSEMOTION,
            {"pos": (170, 145), "rel": (50, 30), "buttons": (1, 0, 0)},
        )
    )
    manager.handle(
        pygame.event.Event(
            pygame.MOUSEBUTTONUP,
            {"button": 1, "pos": (170, 145)},
        )
    )

    assert window.rect.topleft == (150, 130)

    resize_start = (window.rect.right - 4, window.rect.bottom - 4)
    manager.handle(
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            {"button": 1, "pos": resize_start},
        )
    )
    manager.handle(
        pygame.event.Event(
            pygame.MOUSEMOTION,
            {
                "pos": (resize_start[0] + 50, resize_start[1] + 50),
                "rel": (50, 50),
                "buttons": (1, 0, 0),
            },
        )
    )
    manager.handle(
        pygame.event.Event(
            pygame.MOUSEBUTTONUP,
            {"button": 1, "pos": window.rect.bottomright},
        )
    )

    assert window.rect.size == (350, 350)


def test_keyboard_focus_activates_button() -> None:
    activated: list[bool] = []
    button = Button(pygame.Rect(0, 0, 100, 30), "Run", lambda: activated.append(True))
    manager = UIManager()
    manager.set_focusables([button])

    manager.handle_event(
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB}),
        [button],
    )
    manager.handle_event(
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}),
        [button],
    )

    assert activated == [True]


def test_tab_bar_highlights_active_and_hovered_destinations() -> None:
    pygame.font.init()
    surface = pygame.Surface((300, 42))
    theme = Theme()
    tabs = TabBar(pygame.Rect(0, 0, 300, 40), ["GALAXY", "SYSTEM", "EMPIRE"])

    tabs.draw(surface, pygame.font.Font(None, 16), theme)
    assert surface.get_at((50, 38))[:3] == theme.accent

    tabs.handle(
        pygame.event.Event(
            pygame.MOUSEMOTION,
            {"pos": (150, 20)},
        )
    )
    assert tabs.hovered_index == 1


def test_modal_dialog_blocks_input_until_an_action_is_chosen() -> None:
    bounds = pygame.Rect(0, 0, 800, 600)
    chosen: list[str] = []
    manager = UIManager()
    manager.show_dialog(
        "Confirm",
        "Continue?",
        {"Yes": lambda: chosen.append("yes"), "No": lambda: chosen.append("no")},
        bounds,
    )
    dialog = manager.modal
    assert dialog is not None
    button_y = dialog.rect.bottom - 36
    button_x = dialog.rect.centerx - 130

    assert manager.handle_event(
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            {"button": 1, "pos": (button_x + 10, button_y + 10)},
        ),
        [],
    )

    assert chosen == ["yes"]
    assert manager.modal is None
