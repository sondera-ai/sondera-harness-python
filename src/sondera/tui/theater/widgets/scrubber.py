"""Scrubber timeline widget for trajectory playback."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import RenderableType
from rich.style import Style
from rich.text import Text
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget

if TYPE_CHECKING:
    from sondera.types import AdjudicatedStep, Decision, Role

# Color constants for decisions
COLOR_ALLOW = "#81DDB4"  # Electric Green
COLOR_DENY = "#BF616A"  # Red
COLOR_ESCALATE = "#EBCB8B"  # Yellow

# Role colors
COLOR_USER = "#7aa2f7"  # Blue
COLOR_MODEL = "#bb9af7"  # Purple
COLOR_TOOL = "#7dcfff"  # Cyan

# UI colors - will be selected based on theme in render()
# Dark theme colors
COLOR_DIM_DARK = "#666666"
COLOR_HIGHLIGHT_DARK = "#e0e0e0"
COLOR_BAR_DARK = "#444444"

# Light theme colors
COLOR_DIM_LIGHT = "#999999"
COLOR_HIGHLIGHT_LIGHT = "#333333"
COLOR_BAR_LIGHT = "#cccccc"


class ScrubberTimeline(Widget):
    """A visual timeline with draggable/clickable progress for trajectory playback.

    Displays:
    - A progress bar with a handle showing current position
    - Step numbers below
    - Role indicators (U/M/T) with decision color coding
    """

    DEFAULT_CSS = """
    ScrubberTimeline {
        width: 100%;
        height: 4;
        padding: 0 1;
    }
    """

    class Seek(Message):
        """Message emitted when user seeks to a step."""

        def __init__(self, step: int) -> None:
            super().__init__()
            self.step = step

    current_step: reactive[int] = reactive(0)
    """Current step index."""

    total_steps: reactive[int] = reactive(0)
    """Total number of steps."""

    def __init__(
        self,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._steps: list[AdjudicatedStep] = []

    def set_steps(self, steps: list[AdjudicatedStep]) -> None:
        """Set the trajectory steps for display."""
        self._steps = steps
        self.total_steps = len(steps)
        self.current_step = 0
        self.refresh()

    def clear(self) -> None:
        """Clear the scrubber."""
        self._steps = []
        self.total_steps = 0
        self.current_step = 0
        self.refresh()

    def _get_decision_color(self, decision: Decision) -> str:
        """Get color for a decision."""
        from sondera.types import Decision

        if decision == Decision.DENY:
            return COLOR_DENY
        elif decision == Decision.ESCALATE:
            return COLOR_ESCALATE
        return COLOR_ALLOW

    def _get_role_char(self, role: Role) -> str:
        """Get character for a role."""
        from sondera.types import Role

        return {
            Role.USER: "U",
            Role.MODEL: "M",
            Role.TOOL: "T",
            Role.SYSTEM: "S",
        }.get(role, "?")

    def _get_role_color(self, role: Role) -> str:
        """Get color for a role."""
        from sondera.types import Role

        return {
            Role.USER: COLOR_USER,
            Role.MODEL: COLOR_MODEL,
            Role.TOOL: COLOR_TOOL,
            Role.SYSTEM: COLOR_ALLOW,
        }.get(role, COLOR_ALLOW)

    def render(self) -> RenderableType:
        """Render the scrubber timeline."""
        # Detect theme and select colors
        is_dark = self.app.current_theme.dark if self.app else True
        if is_dark:
            color_dim = COLOR_DIM_DARK
            color_highlight = COLOR_HIGHLIGHT_DARK
            color_bar = COLOR_BAR_DARK
        else:
            color_dim = COLOR_DIM_LIGHT
            color_highlight = COLOR_HIGHLIGHT_LIGHT
            color_bar = COLOR_BAR_LIGHT

        if self.total_steps == 0:
            return Text("No trajectory loaded", style=Style(color=color_dim))

        # Get available width (accounting for padding)
        width = self.size.width - 2
        if width < 10:
            width = 60

        lines = []

        # Line 1: Progress bar
        # ◀────────────●───────────────────────────────────▶
        bar_width = width - 2  # Account for arrows

        if self.total_steps > 1:
            progress = self.current_step / (self.total_steps - 1)
        else:
            progress = 0.0

        handle_pos = int(progress * (bar_width - 1))

        bar_line = Text()
        bar_line.append("◀", style=Style(color=color_dim))

        for i in range(bar_width):
            if i == handle_pos:
                bar_line.append("●", style=Style(color=color_highlight, bold=True))
            elif i < handle_pos:
                bar_line.append(
                    "─", style=Style(color=color_highlight)
                )  # Filled portion
            else:
                bar_line.append("─", style=Style(color=color_bar))  # Unfilled portion

        bar_line.append("▶", style=Style(color=color_dim))
        lines.append(bar_line)

        # Line 2: Step numbers (show subset if too many)
        # Calculate how many steps we can show
        steps_to_show = min(self.total_steps, (width - 4) // 4)  # ~4 chars per step

        if steps_to_show < self.total_steps:
            # Show sampled steps
            step_indices = self._sample_indices(self.total_steps, steps_to_show)
        else:
            step_indices = list(range(self.total_steps))

        # Build number line
        num_line = Text()
        num_line.append("  ")  # Indent to align with bar

        for step_idx in step_indices:
            step_num = str(step_idx + 1)
            # Highlight current step
            if step_idx == self.current_step:
                style = Style(color=color_highlight, bold=True)
            else:
                style = Style(color=color_dim)

            num_line.append(step_num.center(4), style=style)

        lines.append(num_line)

        # Line 3: Role indicators with decision colors
        role_line = Text()
        role_line.append("  ")  # Indent

        for step_idx in step_indices:
            step = self._steps[step_idx]
            role_char = self._get_role_char(step.step.role)
            decision_color = self._get_decision_color(step.adjudication.decision)

            # Highlight current step
            if step_idx == self.current_step:
                style = Style(color=decision_color, bold=True)
            else:
                style = Style(color=decision_color, dim=True)

            role_line.append(role_char.center(4), style=style)

        lines.append(role_line)

        return Text("\n").join(lines)

    def _sample_indices(self, total: int, count: int) -> list[int]:
        """Sample indices evenly distributed across total range."""
        if count >= total:
            return list(range(total))

        # Always include first, last, and current
        indices = {0, total - 1, self.current_step}

        # Fill in remaining evenly
        remaining = count - len(indices)
        if remaining > 0:
            step_size = total / (remaining + 1)
            for i in range(1, remaining + 1):
                indices.add(int(i * step_size))

        return sorted(indices)[:count]

    def on_click(self, event) -> None:
        """Handle click to seek to position."""
        if self.total_steps == 0:
            return

        # Calculate which step was clicked
        # The bar starts at x=1 (after left arrow)
        bar_width = self.size.width - 4  # Remove padding and arrows
        click_x = event.x - 2  # Adjust for padding and arrow

        if click_x < 0:
            click_x = 0
        if click_x >= bar_width:
            click_x = bar_width - 1

        # Convert x position to step
        if bar_width > 1:
            step = int((click_x / (bar_width - 1)) * (self.total_steps - 1))
        else:
            step = 0

        step = max(0, min(step, self.total_steps - 1))

        # Emit seek message
        self.post_message(self.Seek(step))
