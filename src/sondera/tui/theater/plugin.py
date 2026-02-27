"""Base protocol for theater visualization plugins."""

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.widget import Widget

if TYPE_CHECKING:
    from sondera.tui.theater.events import StepEvent


class TheaterPlugin(Widget):
    """Base class for theater visualization plugins.

    Plugins receive step events during trajectory playback and render
    visualizations. Each plugin is a Textual Widget that composes its
    own UI elements.

    Subclasses must implement `on_step`, `on_reset`, and `compose`.

    Example:
        class MyPlugin(TheaterPlugin):
            plugin_name = "My Visualization"
            plugin_id = "my-viz"

            def on_step(self, event: StepEvent) -> None:
                # Update visualization based on step data
                self.update_display(event)

            def on_reset(self) -> None:
                # Clear visualization state
                self.clear()

            def compose(self) -> ComposeResult:
                yield Static("My visualization content")
    """

    plugin_name: str = "Unnamed Plugin"
    """Display name for the plugin."""

    plugin_id: str = "unnamed"
    """Stable identifier for the plugin (used for selection/switching)."""

    enabled: bool = True
    """Whether the plugin is currently active."""

    def on_step(self, event: "StepEvent") -> None:
        """Called when a trajectory step is played.

        Subclasses must override this method.

        Args:
            event: The step event containing all step data.
        """
        raise NotImplementedError("Subclasses must implement on_step")

    def on_reset(self) -> None:
        """Called when playback is reset to the beginning.

        Subclasses must override this method. Plugins should clear
        their visualization state here.
        """
        raise NotImplementedError("Subclasses must implement on_reset")

    def compose(self) -> ComposeResult:
        """Return widgets for this plugin's visualization.

        Subclasses must override this method.

        Returns:
            An iterable of widgets to display.
        """
        raise NotImplementedError("Subclasses must implement compose")

    def set_current_index(self, index: int) -> None:
        """Optional: Set which point is current (for seeking/rewinding).

        Plugins that support seeking can override this method.

        Args:
            index: The index of the current step.
        """
        pass

    def set_playing(self, playing: bool) -> None:
        """Optional: Set whether the visualization is actively playing.

        Plugins that have different active/paused states can override this.

        Args:
            playing: True if playback is active, False if paused.
        """
        pass
