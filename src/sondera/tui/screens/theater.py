"""Trajectory Theater screen - iMovie-style layout."""

from __future__ import annotations

import contextlib
from collections import defaultdict
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.css.query import NoMatches
from textual.events import MouseDown, MouseMove, MouseUp
from textual.message import Message
from textual.reactive import reactive
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Button, Footer, Header, Static

from sondera.tui.theater.events import PlaybackComplete, PlaybackReset, StepEvent
from sondera.tui.theater.player import TrajectoryPlayer
from sondera.tui.theater.plugin import TheaterPlugin
from sondera.tui.theater.plugins import AVAILABLE_PLUGINS, EKGPlugin
from sondera.tui.theater.widgets import AnimationCanvas, VisualizationPalette
from sondera.types import AdjudicatedTrajectory, Decision, Role


class FocusableStepLog(ScrollableContainer):
    """A step log container that can be focused and navigated with arrow keys."""

    can_focus = True

    class StepSelected(Message):
        """Emitted when a step is selected via keyboard navigation."""

        def __init__(self, step_index: int, direction: int) -> None:
            super().__init__()
            self.step_index = step_index
            self.direction = direction  # -1 for up, +1 for down

    BINDINGS = [
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
    ]

    DEFAULT_CSS = """
    FocusableStepLog {
        /* No visible focus indicator - just captures key events when focused */
    }
    FocusableStepLog:focus {
        /* No border change on focus to prevent layout shift */
    }
    """

    def action_move_up(self) -> None:
        """Move selection up."""
        self.post_message(self.StepSelected(step_index=-1, direction=-1))

    def action_move_down(self) -> None:
        """Move selection down."""
        self.post_message(self.StepSelected(step_index=-1, direction=1))


class VCRButton(Button):
    """Button for VCR controls with subtle focus styling."""

    pass


class RepeatButton(VCRButton):
    """Button that repeats action while held down.

    Single click triggers one action. Holding starts repeat after a short delay.
    """

    INITIAL_DELAY = 0.4  # Seconds before repeat starts
    REPEAT_INTERVAL = 0.1  # Seconds between repeats

    class Repeated(Message):
        """Sent when button action should repeat."""

        def __init__(self, button: RepeatButton) -> None:
            super().__init__()
            self.button = button

    def __init__(
        self,
        label: str = "",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        super().__init__(label, name=name, id=id, classes=classes, disabled=disabled)
        self._holding = False
        self._repeat_timer = None
        self._initial_timer = None

    def on_mouse_down(self, event: MouseDown) -> None:
        """Start tracking hold state."""
        if self.disabled:
            return
        self._holding = True
        # First action happens immediately via normal Button.Pressed
        # Then start timer for repeat after delay
        self._initial_timer = self.set_timer(self.INITIAL_DELAY, self._start_repeating)

    def _start_repeating(self) -> None:
        """Begin rapid repeating after initial delay."""
        if not self._holding:
            return
        self._repeat_timer = self.set_interval(self.REPEAT_INTERVAL, self._on_repeat)

    def _on_repeat(self) -> None:
        """Fire repeat event."""
        if self._holding:
            self.post_message(self.Repeated(self))

    def on_mouse_up(self, event: MouseUp) -> None:
        """Stop repeating."""
        self._stop_holding()

    def on_leave(self, event) -> None:
        """Stop if mouse leaves button."""
        self._stop_holding()

    def _stop_holding(self) -> None:
        """Clean up hold state and timers."""
        self._holding = False
        if self._initial_timer:
            self._initial_timer.stop()
            self._initial_timer = None
        if self._repeat_timer:
            self._repeat_timer.stop()
            self._repeat_timer = None


class Splitter(Widget):
    """A draggable horizontal splitter bar.

    Uses background colors instead of text characters to minimize
    text selection artifacts during dragging.
    """

    can_focus = False

    class Dragged(Message):
        """Sent when the splitter is dragged."""

        def __init__(self, delta: int) -> None:
            super().__init__()
            self.delta = delta

    DEFAULT_CSS = """
    Splitter {
        height: 1;
        width: 100%;
        background: $primary 30%;
        content-align: center middle;
    }
    Splitter:hover {
        background: $primary 60%;
    }
    Splitter.dragging {
        background: $primary;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._dragging = False
        self._last_y: int | None = None

    def render(self) -> Text:
        from rich.style import Style

        width = self.size.width
        line = Text()

        # Calculate padding for centering the arrow indicator
        label = " ⬍ "
        label_len = len(label)
        left_pad = (width - label_len) // 2
        right_pad = width - label_len - left_pad

        # Get background color from resolved styles
        bg = self.styles.background
        bg_color = f"rgb({bg.r},{bg.g},{bg.b})" if bg else "rgb(45,74,62)"
        bar_style = Style(bgcolor=bg_color)
        label_style = Style(color="rgb(128,128,128)", bgcolor=bg_color)

        line.append(" " * left_pad, bar_style)
        line.append(label, label_style)
        line.append(" " * right_pad, bar_style)

        return line

    def on_mouse_down(self, event: MouseDown) -> None:
        self._dragging = True
        self._last_y = event.screen_y
        self.add_class("dragging")
        self.capture_mouse()
        event.stop()
        event.prevent_default()

    def on_mouse_move(self, event: MouseMove) -> None:
        if self._dragging and self._last_y is not None:
            delta = self._last_y - event.screen_y
            if delta != 0:
                self.post_message(self.Dragged(delta))
                self._last_y = event.screen_y
            event.stop()
            event.prevent_default()

    def on_mouse_up(self, event: MouseUp) -> None:
        if self._dragging:
            self._dragging = False
            self._last_y = None
            self.remove_class("dragging")
            self.release_mouse()
            event.stop()
            event.prevent_default()


class TimelineScrubber(Widget):
    """A draggable timeline scrubber for seeking through trajectory.

    Uses background color strips instead of text characters to minimize
    text selection artifacts during dragging.
    """

    can_focus = False

    class Seeked(Message):
        """Sent when user seeks to a position."""

        def __init__(self, progress: float) -> None:
            super().__init__()
            self.progress = progress  # 0.0 to 1.0

    DEFAULT_CSS = """
    TimelineScrubber {
        height: 1;
        width: 100%;
        background: $surface-darken-1;
    }
    """

    def __init__(
        self,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._progress: float = 0.0
        self._total_steps: int = 0
        self._current_step: int = 0
        self._dragging = False

    def set_progress(self, current: int, total: int) -> None:
        """Update the progress display."""
        self._current_step = current
        self._total_steps = total
        self._progress = current / max(1, total - 1) if total > 1 else 0.0
        self.refresh()

    def render(self) -> Text:
        """Render the scrubber bar using spaces with background colors.

        This minimizes text selection issues since there's nothing to select.
        """
        from rich.style import Style

        width = self.size.width
        if width < 10:
            width = 60

        # Calculate handle position (handle is 3 chars wide)
        handle_width = 3
        track_width = max(1, width - handle_width)
        handle_pos = int(self._progress * track_width)

        line = Text()

        # Get colors dynamically from current theme
        # This adapts to any theme (nord, dracula, solarized, etc.)
        try:
            # Get primary color from theme for handle
            primary = self.app.get_css_variables().get("primary", "rgb(129,221,180)")
            # Parse primary to derive related colors
            if primary.startswith("#"):
                # Convert hex to RGB
                hex_color = primary.lstrip("#")
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
            elif primary.startswith("rgb"):
                # Parse rgb(r,g,b)
                import re

                match = re.match(r"rgb\((\d+),\s*(\d+),\s*(\d+)\)", primary)
                if match:
                    r, g, b = (
                        int(match.group(1)),
                        int(match.group(2)),
                        int(match.group(3)),
                    )
                else:
                    r, g, b = 129, 221, 180  # fallback
            else:
                r, g, b = 129, 221, 180  # fallback

            # Handle: full primary color
            handle_color = f"rgb({r},{g},{b})"
            # Played: slightly dimmed primary
            played_color = f"rgb({int(r * 0.7)},{int(g * 0.7)},{int(b * 0.7)})"
            # Remaining: much darker version
            remaining_color = f"rgb({int(r * 0.25)},{int(g * 0.25)},{int(b * 0.25)})"
        except Exception:
            # Fallback to neutral colors
            handle_color = "rgb(200,200,200)"
            played_color = "rgb(120,120,120)"
            remaining_color = "rgb(50,50,50)"

        played_style = Style(bgcolor=played_color)
        handle_style = Style(bgcolor=handle_color)
        remaining_style = Style(bgcolor=remaining_color)

        # Build progress bar with spaces (no selectable text)
        for i in range(width):
            if handle_pos <= i < handle_pos + handle_width:
                line.append(" ", handle_style)
            elif i < handle_pos:
                line.append(" ", played_style)
            else:
                line.append(" ", remaining_style)

        return line

    def _get_progress_from_x(self, x: int) -> float:
        """Convert x coordinate to progress value."""
        width = max(1, self.size.width - 3)  # Account for handle width
        x = max(0, min(x, width))
        return x / max(1, width)

    def on_mouse_down(self, event: MouseDown) -> None:
        self._dragging = True
        progress = self._get_progress_from_x(event.x)
        self._progress = progress
        self.post_message(self.Seeked(progress))
        self.capture_mouse()
        self.refresh()
        event.stop()
        event.prevent_default()

    def on_mouse_move(self, event: MouseMove) -> None:
        if self._dragging:
            progress = self._get_progress_from_x(event.x)
            self._progress = progress
            self.post_message(self.Seeked(progress))
            self.refresh()
            event.stop()
            event.prevent_default()

    def on_mouse_up(self, event: MouseUp) -> None:
        if self._dragging:
            self._dragging = False
            self.release_mouse()
            self.refresh()
            event.stop()
            event.prevent_default()


class TrajectoryTheater(Screen):
    """Trajectory playback with visualization."""

    TITLE = "Sondera Harness"
    SUB_TITLE = "Trajectory Theater"

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("space", "toggle_play", "Play/Pause"),
        Binding("r", "reset", "Reset"),
        Binding("l", "toggle_loop", "Loop"),
        Binding("v", "show_viz_palette", "Viz"),
        Binding("left", "step_back", "◀ Prev"),
        Binding("right", "step_forward", "Next ▶"),
        Binding("up", "speed_up", "Faster"),
        Binding("down", "speed_down", "Slower"),
        Binding("home", "go_to_start", "Start", show=False),
        Binding("end", "go_to_end", "End", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("plus", "grow_chart", "+Chart", show=False),
        Binding("equal", "grow_chart", "+Chart", show=False),
        Binding("minus", "shrink_chart", "-Chart", show=False),
    ]

    DEFAULT_CSS = """
    TrajectoryTheater {
        background: $surface;
    }

    #theater-layout {
        width: 100%;
        height: 1fr;
    }

    /* Left sidebar */
    #picker {
        width: 28;
        height: 100%;
        border-right: tall $primary;
    }

    #picker-header {
        height: 1;
        padding: 0 1;
        background: $primary;
        color: $surface;
        text-style: bold;
    }

    #traj-list {
        height: 1fr;
    }

    .agent-header {
        height: 1;
        padding: 0 1;
        background: $panel;
        color: $text-muted;
    }

    .agent-header:hover {
        background: $primary 20%;
    }

    .agent-header.has-selection {
        color: $primary;
        text-style: bold;
    }

    .traj-item {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }

    .traj-item:hover {
        background: $primary 15%;
    }

    .traj-item.selected {
        background: $primary;
        color: $surface;
        text-style: bold;
    }

    /* Main content - no padding to use full width */
    #main-content {
        width: 1fr;
        height: 100%;
    }

    /* Header bar */
    #header-bar {
        height: 1;
        background: $panel;
        padding: 0 1;
    }

    #header-agent {
        width: 1fr;
        text-style: bold;
        color: $primary;
    }

    #header-info {
        width: auto;
        color: $text-muted;
    }

    /* Step log - fills available space */
    #step-log {
        height: 1fr;
        min-height: 5;
        padding: 0 1;
    }

    .log-entry {
        height: 1;
    }

    .log-entry:hover {
        background: $primary 10%;
    }

    .log-entry.current {
        background: $primary 15%;
    }

    .log-num {
        width: 4;
        color: $text-muted;
    }

    .log-role {
        width: 8;
        text-style: bold;
    }

    .log-role.user { color: #7aa2f7; }
    .log-role.model { color: #bb9af7; }
    .log-role.tool { color: #7dcfff; }

    .log-decision {
        width: 12;
    }

    .log-decision.allow { color: $success; }
    .log-decision.deny { color: $error; }
    .log-decision.escalate { color: $warning; }

    .log-content {
        width: 1fr;
        color: $text;
    }

    /* Transport bar - matches theme */
    #transport-bar {
        height: 3;
        background: $surface-darken-1;
        padding: 0 1;
    }

    #vcr-buttons {
        width: auto;
        height: 3;
    }

    /* Transport buttons - theme-aware */
    .vcr-btn {
        min-width: 5;
        height: 3;
        border: none;
        margin: 0;
        text-style: bold;
        background: $surface-darken-2;
        color: $text-muted;
    }

    .vcr-btn:hover {
        background: $primary 30%;
        color: $primary-lighten-2;
        border: none;
    }

    .vcr-btn:focus {
        background: $primary 20%;
        color: $primary;
        border: none;
    }

    .vcr-btn.-active {
        background: $surface-darken-2;
        color: $text-muted;
        border: none;
    }

    /* Prevent button focus highlight rectangles */
    Button:focus {
        border: none;
    }

    /* Play button when playing - bright icon */
    #btn-play.playing {
        color: $primary;
        text-style: bold;
    }

    /* Loop button when active - bright icon */
    #btn-loop.loop-active {
        color: $primary;
    }

    /* Counter display - same style as buttons */
    #counter-display {
        width: 11;
        height: 3;
        background: $surface-darken-2;
        border: none;
        padding: 0 1;
        margin-left: 1;
        color: $text-muted;
        text-style: bold;
        content-align: center middle;
    }

    /* Speed panel */
    #speed-panel {
        width: auto;
        height: 3;
        background: transparent;
        margin-left: 1;
    }

    /* Speed buttons - just override width, inherit rest from .vcr-btn */
    #btn-slower, #btn-faster {
        min-width: 4;
    }

    #speed-display {
        width: 6;
        height: 3;
        background: $surface-darken-2;
        color: $text-muted;
        text-style: bold;
        content-align: center middle;
        border: none;
    }

    /* Scrubber row */
    #scrubber-row {
        height: 1;
        padding: 0 1;
        background: $surface-darken-1;
    }


    /* Animation - default 8 rows for good visibility */
    #animation-area {
        height: 8;
        padding: 0 1;
    }

    AnimationCanvas {
        height: 1fr;
        width: 100%;
    }

    /* Theater plugins fill the animation area */
    TheaterPlugin {
        height: 1fr;
        width: 100%;
    }

    TrajectoryPlayer {
        display: none;
    }

    /* Visualization palette overlay - centered modal */
    #viz-palette-container {
        width: 100%;
        height: 100%;
        align: center middle;
        background: rgba(0, 0, 0, 0.5);
    }
    """

    loop_enabled: reactive[bool] = reactive(False)
    current_speed: reactive[float] = reactive(1.0)
    chart_height: reactive[int] = reactive(8)  # Default chart height in rows

    def __init__(self, trajectory_file: Path | None = None) -> None:
        super().__init__()
        self._trajectory_file = trajectory_file
        self._trajectories: list[AdjudicatedTrajectory] = []
        self._grouped: dict[str, list[AdjudicatedTrajectory]] = {}
        self._player: TrajectoryPlayer | None = None
        self._current_traj: AdjudicatedTrajectory | None = None
        self._selected_traj_id: str | None = None
        self._expanded_agents: set[str] = set()
        self._widget_data: dict[int, dict] = {}
        self._step_history: list[StepEvent] = []
        self._step_widgets: dict[int, Horizontal] = {}  # step_index -> log entry widget
        self._loading_trajectory = False  # Flag during trajectory loading
        self._selected_log_step: int = 0  # Currently selected step in the log
        # Visualization plugin state
        self._current_plugin_class: type[TheaterPlugin] = EKGPlugin
        self._current_plugin: TheaterPlugin | None = None
        self._viz_palette: VisualizationPalette | None = None

    def compose(self) -> ComposeResult:
        yield Header()

        with Horizontal(id="theater-layout"):
            # Left: Trajectory list
            with Vertical(id="picker"):
                yield Static("TRAJECTORIES", id="picker-header")
                yield ScrollableContainer(id="traj-list")

            # Right: Main content
            with Vertical(id="main-content"):
                # Header
                with Horizontal(id="header-bar"):
                    yield Static("Select a trajectory", id="header-agent")
                    yield Static("", id="header-info")

                # Step log - focusable for keyboard navigation
                yield FocusableStepLog(id="step-log")

                # Transport + Timeline (VCR style)
                with Horizontal(id="transport-bar"):
                    # VCR-style button panel
                    with Horizontal(id="vcr-buttons"):
                        yield VCRButton("⏮", id="btn-start", classes="vcr-btn")
                        yield RepeatButton("◀◀", id="btn-prev", classes="vcr-btn")
                        yield VCRButton("▶", id="btn-play", classes="vcr-btn")
                        yield RepeatButton("▶▶", id="btn-next", classes="vcr-btn")
                        yield VCRButton("⏭", id="btn-end", classes="vcr-btn")
                        yield VCRButton("⟳", id="btn-loop", classes="vcr-btn")

                    # Analog counter display - single widget for reliability
                    yield Static("001/100", id="counter-display")

                    # Speed control
                    with Horizontal(id="speed-panel"):
                        yield VCRButton("−", id="btn-slower", classes="vcr-btn")
                        yield Static("1.0x", id="speed-display")
                        yield VCRButton("+", id="btn-faster", classes="vcr-btn")

                # Scrubber bar
                with Horizontal(id="scrubber-row"):
                    yield TimelineScrubber(id="scrubber")

                # Resizable splitter
                yield Splitter()

                # Animation area - dynamically mounts plugins
                yield Vertical(id="animation-area")

        self._player = TrajectoryPlayer(id="player")
        yield self._player
        yield Footer()

    def on_mount(self) -> None:
        # Mount the initial visualization plugin
        self._mount_plugin(self._current_plugin_class)
        self._load_trajectories()
        # Don't autoplay - let user control playback
        # Sync loop button state with initial value
        if self.loop_enabled:
            self.query_one("#btn-loop", VCRButton).add_class("loop-active")

    def _mount_plugin(self, plugin_class: type[TheaterPlugin]) -> None:
        """Mount a visualization plugin into the animation area."""
        animation_area = self.query_one("#animation-area", Vertical)

        # Remove existing plugin
        if self._current_plugin:
            self._current_plugin.remove()

        # Create and mount new plugin
        self._current_plugin_class = plugin_class
        self._current_plugin = plugin_class(id="viz-plugin")
        animation_area.mount(self._current_plugin)

        # Replay step history to the new plugin
        if self._step_history:
            for event in self._step_history:
                self._current_plugin.on_step(event)

    def _swap_visualization(self, plugin_id: str) -> None:
        """Swap to a different visualization plugin."""
        # Find the plugin class
        for plugin_class in AVAILABLE_PLUGINS:
            if plugin_class.plugin_id == plugin_id:
                if plugin_class != self._current_plugin_class:
                    self._mount_plugin(plugin_class)
                break

    def action_show_viz_palette(self) -> None:
        """Show the visualization selector palette."""
        if self._viz_palette:
            # Palette already open, dismiss it
            self._dismiss_viz_palette()
            return

        # Create and mount the palette as an overlay
        from textual.containers import Container

        container = Container(id="viz-palette-container")
        self._viz_palette = VisualizationPalette(
            plugins=AVAILABLE_PLUGINS,
            current_plugin_id=self._current_plugin_class.plugin_id,
            id="viz-palette",
        )
        self.mount(container)
        container.mount(self._viz_palette)

    def _dismiss_viz_palette(self) -> None:
        """Dismiss the visualization palette."""
        if self._viz_palette:
            try:
                container = self.query_one("#viz-palette-container")
                container.remove()
            except Exception:
                pass
            self._viz_palette = None

    def on_visualization_palette_selected(
        self, event: VisualizationPalette.Selected
    ) -> None:
        """Handle visualization selection from palette."""
        self._swap_visualization(event.plugin_id)
        self._dismiss_viz_palette()

    def on_visualization_palette_dismissed(
        self, event: VisualizationPalette.Dismissed
    ) -> None:
        """Handle palette dismissal."""
        self._dismiss_viz_palette()

    def _load_trajectories(self) -> None:
        """Load trajectories from JSON file."""
        paths = [
            Path("data/sample_trajectories/trajectories.json"),
            Path.cwd() / "data" / "sample_trajectories" / "trajectories.json",
        ]
        if self._trajectory_file:
            paths.insert(0, self._trajectory_file)

        if not self._player:
            return

        for path in paths:
            if path.exists():
                try:
                    self._trajectories = self._player.load_from_file(path)
                    break
                except Exception as e:
                    self.notify(f"Error: {e}", severity="error")
                    return

        if not self._trajectories:
            self.notify("No trajectories found", severity="warning")
            return

        self._trajectories.sort(key=lambda t: t.created_at, reverse=True)

        self._grouped = defaultdict(list)
        for traj in self._trajectories:
            self._grouped[traj.agent_id].append(traj)

        self._expanded_agents = set(self._grouped.keys())
        self._build_trajectory_list()

        if self._trajectories:
            self._select_trajectory(self._trajectories[0])

    def _build_trajectory_list(self) -> None:
        """Build the trajectory list UI."""
        traj_list = self.query_one("#traj-list", ScrollableContainer)

        children = list(traj_list.children)
        for child in children:
            child.remove()

        self._widget_data = {}

        for agent_id in sorted(self._grouped.keys()):
            trajectories = self._grouped[agent_id]
            is_expanded = agent_id in self._expanded_agents

            has_selection = any(t.id == self._selected_traj_id for t in trajectories)

            arrow = "▼" if is_expanded else "▶"
            name = agent_id[:22] + "…" if len(agent_id) > 22 else agent_id
            header_text = f"{arrow} {name} ({len(trajectories)})"

            header_classes = "agent-header"
            if has_selection:
                header_classes += " has-selection"

            header = Static(header_text, classes=header_classes)
            self._widget_data[id(header)] = {"type": "agent", "agent_id": agent_id}
            traj_list.mount(header)

            if is_expanded:
                for traj in trajectories:
                    date = traj.created_at.strftime("%b %d %H:%M")
                    steps = len(traj.steps)
                    item_text = f"  {date} [{steps}]"

                    item_classes = "traj-item"
                    if traj.id == self._selected_traj_id:
                        item_classes += " selected"

                    item = Static(item_text, classes=item_classes)
                    self._widget_data[id(item)] = {"type": "traj", "traj_id": traj.id}
                    traj_list.mount(item)

    def _select_trajectory(self, traj: AdjudicatedTrajectory) -> None:
        """Select a trajectory for playback."""
        self._current_traj = traj
        self._selected_traj_id = traj.id
        self._step_history = []
        self._step_widgets = {}
        self._selected_log_step = 0  # Reset to first step
        self._loading_trajectory = True  # Flag to prevent reset from clearing

        # Clear and reset first
        self._clear_step_log()
        if self._current_plugin:
            self._current_plugin.on_reset()

        # Pre-populate all steps for historical trajectories
        self._load_all_steps(traj)

        # Now load into player (won't emit since we pass emit_first=False)
        if self._player:
            self._player.load_trajectory(traj, emit_first=False)

        self._loading_trajectory = False

        date_str = traj.created_at.strftime("%Y-%m-%d %H:%M")
        self.query_one("#header-agent", Static).update(f"[bold]{traj.agent_id}[/]")
        self.query_one("#header-info", Static).update(
            f"{date_str}  1/{len(traj.steps)}"
        )

        self._update_timeline(0, len(traj.steps))
        self._update_selection_highlight()

        # Highlight first step
        if traj.steps:
            self._highlight_step(0)

    def _load_all_steps(self, traj: AdjudicatedTrajectory) -> None:
        """Load all steps from a trajectory into the log and animation."""
        for i, step in enumerate(traj.steps):
            event = StepEvent(
                step_index=i,
                total_steps=len(traj.steps),
                stage=step.step.stage,
                role=step.step.role,
                decision=step.adjudication.decision,
                reason=step.adjudication.reason,
                content=step.step.content,
                timestamp=step.step.created_at,
                delta_ms=0,
                policy_ids=[p.id for p in step.adjudication.policies],
            )
            self._step_history.append(event)
            self._add_step_to_log(event, highlight=False)
            if self._current_plugin:
                self._current_plugin.on_step(event)

    def _clear_step_log(self) -> None:
        """Clear the step log."""
        step_log = self.query_one("#step-log", FocusableStepLog)
        children = list(step_log.children)
        for child in children:
            child.remove()

    def _add_step_to_log(self, event: StepEvent, highlight: bool = True) -> None:
        """Add a step to the scrollable log.

        Args:
            event: The step event to add.
            highlight: Whether to highlight this step as current.
        """
        step_log = self.query_one("#step-log", FocusableStepLog)

        if highlight:
            for child in step_log.children:
                if hasattr(child, "remove_class"):
                    child.remove_class("current")

        # Role with single letter marker (matches visualization)
        role_markers = {Role.USER: "U", Role.MODEL: "M", Role.TOOL: "T"}
        role_names = {Role.USER: "USER", Role.MODEL: "MODEL", Role.TOOL: "TOOL"}
        role_marker = role_markers.get(event.role, "?")
        role_name = role_names.get(event.role, "?")
        role_class = event.role.value

        # Format decision with full word
        dec_info = {
            Decision.ALLOW: ("✓", "ALLOW"),
            Decision.DENY: ("✗", "DENY"),
            Decision.ESCALATE: ("⚠", "ESCALATE"),
        }
        dec_symbol, dec_text = dec_info.get(event.decision, ("?", "?"))
        dec_class = event.decision.value

        # Format content - show rule reason and policy IDs for DENY/ESCALATE
        content = self._format_content(event)
        if event.decision == Decision.DENY:
            # Show reason and policy IDs prominently before content
            reason_text = event.reason or "blocked"
            if event.policy_ids:
                policies = ", ".join(event.policy_ids)
                display_content = f"[bold #BF616A]«{reason_text}»[/] [dim #BF616A]({policies})[/] {content}"
            else:
                display_content = f"[bold #BF616A]«{reason_text}»[/] {content}"
        elif event.decision == Decision.ESCALATE:
            reason_text = event.reason or "escalated"
            if event.policy_ids:
                policies = ", ".join(event.policy_ids)
                display_content = f"[bold #EBCB8B]«{reason_text}»[/] [dim #EBCB8B]({policies})[/] {content}"
            else:
                display_content = f"[bold #EBCB8B]«{reason_text}»[/] {content}"
        else:
            display_content = content

        # Step number (1-indexed for display)
        step_num = f"{event.step_index + 1:3d}"

        entry_classes = "log-entry current" if highlight else "log-entry"
        entry = Horizontal(classes=entry_classes)
        num_widget = Static(step_num, classes="log-num")
        # Show marker + name for clarity (e.g., "M MODEL")
        role_widget = Static(
            f"{role_marker} {role_name}", classes=f"log-role {role_class}"
        )
        dec_widget = Static(
            f"{dec_symbol} {dec_text}", classes=f"log-decision {dec_class}"
        )
        # Use markup=True to parse Rich formatting for reasons
        content_widget = Static(display_content, classes="log-content", markup=True)

        # Store step index for click-to-seek and seeking highlight
        self._widget_data[id(entry)] = {
            "type": "log-entry",
            "step_index": event.step_index,
        }
        self._step_widgets[event.step_index] = entry

        step_log.mount(entry)
        entry.mount(num_widget)
        entry.mount(role_widget)
        entry.mount(dec_widget)
        entry.mount(content_widget)

        if highlight:
            step_log.scroll_end(animate=False)

    def _highlight_step(self, step_index: int) -> None:
        """Highlight an existing step entry and scroll to it."""
        self._selected_log_step = step_index  # Keep selection in sync
        step_log = self.query_one("#step-log", FocusableStepLog)

        # Remove 'current' class from all entries
        for child in step_log.children:
            if hasattr(child, "remove_class"):
                child.remove_class("current")

        # Highlight the target entry
        if step_index in self._step_widgets:
            entry = self._step_widgets[step_index]
            entry.add_class("current")
            entry.scroll_visible(animate=False)

        # Update the visualization to highlight this point
        if self._current_plugin:
            self._current_plugin.set_current_index(step_index)

    def _update_selection_highlight(self) -> None:
        """Update selection highlighting without rebuilding list."""
        traj_list = self.query_one("#traj-list", ScrollableContainer)
        for child in traj_list.children:
            if not isinstance(child, Static):
                continue
            data = self._widget_data.get(id(child))
            if not data:
                continue

            if data["type"] == "traj":
                if data["traj_id"] == self._selected_traj_id:
                    child.add_class("selected")
                else:
                    child.remove_class("selected")
            elif data["type"] == "agent":
                agent_id = data["agent_id"]
                trajectories = self._grouped.get(agent_id, [])
                has_selection = any(
                    t.id == self._selected_traj_id for t in trajectories
                )
                if has_selection:
                    child.add_class("has-selection")
                else:
                    child.remove_class("has-selection")

    def _update_timeline(self, current: int, total: int) -> None:
        """Update the timeline display."""
        # Update the scrubber
        try:
            scrubber = self.query_one("#scrubber", TimelineScrubber)
            scrubber.set_progress(current, total)
        except Exception:
            pass

        # Update analog counter display (single widget now)
        try:
            counter_text = f"{current + 1:03d}/{total:03d}"
            self.query_one("#counter-display", Static).update(counter_text)
        except Exception:
            pass

    def on_splitter_dragged(self, event: Splitter.Dragged) -> None:
        """Handle splitter drag to resize chart."""
        new_height = self.chart_height + event.delta
        self.chart_height = max(4, min(30, new_height))

    def on_timeline_scrubber_seeked(self, event: TimelineScrubber.Seeked) -> None:
        """Handle scrubber drag to seek."""
        if self._player and self._current_traj:
            total = len(self._current_traj.steps)
            step = int(event.progress * (total - 1))
            step = max(0, min(step, total - 1))
            self.seek_to_step(step)

    def on_animation_canvas_dot_clicked(
        self, event: AnimationCanvas.DotClicked
    ) -> None:
        """Handle click on a dot in the animation - scroll to row without changing playback."""
        self._scroll_to_step_row(event.step_index)

    def on_focusable_step_log_step_selected(
        self, event: FocusableStepLog.StepSelected
    ) -> None:
        """Handle keyboard navigation in the step log."""
        if not self._current_traj:
            return
        total = len(self._current_traj.steps)
        if total == 0:
            return

        # Calculate new step based on direction
        new_step = self._selected_log_step + event.direction
        new_step = max(0, min(new_step, total - 1))

        if new_step != self._selected_log_step:
            self._selected_log_step = new_step
            self._select_log_step(new_step)

    def _scroll_to_step_row(self, step_index: int) -> None:
        """Scroll to and highlight a step row without affecting playback position."""
        step_log = self.query_one("#step-log", FocusableStepLog)

        # Remove 'current' class from all entries
        for child in step_log.children:
            if hasattr(child, "remove_class"):
                child.remove_class("current")

        # Highlight and scroll to the target entry
        if step_index in self._step_widgets:
            entry = self._step_widgets[step_index]
            entry.add_class("current")
            entry.scroll_visible(animate=True)

    def on_click(self, event) -> None:
        """Handle clicks on list items and log entries."""
        widget = event.widget
        if not widget:
            return

        # Check widget and its parent (for log entry children)
        data = self._widget_data.get(id(widget))
        if not data and hasattr(widget, "parent"):
            data = self._widget_data.get(id(widget.parent))

        if not data:
            return

        if data["type"] == "agent":
            agent_id = data["agent_id"]
            if agent_id in self._expanded_agents:
                self._expanded_agents.remove(agent_id)
            else:
                self._expanded_agents.add(agent_id)
            self._build_trajectory_list()
            return

        if data["type"] == "traj":
            traj_id = data["traj_id"]
            for traj in self._trajectories:
                if traj.id == traj_id:
                    self._select_trajectory(traj)
                    if self._player:
                        self._player.play()
                        self._update_play_button(True)
                    break
            return

        if data["type"] == "log-entry":
            # Click on log entry - select that step
            step_index = data["step_index"]
            self._selected_log_step = step_index
            self._select_log_step(step_index)

    def on_step_event(self, event: StepEvent) -> None:
        """Handle step playback."""
        if self._current_traj:
            date_str = self._current_traj.created_at.strftime("%Y-%m-%d %H:%M")
            self.query_one("#header-info", Static).update(
                f"{date_str}  {event.step_index + 1}/{event.total_steps}"
            )

        # Check if this step is already displayed (seeking to existing step)
        if event.step_index in self._step_widgets:
            # Just highlight the existing entry and scroll to it
            self._highlight_step(event.step_index)
        else:
            # New step - add to log and history
            self._step_history.append(event)
            self._add_step_to_log(event)
            if self._current_plugin:
                self._current_plugin.on_step(event)

        self._update_timeline(event.step_index, event.total_steps)

    def _format_content(self, event: StepEvent) -> str:
        """Format step content - handle various structures."""
        content = event.content
        role = event.role

        # Handle dict content
        if isinstance(content, dict):
            ctype = content.get("content_type", "")

            if ctype == "prompt":
                text = content.get("text", "")
                # Handle text as list (e.g., list of tool uses)
                if isinstance(text, list):
                    if text:
                        first = text[0]
                        if isinstance(first, dict):
                            if "toolUse" in first:
                                tool_use = first["toolUse"]
                                name = tool_use.get("name", "?")
                                return f"→ {name}(...)"
                            if "text" in first:
                                return str(first["text"])[:120].replace("\n", " ")
                        return str(first)[:120]
                    return f"[{role.value} - no content]"
                # Handle text as string
                if isinstance(text, str) and text.strip():
                    return text[:120].replace("\n", " ")
                # Empty text - show stage info
                stage = event.stage.value if hasattr(event, "stage") else ""
                if role == Role.MODEL:
                    return f"[{stage}]" if stage else "[thinking...]"
                return f"[{role.value}]"

            elif ctype == "tool_request":
                tool = content.get("tool_id", "?")
                args = content.get("args", {})
                args_str = str(args)[:60] if args else ""
                return f"→ {tool}({args_str})"

            elif ctype == "tool_response":
                tool = content.get("tool_id", "?")
                resp = str(content.get("response", ""))[:60]
                return f"← {tool}: {resp}"

            # Generic dict - try to extract something useful
            for key in ["text", "message", "content", "output"]:
                if key in content and content[key]:
                    val = content[key]
                    if isinstance(val, str) and val.strip():
                        return val[:120].replace("\n", " ")
                    if val:
                        return str(val)[:120]
            return f"[{role.value}]"

        # Handle object content (Pydantic models)
        ctype = getattr(content, "content_type", "")
        if ctype == "prompt":
            text = getattr(content, "text", "")
            if isinstance(text, list) and text:
                first = text[0]
                if isinstance(first, dict) and "toolUse" in first:
                    return f"→ {first['toolUse'].get('name', '?')}(...)"
                return str(first)[:120]
            if isinstance(text, str) and text.strip():
                return text[:120].replace("\n", " ")
            stage = event.stage.value if hasattr(event, "stage") else ""
            if role == Role.MODEL:
                return f"[{stage}]" if stage else "[thinking...]"
            return f"[{role.value}]"
        elif ctype == "tool_request":
            tool = getattr(content, "tool_id", "?")
            args = getattr(content, "args", {})
            args_str = str(args)[:60] if args else ""
            return f"→ {tool}({args_str})"
        elif ctype == "tool_response":
            tool = getattr(content, "tool_id", "?")
            resp = str(getattr(content, "response", ""))[:60]
            return f"← {tool}: {resp}"

        return str(content)[:120] if str(content).strip() else f"[{role.value}]"

    def on_playback_reset(self, event: PlaybackReset) -> None:
        """Handle reset - but don't clear if we're loading a trajectory."""
        if self._loading_trajectory:
            # Skip clearing during initial load
            return

        self._step_history = []
        self._step_widgets = {}
        self._clear_step_log()

        if self._current_traj:
            # Re-load all steps
            if self._current_plugin:
                self._current_plugin.on_reset()
            self._load_all_steps(self._current_traj)

            date_str = self._current_traj.created_at.strftime("%Y-%m-%d %H:%M")
            self.query_one("#header-info", Static).update(
                f"{date_str}  1/{len(self._current_traj.steps)}"
            )
            self._update_timeline(0, len(self._current_traj.steps))
            self._highlight_step(0)

        self._update_play_button(False)

    def on_playback_complete(self, event: PlaybackComplete) -> None:
        """Handle playback end."""
        self._update_play_button(False)

        if self._current_traj:
            total = len(self._current_traj.steps)
            self._update_timeline(total - 1, total)

        # Loop with a small delay so user sees completed state
        if self.loop_enabled and self._player:
            self.set_timer(1.0, self._loop_restart)

    def _loop_restart(self) -> None:
        """Restart playback after loop delay."""
        if self.loop_enabled and self._player:
            self._player.reset()
            self._player.play()
            self._update_play_button(True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks - single step only."""
        btn = event.button.id
        if btn == "btn-play":
            self.action_toggle_play()
        elif btn == "btn-prev":
            self.action_step_back()
        elif btn == "btn-next":
            self.action_step_forward()
        elif btn == "btn-start":
            self.action_go_to_start()
        elif btn == "btn-end":
            self.action_go_to_end()
        elif btn == "btn-loop":
            self.action_toggle_loop()
        elif btn == "btn-slower":
            self.action_speed_down()
        elif btn == "btn-faster":
            self.action_speed_up()
        # Remove focus from button to prevent highlight rectangle
        self.set_focus(None)

    def on_repeat_button_repeated(self, event: RepeatButton.Repeated) -> None:
        """Handle held button repeats for prev/next."""
        btn_id = event.button.id
        if btn_id == "btn-prev":
            self.action_step_back()
        elif btn_id == "btn-next":
            self.action_step_forward()

    def _update_play_button(self, playing: bool) -> None:
        """Update play button and animation state."""
        btn = self.query_one("#btn-play", VCRButton)
        btn.label = "⏸" if playing else "▶"
        if playing:
            btn.add_class("playing")
        else:
            btn.remove_class("playing")
        # Sync visualization with playback state
        if self._current_plugin:
            self._current_plugin.set_playing(playing)

    def watch_current_speed(self, speed: float) -> None:
        """Update speed display."""
        if self._player:
            self._player.speed = speed
        with contextlib.suppress(NoMatches):
            self.query_one("#speed-display", Static).update(f"{speed:.1f}x")

    def watch_loop_enabled(self, enabled: bool) -> None:
        """Update loop button."""
        try:
            btn = self.query_one("#btn-loop", VCRButton)
            if enabled:
                btn.add_class("loop-active")
            else:
                btn.remove_class("loop-active")
        except Exception:
            pass

    def watch_chart_height(self, height: int) -> None:
        """Update chart height."""
        try:
            anim_area = self.query_one("#animation-area")
            anim_area.styles.height = height
        except Exception:
            pass

    # Actions

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_toggle_play(self) -> None:
        if self._player:
            self._player.toggle()
            self._update_play_button(self._player.playing)

    def action_reset(self) -> None:
        if self._player:
            self._player.reset()
            self._update_play_button(False)

    def action_step_forward(self) -> None:
        if self._player:
            self._player.step_forward()

    def action_step_back(self) -> None:
        if self._player:
            self._player.step_backward()

    def action_speed_up(self) -> None:
        speeds = [0.5, 1.0, 2.0, 4.0, 8.0]
        try:
            idx = speeds.index(self.current_speed)
            if idx < len(speeds) - 1:
                self.current_speed = speeds[idx + 1]
        except ValueError:
            self.current_speed = 1.0

    def action_speed_down(self) -> None:
        speeds = [0.5, 1.0, 2.0, 4.0, 8.0]
        try:
            idx = speeds.index(self.current_speed)
            if idx > 0:
                self.current_speed = speeds[idx - 1]
        except ValueError:
            self.current_speed = 1.0

    def action_toggle_loop(self) -> None:
        self.loop_enabled = not self.loop_enabled

    def action_log_up(self) -> None:
        """Move selection up in the step log."""
        if not self._current_traj or not self._step_widgets:
            return
        if self._selected_log_step > 0:
            self._selected_log_step -= 1
            self._select_log_step(self._selected_log_step)

    def action_log_down(self) -> None:
        """Move selection down in the step log."""
        if not self._current_traj or not self._step_widgets:
            return
        total = len(self._current_traj.steps)
        if self._selected_log_step < total - 1:
            self._selected_log_step += 1
            self._select_log_step(self._selected_log_step)

    def _select_log_step(self, step_index: int) -> None:
        """Select and highlight a step in the log without affecting playback."""
        step_log = self.query_one("#step-log", FocusableStepLog)

        # Remove 'current' class from all entries
        for child in step_log.children:
            if hasattr(child, "remove_class"):
                child.remove_class("current")

        # Highlight and scroll to the target entry
        if step_index in self._step_widgets:
            entry = self._step_widgets[step_index]
            entry.add_class("current")
            entry.scroll_visible(animate=False)

        # Update the animation canvas to show this point
        self.query_one("#animation", AnimationCanvas).set_current_index(step_index)

        # Update header info
        if self._current_traj:
            total = len(self._current_traj.steps)
            date_str = self._current_traj.created_at.strftime("%Y-%m-%d %H:%M")
            self.query_one("#header-info", Static).update(
                f"{date_str}  {step_index + 1}/{total}"
            )
            self._update_timeline(step_index, total)

    def action_go_to_start(self) -> None:
        """Go to the first step."""
        if self._player:
            self._player.reset()
            self._update_play_button(False)

    def action_go_to_end(self) -> None:
        """Go to the last step."""
        if self._player and self._current_traj:
            total = len(self._current_traj.steps)
            if total > 0:
                self.seek_to_step(total - 1)

    def action_cursor_down(self) -> None:
        """Move to next trajectory."""
        if not self._trajectories or not self._selected_traj_id:
            return
        for i, traj in enumerate(self._trajectories):
            if traj.id == self._selected_traj_id:
                if i < len(self._trajectories) - 1:
                    self._select_trajectory(self._trajectories[i + 1])
                break

    def action_cursor_up(self) -> None:
        """Move to previous trajectory."""
        if not self._trajectories or not self._selected_traj_id:
            return
        for i, traj in enumerate(self._trajectories):
            if traj.id == self._selected_traj_id:
                if i > 0:
                    self._select_trajectory(self._trajectories[i - 1])
                break

    def action_grow_chart(self) -> None:
        """Increase chart height."""
        self.chart_height = min(30, self.chart_height + 2)

    def action_shrink_chart(self) -> None:
        """Decrease chart height."""
        self.chart_height = max(6, self.chart_height - 2)

    def seek_to_step(self, step_index: int) -> None:
        """Seek to a specific step."""
        if (
            self._player
            and self._current_traj
            and 0 <= step_index < len(self._current_traj.steps)
        ):
            self._player.seek(step_index)
