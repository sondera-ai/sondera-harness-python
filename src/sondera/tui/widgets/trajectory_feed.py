"""Trajectory feed widget: selectable trajectory rows with inline violation expand."""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import ScrollableContainer
from textual.events import Click
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from sondera.tui.colors import SPINNER_CHARS, SPINNER_INTERVAL, get_theme_colors
from sondera.tui.events import EventStep, correlate_events, parse_ts
from sondera.tui.util import _utc_seconds_ago
from sondera.types import Decision, Trajectory

from .pagination_bar import PaginationBar


def _step_content_type(s: EventStep) -> str:
    return s.content_type


def _step_tool_id(s: EventStep) -> str:
    return s.tool_id


def _step_text(s: EventStep) -> str:
    return s.text


def _iter_step_groups(steps: list[EventStep]) -> Iterator[list[int]]:
    """Yield groups of step indices, merging duplicates and request+response pairs.

    Must match the grouping in screens/trajectory.py::_build_step_groups so
    counts shown here agree with the trajectory detail screen.
    """
    seen: set[int] = set()
    i = 0
    n = len(steps)
    while i < n:
        if i in seen:
            i += 1
            continue

        ct = _step_content_type(steps[i])
        group = [i]

        if ct == "prompt":
            text = _step_text(steps[i])
            j = i + 1
            while (
                j < n
                and _step_content_type(steps[j]) == "prompt"
                and _step_text(steps[j]) == text
            ):
                group.append(j)
                seen.add(j)
                j += 1
        elif ct == "tool_request":
            tool_id = _step_tool_id(steps[i])
            j = i + 1
            while j < n:
                if j in seen:
                    j += 1
                    continue
                jct = _step_content_type(steps[j])
                jtid = _step_tool_id(steps[j])
                if jct == "tool_request" and jtid == tool_id:
                    group.append(j)
                    seen.add(j)
                    j += 1
                elif jct == "tool_response" and jtid == tool_id:
                    group.append(j)
                    seen.add(j)
                    k = j + 1
                    while k < n:
                        if (
                            _step_content_type(steps[k]) == "tool_response"
                            and _step_tool_id(steps[k]) == tool_id
                        ):
                            group.append(k)
                            seen.add(k)
                            k += 1
                        else:
                            break
                    break
                else:
                    j += 1
        elif ct == "tool_response":
            tool_id = _step_tool_id(steps[i])
            j = i + 1
            while (
                j < n
                and _step_content_type(steps[j]) == "tool_response"
                and _step_tool_id(steps[j]) == tool_id
            ):
                group.append(j)
                seen.add(j)
                j += 1

        yield group
        i += 1


def _count_grouped_steps(steps: list[EventStep]) -> int:
    """Count agent-loop turns: skip duplicates, merge request+response pairs."""
    return sum(1 for _ in _iter_step_groups(steps))


_STATUS_ICONS: dict[str, str] = {
    "running": "\u25cf ",
    "pending": "\u25cf ",
    "completed": "\u2713 ",
    "suspended": "\u25cb ",
    "failed": "\u2717 ",
    "unknown": "? ",
}

# Normalize backend status labels for display
_STATUS_LABELS: dict[str, str] = {
    "running": "running",
    "pending": "running",
    "completed": "completed",
    "suspended": "suspended",
    "failed": "failed",
    "unknown": "unknown",
}

# 1 hour: RUNNING/PENDING trajectories older than this are stale (session didn't finalize)
_STALE_THRESHOLD_SECONDS = 3600


def _is_stale(trajectory: Trajectory) -> bool:
    """Return True if a RUNNING/PENDING trajectory hasn't been updated recently.

    Falls back to the best available metadata timestamp.
    """
    status = str(trajectory.status or "unknown").lower()
    if status not in {"running", "pending"}:
        return False
    # Use best available metadata timestamp
    last = max(parse_ts(trajectory.update_time), parse_ts(trajectory.create_time))
    if last.tzinfo is None:
        last = last.astimezone(UTC)
    now = datetime.now(tz=UTC)
    return (now - last).total_seconds() > _STALE_THRESHOLD_SECONDS


def _relative_time(
    dt: datetime | str, primary: str, fg: str, fg_secondary: str, fg_dim: str
) -> tuple[str, str]:
    """Format a datetime as a relative time string with theme-aware color."""
    if isinstance(dt, str):
        dt = parse_ts(dt)
    seconds = _utc_seconds_ago(dt)
    if seconds < 5:
        label = "just now"
    elif seconds < 60:
        label = f"{seconds}s ago"
    elif seconds < 3600:
        label = f"{seconds // 60}m ago"
    elif seconds < 86400:
        label = f"{seconds // 3600}h ago"
    elif seconds < 172800:
        label = "yesterday"
    else:
        label = f"{seconds // 86400}d ago"

    if seconds < 300:
        color = primary
    elif seconds < 3600:
        color = fg
    elif seconds < 86400:
        color = fg_secondary
    else:
        color = fg_dim

    return label, color


def _uptime_label(created_at: datetime | str) -> str:
    """Format a duration since created_at as a compact uptime string."""
    if isinstance(created_at, str):
        created_at = parse_ts(created_at)
    if created_at.tzinfo is None:
        created_at = created_at.astimezone(UTC)
    now = datetime.now(tz=UTC)
    seconds = int((now - created_at).total_seconds())
    if seconds < 60:
        return f"\u2191{seconds}s"
    if seconds < 3600:
        return f"\u2191{seconds // 60}m"
    if seconds < 86400:
        return f"\u2191{seconds // 3600}h{(seconds % 3600) // 60}m"
    return f"\u2191{seconds // 86400}d"


def _last_active_dt(trajectory: Trajectory) -> datetime:
    """Return the best available 'last active' datetime."""
    return parse_ts(trajectory.update_time)


def _worst_decision(a: Decision, b: Decision) -> Decision:
    """DENY > ESCALATE > ALLOW."""
    if a == Decision.Deny or b == Decision.Deny:
        return Decision.Deny
    if a == Decision.Escalate or b == Decision.Escalate:
        return Decision.Escalate
    return Decision.Allow


def _get_event_steps(trajectory: Trajectory) -> list[EventStep]:
    """Get correlated EventSteps from a trajectory's events."""
    if not trajectory.events:
        return []
    return correlate_events(trajectory.events)


def _count_violations(
    trajectory: Trajectory, steps: list[EventStep] | None = None
) -> tuple[int, int]:
    """Count denied and escalated *grouped* steps. Returns (denied, escalated)."""
    if steps is None:
        steps = _get_event_steps(trajectory)
    if not steps:
        return 0, 0

    denied = 0
    escalated = 0
    for indices in _iter_step_groups(steps):
        group_decision = Decision.Allow
        for idx in indices:
            group_decision = _worst_decision(group_decision, steps[idx].decision)
        if group_decision == Decision.Deny:
            denied += 1
        elif group_decision == Decision.Escalate:
            escalated += 1
    return denied, escalated


_MCP_PREFIX_RE = re.compile(r"^mcp__(?:plugin_)?(\w+?)_(\w+?)__(\w+)$")


def _clean_tool_name(tool_id: str) -> str:
    """Shorten MCP tool IDs: mcp__plugin_linear_linear__create_issue -> linear: create_issue."""
    m = _MCP_PREFIX_RE.match(tool_id)
    if m:
        return f"{m.group(1)}: {m.group(3)}"
    return tool_id


def _format_step_snippet(step: EventStep, max_len: int) -> str:
    """Format a step's content as a short snippet string.

    Prefers Scanned description for tool requests when available, as it
    provides a concise human-readable summary of what the tool is doing.
    """
    ct = step.content_type
    if ct == "tool_request":
        # Prefer Scanned description for richer context
        if step.scan_description:
            desc = step.scan_description.strip().replace("\n", " ")
            return desc[:max_len]
        args = step.args
        args_str = ""
        if args:
            first_key = next(iter(args))
            first_val = str(args[first_key]).strip().replace("\n", " ")
            if len(first_val) > 25:
                first_val = first_val[:22] + "..."
            args_str = f'("{first_val}")'
        tool_name = _clean_tool_name(step.tool_id)
        snippet = f"{tool_name}{args_str}"
        return snippet[:max_len]
    text = step.text.strip().replace("\n", " ")
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _activity_snippet(
    trajectory: Trajectory,
    max_len: int = 40,
    steps: list[EventStep] | None = None,
) -> str | None:
    """Get a short snippet of the most recent activity (last meaningful step)."""
    if steps is None:
        steps = _get_event_steps(trajectory)
    if not steps:
        return None

    # Priority: show denied step content if any violations exist
    for step in reversed(steps):
        if step.decision == Decision.Deny:
            ct = step.content_type
            if ct in ("tool_request", "prompt"):
                return _format_step_snippet(step, max_len)

    # Fallback: last tool request or prompt
    for step in reversed(steps):
        ct = step.content_type
        if ct == "tool_request":
            return _format_step_snippet(step, max_len)
        if ct == "tool_response":
            continue
        if ct == "prompt":
            return _format_step_snippet(step, max_len)
    return None


def _trajectory_label(
    trajectory: Trajectory,
    max_len: int = 18,
    steps: list[EventStep] | None = None,
) -> str:
    """Derive a short label from the first user prompt or tool call."""
    if steps is None:
        steps = _get_event_steps(trajectory)
    tid = trajectory.name
    if steps:
        # Priority 1: first user prompt
        for step in steps:
            if step.content_type == "prompt" and step.text.strip():
                label = step.text.strip().replace("\n", " ")
                if len(label) > max_len:
                    return label[: max_len - 1] + "\u2026"
                return label
        # Priority 2: first tool call
        for step in steps:
            if step.content_type == "tool_request":
                tool_name = _clean_tool_name(step.tool_id)
                args = step.args
                if args:
                    first_val = str(next(iter(args.values())))
                    first_val = first_val.strip().replace("\n", " ")
                    if len(first_val) > 15:
                        first_val = first_val[:12] + "\u2026"
                    label = f"{tool_name} {first_val}"
                else:
                    label = tool_name
                if len(label) > max_len:
                    return label[: max_len - 1] + "\u2026"
                return label
        # Has steps but no prompt or tool call
        return tid[:8]
    # Not yet enriched: show short ID so instances are distinguishable
    return tid[:8]


class TrajectoryFeed(Widget):
    """Trajectory feed with cursor navigation and inline violation expand."""

    can_focus = True

    DEFAULT_CSS = """
    TrajectoryFeed {
        height: 1fr;
    }
    TrajectoryFeed #trajectories-header {
        height: 1;
        padding: 0 1;
    }
    TrajectoryFeed #trajectories-container {
        height: 1fr;
        scrollbar-size: 0 0;
    }
    TrajectoryFeed .trajectory-row {
        height: 1;
        padding: 0 1;
    }
    TrajectoryFeed .trajectory-row.--selected {
        background: $primary 12%;
    }
    """

    trajectories: reactive[list[Trajectory]] = reactive(list, always_update=True)
    denied_count: reactive[int] = reactive(0)
    awaiting_count: reactive[int] = reactive(0)
    filter_label: reactive[str] = reactive("")

    class TrajectorySelected(Message):
        """Posted when user presses Enter on a trajectory."""

        def __init__(self, trajectory: Trajectory) -> None:
            self.trajectory = trajectory
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._selected_index: int = 0
        self._row_widgets: list[Static] = []
        self._spinner_frame: int = 0
        self._timer = None
        self._enrichment_attempted: set[str] = (
            set()
        )  # trajectory IDs we tried to enrich

    def compose(self) -> ComposeResult:
        yield Static(id="trajectories-header")
        yield ScrollableContainer(id="trajectories-container")
        yield PaginationBar(id="trajectories-pagination")

    def on_mount(self) -> None:
        self._timer = self.set_interval(SPINNER_INTERVAL, self._tick)

    def _tick(self) -> None:
        """Advance spinner for active trajectory rows."""
        self._spinner_frame += 1
        for i, trajectory in enumerate(self.trajectories):
            if (
                not _is_stale(trajectory)
                and str(trajectory.status or "unknown").lower()
                in {"running", "pending"}
                and i < len(self._row_widgets)
            ):
                is_selected = i == self._selected_index
                row = self._render_row(trajectory, is_selected, self._spinner_frame)
                self._row_widgets[i].update(row)

    def watch_trajectories(self) -> None:
        self._selected_index = 0
        self._rebuild()

    def watch_denied_count(self) -> None:
        self._update_header()

    def watch_awaiting_count(self) -> None:
        self._update_header()

    def watch_filter_label(self) -> None:
        self._update_header()

    def _update_header(self) -> None:
        """Update the header text with count and stats."""
        try:
            header = self.query_one("#trajectories-header", Static)
        except Exception:
            return

        try:
            bar = self.query_one("#trajectories-pagination", PaginationBar)
            total = bar.total_items
        except Exception:
            total = None
        display_count = total if total is not None else len(self.trajectories)

        c = get_theme_colors(self.app)
        header_text = Text()
        header_text.append("TRAJECTORIES", style=f"bold {c.fg}")
        header_text.append(f" ({display_count})", style=c.fg_dim)
        if self.filter_label:
            header_text.append(f"  [{self.filter_label}]", style=f"bold {c.primary}")
        header.update(header_text)

    def _rebuild(self) -> None:
        """Rebuild all trajectory rows."""
        try:
            container = self.query_one("#trajectories-container", ScrollableContainer)
        except Exception:
            return

        self._update_header()
        trajectories = self.trajectories

        # Rebuild rows
        container.remove_children()
        self._row_widgets = []

        if not trajectories:
            c = get_theme_colors(self.app)
            empty = Static(Text("  No trajectories", style=c.fg_dim))
            empty.add_class("trajectory-row")
            container.mount(empty)
            return

        for i, trajectory in enumerate(trajectories):
            is_selected = i == self._selected_index
            row = self._render_row(trajectory, is_selected, self._spinner_frame)
            widget = Static(row)
            widget.add_class("trajectory-row")
            if is_selected:
                widget.add_class("--selected")
            container.mount(widget)
            self._row_widgets.append(widget)

        # Scroll to keep the selected row visible
        if self._row_widgets and 0 <= self._selected_index < len(self._row_widgets):
            self._row_widgets[self._selected_index].scroll_visible()

    def _label_width(self) -> int:
        """Compute label width based on terminal width."""
        try:
            w = self.app.size.width
        except Exception:
            w = 120
        if w >= 180:
            return 40
        if w >= 140:
            return 30
        return 18

    def _status_icon_color(self, status: str) -> tuple[str, str]:
        """Return (icon, color) for a trajectory status using theme colors."""
        c = get_theme_colors(self.app)
        color_map = {
            "running": c.primary,
            "pending": c.primary,
            "completed": c.success,
            "suspended": c.warning,
            "failed": c.error,
            "unknown": c.fg_secondary,
        }
        icon = _STATUS_ICONS.get(status, "? ")
        color = color_map.get(status, c.fg_secondary)
        return icon, color

    def _status_text_color(self, status: str) -> str:
        """Return text color for a trajectory status label."""
        c = get_theme_colors(self.app)
        color_map = {
            "running": c.primary,
            "pending": c.primary,
            "completed": c.fg_dim,
            "suspended": c.warning,
            "failed": c.error,
            "unknown": c.fg_secondary,
        }
        return color_map.get(status, c.fg_secondary)

    def _render_row(
        self,
        trajectory: Trajectory,
        is_selected: bool,
        spinner_frame: int = 0,
    ) -> Text:
        """Render a single trajectory row."""
        c = get_theme_colors(self.app)
        text = Text()
        status = str(trajectory.status or "unknown").lower()
        label_w = self._label_width()

        # Compute correlated steps once for the entire row
        event_steps = _get_event_steps(trajectory)

        # Cursor
        if is_selected:
            text.append("\u25b8 ", style=f"bold {c.primary}")
        else:
            text.append("  ")

        # Detect stale RUNNING/PENDING (session ended without finalizing)
        stale = _is_stale(trajectory)

        # Status icon: animated spinner for running, static icon for others
        is_active = not stale and status in {"running", "pending"}
        if is_active:
            sc = SPINNER_CHARS[spinner_frame % len(SPINNER_CHARS)]
            text.append(f"{sc} ", style=f"bold {c.primary}")
        elif stale:
            text.append("\u2713 ", style=f"bold {c.fg_dim}")
        else:
            icon, icon_color = self._status_icon_color(status)
            text.append(icon, style=f"bold {icon_color}")

        # Trajectory label (first user prompt or short ID)
        label = _trajectory_label(trajectory, max_len=label_w, steps=event_steps)
        tid = trajectory.name
        is_bare_id = len(label) == 8 and label == tid[:8]
        label_style = c.fg_dim if is_bare_id else c.fg
        text.append(label[:label_w].ljust(label_w + 2), style=label_style)

        # Status text
        if stale:
            text.append("timed out".ljust(12), style=c.fg_dim)
        else:
            status_color = self._status_text_color(status)
            status_label = _STATUS_LABELS.get(status, status)
            text.append(status_label.ljust(12), style=status_color)

        # Step count
        if event_steps:
            n = _count_grouped_steps(event_steps)
            step_str = f"{n} step{'s' if n != 1 else ''}".ljust(12)
            step_color = c.fg if n > 0 else c.fg_dim
        elif (
            n := len(trajectory.events)
            if trajectory.events
            else (trajectory.event_count or 0)
        ) > 0:
            step_str = f"{n} step{'s' if n != 1 else ''}".ljust(12)
            step_color = c.fg_secondary
        elif tid in self._enrichment_attempted:
            step_str = "\u2026".ljust(12)
            step_color = c.fg_dim
        else:
            step_str = "- steps".ljust(12)
            step_color = c.fg_dim
        text.append(step_str, style=step_color)

        # Time
        col_w = 20
        if not stale and status in {"running", "pending"}:
            time_label, time_color = _relative_time(
                _last_active_dt(trajectory), c.primary, c.fg, c.fg_secondary, c.fg_dim
            )
            uptime = _uptime_label(parse_ts(trajectory.create_time))
            text.append(time_label, style=time_color)
            rest = f" ({uptime})"
            text.append(rest.ljust(col_w - len(time_label)), style=c.fg_dim)
        else:
            time_label, time_color = _relative_time(
                parse_ts(trajectory.create_time),
                c.primary,
                c.fg,
                c.fg_secondary,
                c.fg_dim,
            )
            text.append(time_label.ljust(col_w), style=time_color)

        # Violation badges
        denied, escalated = _count_violations(trajectory, steps=event_steps)
        if denied > 0:
            text.append(f"\u2717 {denied} denied", style=f"bold {c.error}")
            if escalated > 0:
                text.append("  ")
        if escalated > 0:
            text.append(f"\u26a0 {escalated} awaiting", style=f"bold {c.warning}")

        # Activity snippet
        snippet = _activity_snippet(trajectory, steps=event_steps)
        if snippet and denied == 0 and escalated == 0:
            text.append(snippet, style=c.fg_secondary)
        elif snippet:
            text.append("  ")
            text.append(snippet, style=c.fg_secondary)

        return text

    def mark_enrichment_failed(self, index: int) -> None:
        """Mark a trajectory whose enrichment returned no data."""
        if index >= len(self.trajectories):
            return
        self._enrichment_attempted.add(self.trajectories[index].name)
        # Re-render the row to show "0 steps" instead of "- steps"
        if index < len(self._row_widgets):
            is_selected = index == self._selected_index
            row = self._render_row(
                self.trajectories[index], is_selected, self._spinner_frame
            )
            self._row_widgets[index].update(row)

    def update_enrichment(self, index: int, trajectory: Trajectory) -> None:
        """Update a single row after enrichment without full rebuild."""
        if index >= len(self.trajectories):
            return

        self._enrichment_attempted.add(trajectory.name)

        # Mutate the list in place
        traj_list = self.trajectories
        traj_list[index] = trajectory

        # Update the row widget directly if it exists
        if index < len(self._row_widgets):
            is_selected = index == self._selected_index
            row = self._render_row(trajectory, is_selected, self._spinner_frame)
            self._row_widgets[index].update(row)

    def update_pagination(self, next_token: str, page_count: int = 0) -> None:
        """Update the pagination bar state."""
        try:
            bar = self.query_one("#trajectories-pagination", PaginationBar)
            bar.update_state(next_token, page_count=page_count)
        except Exception:
            pass

    def get_selected_trajectory(self) -> Trajectory | None:
        """Get the currently selected trajectory."""
        if self.trajectories and 0 <= self._selected_index < len(self.trajectories):
            return self.trajectories[self._selected_index]
        return None

    def on_click(self, event: Click) -> None:
        """Handle mouse click: first click selects, second click opens."""
        for i, widget in enumerate(self._row_widgets):
            if event.widget is widget:
                if i == self._selected_index:
                    # Already selected: open it
                    self.action_select()
                else:
                    # Select this row
                    self._selected_index = i
                    self._rebuild()
                self.focus()
                event.stop()
                return

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        if self.trajectories and self._selected_index < len(self.trajectories) - 1:
            self._selected_index += 1
            self._rebuild()

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        if self._selected_index > 0:
            self._selected_index -= 1
            self._rebuild()

    def action_select(self) -> None:
        """Select the current trajectory."""
        if self.trajectories and 0 <= self._selected_index < len(self.trajectories):
            self.post_message(
                self.TrajectorySelected(self.trajectories[self._selected_index])
            )
