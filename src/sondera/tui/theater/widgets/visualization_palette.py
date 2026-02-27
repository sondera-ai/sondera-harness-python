"""Visualization palette for selecting theater plugins."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

if TYPE_CHECKING:
    from sondera.tui.theater.plugin import TheaterPlugin


class VisualizationPalette(Widget):
    """Modal overlay for selecting visualization plugins.

    Appears centered on screen with a list of available visualizations.
    Use keyboard (up/down/enter) or click to select.
    Press Escape or 'v' to close without changing.
    """

    can_focus = True

    class Selected(Message):
        """Sent when a visualization is selected."""

        def __init__(self, plugin_id: str) -> None:
            super().__init__()
            self.plugin_id = plugin_id

    class Dismissed(Message):
        """Sent when the palette is dismissed without selection."""

        pass

    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=False),
        Binding("v", "dismiss", "Close", show=False),
        Binding("up", "move_up", "Up", show=False),
        Binding("k", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("j", "move_down", "Down", show=False),
        Binding("enter", "select", "Select", show=False),
    ]

    DEFAULT_CSS = """
    VisualizationPalette {
        width: 40;
        height: auto;
        max-height: 20;
        background: $surface;
        border: tall $primary;
        padding: 0;
    }

    VisualizationPalette #palette-header {
        height: 1;
        background: $primary;
        color: $surface;
        text-style: bold;
        padding: 0 1;
        content-align: center middle;
    }

    VisualizationPalette #palette-list {
        height: auto;
        padding: 0;
    }

    VisualizationPalette .palette-item {
        height: 1;
        padding: 0 2;
        color: $text;
    }

    VisualizationPalette .palette-item:hover {
        background: $primary 20%;
    }

    VisualizationPalette .palette-item.highlighted {
        background: $primary 30%;
        color: $primary-lighten-2;
    }

    VisualizationPalette .palette-item.current {
        color: $primary;
        text-style: bold;
    }

    VisualizationPalette .palette-item.current.highlighted {
        background: $primary 40%;
        color: $primary-lighten-3;
    }
    """

    def __init__(
        self,
        plugins: tuple[type[TheaterPlugin], ...],
        current_plugin_id: str,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._plugins = plugins
        self._current_plugin_id = current_plugin_id
        self._highlighted_index = 0
        self._item_widgets: list[Static] = []

        # Find current plugin index to start highlighting there
        for i, plugin_cls in enumerate(plugins):
            if plugin_cls.plugin_id == current_plugin_id:
                self._highlighted_index = i
                break

    def compose(self) -> ComposeResult:
        yield Static("Visualizations", id="palette-header")
        with Vertical(id="palette-list"):
            for i, plugin_cls in enumerate(self._plugins):
                is_current = plugin_cls.plugin_id == self._current_plugin_id
                is_highlighted = i == self._highlighted_index

                classes = "palette-item"
                if is_current:
                    classes += " current"
                if is_highlighted:
                    classes += " highlighted"

                # Show checkmark for current
                prefix = "● " if is_current else "  "
                item = Static(f"{prefix}{plugin_cls.plugin_name}", classes=classes)
                self._item_widgets.append(item)
                yield item

    def on_mount(self) -> None:
        """Focus self when mounted."""
        self.focus()

    def _update_highlight(self) -> None:
        """Update visual highlighting."""
        for i, item in enumerate(self._item_widgets):
            if i == self._highlighted_index:
                item.add_class("highlighted")
            else:
                item.remove_class("highlighted")

    def action_move_up(self) -> None:
        """Move highlight up."""
        if self._highlighted_index > 0:
            self._highlighted_index -= 1
            self._update_highlight()

    def action_move_down(self) -> None:
        """Move highlight down."""
        if self._highlighted_index < len(self._plugins) - 1:
            self._highlighted_index += 1
            self._update_highlight()

    def action_select(self) -> None:
        """Select the highlighted plugin."""
        if 0 <= self._highlighted_index < len(self._plugins):
            plugin_cls = self._plugins[self._highlighted_index]
            self.post_message(self.Selected(plugin_cls.plugin_id))

    def action_dismiss(self) -> None:
        """Dismiss the palette without selecting."""
        self.post_message(self.Dismissed())

    def on_click(self, event) -> None:
        """Handle click on items."""
        widget = event.widget
        if widget in self._item_widgets:
            idx = self._item_widgets.index(widget)
            self._highlighted_index = idx
            self._update_highlight()
            self.action_select()
