"""EKG Plot visualization plugin for trajectory theater."""

from __future__ import annotations

from textual.app import ComposeResult

from sondera.tui.theater.events import StepEvent
from sondera.tui.theater.plugin import TheaterPlugin
from sondera.tui.theater.widgets import AnimationCanvas


class EKGPlugin(TheaterPlugin):
    """EKG-style decision plot visualization.

    Shows decisions as a scrolling EKG plot where:
    - Row 0: ALLOW (green)
    - Row 1: DENY (red)
    - Row 2: ESCALATE (yellow)

    Points are connected with lines. Supports rewinding (only shows
    points up to current position). Click on a dot to navigate to that step.
    """

    plugin_name = "EKG Plot"
    plugin_id = "ekg"

    DEFAULT_CSS = """
    EKGPlugin {
        width: 100%;
        height: 100%;
    }
    """

    def __init__(
        self,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._canvas: AnimationCanvas | None = None

    def compose(self) -> ComposeResult:
        self._canvas = AnimationCanvas(id="animation")
        yield self._canvas

    def on_step(self, event: StepEvent) -> None:
        if self._canvas:
            self._canvas.on_step(event)

    def on_reset(self) -> None:
        if self._canvas:
            self._canvas.reset()

    def set_current_index(self, index: int) -> None:
        """Set which point is current (for seeking/rewinding)."""
        if self._canvas:
            self._canvas.set_current_index(index)

    def set_playing(self, playing: bool) -> None:
        """Set whether the animation should be active."""
        if self._canvas:
            self._canvas.set_playing(playing)
