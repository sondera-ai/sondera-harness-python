"""Animation canvas widget - EKG-style decision plot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rich.console import RenderableType
from rich.style import Style
from rich.text import Text
from textual.events import Click
from textual.message import Message
from textual.widget import Widget

if TYPE_CHECKING:
    from sondera.tui.theater.events import StepEvent

# Decision colors - brighter for better visibility
COLOR_ALLOW = (129, 221, 180)  # Electric Green #81DDB4
COLOR_DENY = (220, 100, 110)  # Brighter Red
COLOR_ESCALATE = (245, 215, 130)  # Brighter Yellow

# Simple dots - clean and readable
# Color indicates decision (green/red/yellow), role is in the log
ICON_MODEL = "●"
ICON_USER = "●"
ICON_TOOL = "●"

# Current step - slightly larger dot
ICON_MODEL_CURRENT = "◉"
ICON_USER_CURRENT = "◉"
ICON_TOOL_CURRENT = "◉"


@dataclass
class PlotPoint:
    """A point on the EKG plot."""

    decision: int  # 0=ALLOW, 1=DENY, 2=ESCALATE
    role: int  # 0=MODEL, 1=USER, 2=TOOL


class AnimationCanvas(Widget):
    """EKG-style decision visualization - compact 3-row design.

    Shows a scrolling plot where each step appears as a point:
    - Row 0: ALLOW (green)
    - Row 1: DENY (red)
    - Row 2: ESCALATE (yellow)

    Points are connected with lines. Supports rewinding (only shows
    points up to current position). Click on a dot to navigate to that step.
    """

    can_focus = False

    class DotClicked(Message):
        """Sent when a dot is clicked."""

        def __init__(self, step_index: int) -> None:
            super().__init__()
            self.step_index = step_index

    DEFAULT_CSS = """
    AnimationCanvas {
        width: 100%;
        height: 100%;
        background: transparent;
    }
    """

    def __init__(
        self,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._width = 80
        self._height = 3  # Compact: just 3 rows
        self._points: list[PlotPoint] = []
        self._playing = False
        self._current_index: int = -1  # Current playback position (-1 = none)

    def on_mount(self) -> None:
        """Start refresh loop."""
        self.set_interval(0.1, self._tick)

    def on_resize(self, event) -> None:
        """Handle resize."""
        self._width = max(30, self.size.width - 16)  # Room for labels
        self._height = max(3, self.size.height)  # Minimum 3 rows, expands with space

    def _tick(self) -> None:
        """Refresh the display."""
        if self._points and self._current_index >= 0:
            self.refresh()

    def _get_row_for_decision(self, decision: int) -> int:
        """Map decision to row. Distributes 3 levels evenly across height."""
        # decision: 0=ALLOW (top), 1=DENY (middle), 2=ESCALATE (bottom)
        if self._height <= 4:
            # Small canvas: use compact rows 0, 1, 2 (or adjusted for height)
            return min(decision, self._height - 1)

        # For larger canvases, add padding at bottom for visual balance
        # ESCALATE moves up 1 row from the very bottom
        allow_row = 0
        escalate_row = self._height - 2  # Not at very bottom - gives breathing room

        if decision == 0:  # ALLOW - top
            return allow_row
        elif decision == 1:  # DENY - exact midpoint between ALLOW and ESCALATE
            return (allow_row + escalate_row) // 2
        else:  # ESCALATE - near bottom with padding
            return escalate_row

    def _get_color_for_decision(self, decision: int) -> tuple[int, int, int]:
        """Get color for a decision."""
        if decision == 0:
            return COLOR_ALLOW
        elif decision == 1:
            return COLOR_DENY
        else:
            return COLOR_ESCALATE

    def _count_decisions(self, up_to_index: int) -> tuple[int, int, int]:
        """Count decisions up to (and including) the given index."""
        allow = deny = escalate = 0
        for i in range(min(up_to_index + 1, len(self._points))):
            d = self._points[i].decision
            if d == 0:
                allow += 1
            elif d == 1:
                deny += 1
            else:
                escalate += 1
        return allow, deny, escalate

    def render(self) -> RenderableType:
        """Render the EKG-style plot."""
        lines = []

        # Get row positions (compact)
        allow_row = self._get_row_for_decision(0)
        deny_row = self._get_row_for_decision(1)
        escalate_row = self._get_row_for_decision(2)

        # Build a 2D grid for the plot area
        grid = [[" " for _ in range(self._width)] for _ in range(self._height)]
        grid_colors = [
            [(50, 50, 50) for _ in range(self._width)] for _ in range(self._height)
        ]

        # Draw baseline for each level (subtle dotted line)
        for x in range(self._width):
            grid[allow_row][x] = "·"
            grid_colors[allow_row][x] = (35, 60, 50)
            grid[deny_row][x] = "·"
            grid_colors[deny_row][x] = (60, 35, 40)
            grid[escalate_row][x] = "·"
            grid_colors[escalate_row][x] = (65, 55, 35)

        # Only show points up to current_index (for rewind support)
        visible_count = self._current_index + 1 if self._current_index >= 0 else 0
        points_to_show = self._points[:visible_count]
        num_visible = len(points_to_show)

        # Count decisions for visible points only
        allow_count, deny_count, escalate_count = self._count_decisions(
            self._current_index
        )

        # Plot visible points from left to right (step 1 on left, scrolls right)
        # Calculate scroll offset: once we have more points than width, scroll
        scroll_offset = max(0, num_visible - self._width)

        for i in range(num_visible):
            x = i - scroll_offset  # Position minus scroll offset
            if x < 0 or x >= self._width:
                continue

            point = points_to_show[i]
            row = self._get_row_for_decision(point.decision)
            color = self._get_color_for_decision(point.decision)
            is_current = i == num_visible - 1  # Most recent visible point

            # Get shape based on role
            role = point.role
            if is_current:
                # Use emphasized shapes for current point
                if role == 0:  # MODEL
                    shape = ICON_MODEL_CURRENT
                elif role == 1:  # USER
                    shape = ICON_USER_CURRENT
                else:  # TOOL
                    shape = ICON_TOOL_CURRENT
                # Brighten current point
                color = (
                    min(255, color[0] + 40),
                    min(255, color[1] + 40),
                    min(255, color[2] + 40),
                )
            else:
                # Use normal shapes
                if role == 0:  # MODEL
                    shape = ICON_MODEL
                elif role == 1:  # USER
                    shape = ICON_USER
                else:  # TOOL
                    shape = ICON_TOOL

            grid[row][x] = shape
            grid_colors[row][x] = color

            # Draw connecting line to previous point
            if i > 0:
                prev_point = points_to_show[i - 1]
                prev_x = x - 1
                if prev_x >= 0:
                    prev_row = self._get_row_for_decision(prev_point.decision)
                    line_color = (color[0] // 2, color[1] // 2, color[2] // 2)

                    # All dot shapes that shouldn't be overwritten
                    dot_shapes = {
                        ICON_MODEL,
                        ICON_USER,
                        ICON_TOOL,
                        ICON_MODEL_CURRENT,
                        ICON_USER_CURRENT,
                        ICON_TOOL_CURRENT,
                    }

                    if row != prev_row:
                        # Vertical connection
                        min_row = min(row, prev_row)
                        max_row = max(row, prev_row)

                        for r in range(min_row + 1, max_row):
                            grid[r][prev_x] = "│"
                            grid_colors[r][prev_x] = line_color

                        # Corner pieces
                        if row > prev_row:
                            if grid[prev_row][prev_x] not in dot_shapes:
                                grid[prev_row][prev_x] = "╮"
                                grid_colors[prev_row][prev_x] = line_color
                            grid[row][prev_x] = "╰"
                            grid_colors[row][prev_x] = line_color
                        else:
                            if grid[prev_row][prev_x] not in dot_shapes:
                                grid[prev_row][prev_x] = "╯"
                                grid_colors[prev_row][prev_x] = line_color
                            grid[row][prev_x] = "╭"
                            grid_colors[row][prev_x] = line_color
                    else:
                        # Horizontal line on same row
                        if grid[row][prev_x] not in dot_shapes:
                            grid[row][prev_x] = "─"
                            grid_colors[row][prev_x] = line_color

        # Build output lines with labels
        for y in range(self._height):
            line = Text()

            # Add label with count (only for the 3 decision rows)
            if y == allow_row:
                label = f"ALLOW {allow_count:3d}"
                line.append(f"{label:>12} ", Style(color="rgb(129,221,180)", bold=True))
            elif y == deny_row:
                label = f"DENY {deny_count:3d}"
                line.append(f"{label:>12} ", Style(color="rgb(220,100,110)", bold=True))
            elif y == escalate_row:
                label = f"ESCALATE {escalate_count:3d}"
                line.append(f"{label:>12} ", Style(color="rgb(245,215,130)", bold=True))
            else:
                line.append(" " * 13)

            # Add separator
            line.append("│", Style(color="rgb(60,60,60)"))

            # Add plot content
            for x in range(self._width):
                char = grid[y][x]
                r, g, b = grid_colors[y][x]
                style = Style(color=f"rgb({r},{g},{b})")
                line.append(char, style)

            lines.append(line)

        return Text("\n").join(lines)

    def set_playing(self, playing: bool) -> None:
        """Set whether the animation should be active."""
        self._playing = playing

    def on_step(self, event: StepEvent) -> None:
        """Add a point for this step."""
        from sondera.types import Decision

        if event.decision == Decision.Allow:
            decision = 0
        elif event.decision == Decision.Deny:
            decision = 1
        else:  # Escalate
            decision = 2

        if event.role == "model":
            role = 0
        elif event.role == "user":
            role = 1
        else:  # tool (or system, treat as tool)
            role = 2

        self._points.append(PlotPoint(decision=decision, role=role))
        self._current_index = len(self._points) - 1  # Point to the new point
        self.refresh()

    def set_current_index(self, index: int) -> None:
        """Set which point is current (for seeking/rewinding)."""
        if 0 <= index < len(self._points):
            self._current_index = index
            self.refresh()

    def reset(self) -> None:
        """Reset animation."""
        self._points.clear()
        self._playing = False
        self._current_index = -1
        self.refresh()

    def on_click(self, event: Click) -> None:
        """Handle click to navigate to a specific step - only visible dots."""
        # Account for label area (13 chars) + separator (1 char)
        label_offset = 14
        x = event.x - label_offset

        if x < 0 or not self._points or self._current_index < 0:
            return

        # Calculate which step was clicked
        visible_count = self._current_index + 1
        scroll_offset = max(0, visible_count - self._width)
        step_index = x + scroll_offset

        # Only allow clicking on dots that have already appeared (up to current_index)
        if 0 <= step_index <= self._current_index:
            self.post_message(self.DotClicked(step_index))

    @property
    def mode_name(self) -> str:
        return "ekg"
