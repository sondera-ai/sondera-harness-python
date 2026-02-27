"""Agents feed widget: severity-colored rows, search filter, expandable details."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import ScrollableContainer
from textual.css.query import NoMatches
from textual.events import Click
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Static

from sondera.tui.colors import SPINNER_CHARS, SPINNER_INTERVAL, get_theme_colors
from sondera.tui.util import relative_time as _relative_time
from sondera.types import Agent


@dataclass
class AgentStatus:
    """Agent with computed dashboard status.

    Attributes:
        status: Derived agent-level status.
            - ``"live"``: has non-stale RUNNING/PENDING trajectories (actively executing)
            - ``"idle"``: has trajectories but none currently active
            - ``"errored"``: has one or more FAILED trajectories
            - ``"off"``: no trajectories at all
    """

    agent: Agent
    status: str = "idle"  # "live" | "idle" | "errored" | "off"
    live_count: int = 0
    total_trajectories: int = 0
    has_more_trajectories: bool = False
    denied_count: int = 0
    denied_trajectory_count: int = 0
    awaiting_count: int = 0
    last_active: datetime | None = None
    # New fields for improvements 7, 8, 20
    completed_count: int = 0
    failed_count: int = 0
    last_trajectory_status: str | None = None  # "completed", "failed", "running"


class AgentsFeed(Widget):
    """Agents section: severity dots, search filter, expandable inline details."""

    can_focus = True

    DEFAULT_CSS = """
    AgentsFeed {
        height: 1fr;
    }
    AgentsFeed #agents-header {
        height: 1;
        padding: 0 1;
    }
    AgentsFeed #agent-filter {
        height: 1;
        padding: 0 1;
        display: none;
        border: none;
        background: $surface;
    }
    AgentsFeed #agent-filter:focus {
        border: none;
    }
    AgentsFeed #agents-container {
        height: 1fr;
        scrollbar-size: 0 0;
    }
    AgentsFeed .agent-row {
        height: 1;
        padding: 0 1;
    }
    AgentsFeed .agent-row.--selected {
        background: $primary 12%;
    }
    AgentsFeed .agent-row.--problematic {
        background: $error 8%;
    }
    AgentsFeed .agent-row.--selected.--problematic {
        background: $error 15%;
    }
    AgentsFeed .agent-detail {
        height: 1;
        padding: 0 1;
        background: $primary 5%;
    }
    """

    agents: reactive[list[AgentStatus]] = reactive(list, always_update=True)

    class AgentSelected(Message):
        """Posted when user presses Enter on an agent."""

        def __init__(self, agent_status: AgentStatus) -> None:
            self.agent_status = agent_status
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._selected_index: int = 0
        self._spinner_frame: int = 0
        self._agent_widgets: list[Static] = []
        self._timer = None
        self._has_focus: bool = False
        self._filter_text: str = ""
        self._filter_visible: bool = False

    @property
    def _filtered_agents(self) -> list[AgentStatus]:
        """Return agents filtered by search text."""
        if not self._filter_text:
            return list(self.agents)
        q = self._filter_text.lower()
        return [
            a
            for a in self.agents
            if q in (a.agent.name or "").lower()
            or q in a.agent.id.lower()
            or q in (a.agent.description or "").lower()
        ]

    def on_focus(self, _event) -> None:
        self._has_focus = True
        self._rebuild()
        # Deactivate sibling feed
        try:
            from sondera.tui.widgets.violations_feed import ViolationsFeed

            sibling = self.screen.query_one(ViolationsFeed)
            if sibling._has_focus:
                sibling._has_focus = False
                sibling._rebuild()
        except (NoMatches, ImportError):
            pass

    def compose(self) -> ComposeResult:
        yield Static(id="agents-header")
        yield Input(
            placeholder="Filter agents... (Esc to close)",
            id="agent-filter",
        )
        container = ScrollableContainer(id="agents-container")
        container.can_focus = False
        yield container

    def on_mount(self) -> None:
        self._timer = self.set_interval(SPINNER_INTERVAL, self._tick)

    def _tick(self) -> None:
        """Advance spinner for live agents."""
        self._spinner_frame += 1

        filtered = self._filtered_agents
        for i, agent_status in enumerate(filtered):
            if agent_status.status == "live" and i < len(self._agent_widgets):
                text = self._render_agent_row(
                    agent_status, i, i == self._selected_index
                )
                self._agent_widgets[i].update(text)

    def watch_agents(
        self, old_agents: list[AgentStatus], new_agents: list[AgentStatus]
    ) -> None:
        # Preserve selection by matching agent ID across refreshes
        if old_agents and 0 <= self._selected_index < len(old_agents):
            prev_id = old_agents[self._selected_index].agent.id
            for i, a in enumerate(new_agents):
                if a.agent.id == prev_id:
                    self._selected_index = i
                    break
            else:
                self._selected_index = 0
        else:
            self._selected_index = 0
        self._rebuild()

    def _rebuild(self) -> None:
        """Rebuild all agent rows."""
        try:
            header = self.query_one("#agents-header", Static)
            container = self.query_one("#agents-container", ScrollableContainer)
        except Exception:
            return

        filtered = self._filtered_agents
        total = len(self.agents)

        # Update header
        c = get_theme_colors(self.app)
        header_text = Text()
        header_text.append("YOUR AGENTS", style=f"bold {c.fg}")
        header_text.append(f" ({total})", style=c.fg_dim)
        if self._filter_text:
            header_text.append(
                f'  showing {len(filtered)} matching "{self._filter_text}"',
                style=c.fg_muted,
            )
        if not self._filter_visible:
            header_text.append("  ", style="")
            header_text.append("[/] filter", style=c.fg_dim)
        header.update(header_text)

        # Rebuild rows
        container.remove_children()
        self._agent_widgets = []

        if not filtered:
            if self._filter_text:
                empty = Static(
                    Text(f'  No agents matching "{self._filter_text}"', style=c.fg_dim)
                )
            else:
                empty = Static(Text("  No agents", style=c.fg_dim))
            empty.add_class("agent-row")
            container.mount(empty)
            return

        for i, agent_status in enumerate(filtered):
            is_selected = i == self._selected_index
            text = self._render_agent_row(agent_status, i, is_selected)
            widget = Static(text)
            widget.add_class("agent-row")
            if is_selected and self._has_focus:
                widget.add_class("--selected")
            # Highlight problematic agents
            if agent_status.denied_count > 0 or agent_status.awaiting_count > 0:
                widget.add_class("--problematic")
            container.mount(widget)
            self._agent_widgets.append(widget)

    @staticmethod
    def _total_label(a: AgentStatus) -> str:
        """Format trajectory total, appending '+' when more pages exist."""
        n = a.total_trajectories
        suffix = "+" if a.has_more_trajectories else ""
        return f"{n}{suffix}"

    def _severity_dot(self, a: AgentStatus) -> tuple[str, str]:
        """Return (icon, color) based on agent health severity."""
        c = get_theme_colors(self.app)
        if a.denied_count > 0:
            return ("\u25cf", c.error)
        if a.awaiting_count > 0:
            return ("\u25cf", c.warning)
        if a.status == "live":
            sc = SPINNER_CHARS[
                (self._spinner_frame + hash(a.agent.id) % 7) % len(SPINNER_CHARS)
            ]
            return (sc, c.primary)
        if a.status == "errored":
            return ("\u2717", c.error)
        if a.status == "off":
            return ("\u25cb", c.border)
        # Idle: checkmark for clean, circle for stale/unknown
        if a.last_trajectory_status in ("completed", None) and a.failed_count == 0:
            return ("\u2713", c.success)
        return ("\u25cb", c.fg_dim)

    def _render_agent_row(self, a: AgentStatus, index: int, is_selected: bool) -> Text:
        """Render a single agent status row."""
        c = get_theme_colors(self.app)
        text = Text()
        name = a.agent.name or a.agent.id[:18]
        name_width = 26
        display_name = (
            name[: name_width - 1] + "\u2026" if len(name) > name_width else name
        )
        is_live = a.status == "live"

        # Cursor indicator (only visible when this feed has focus)
        if is_selected and self._has_focus:
            text.append("\u25b8 ", style=f"bold {c.primary}")
        else:
            text.append("  ")

        # Severity dot
        dot_icon, dot_color = self._severity_dot(a)
        text.append(f"{dot_icon} ", style=f"bold {dot_color}")

        # Agent name
        if is_live:
            text.append(display_name.ljust(name_width), style=f"bold {c.primary}")
        elif a.denied_count > 0:
            text.append(display_name.ljust(name_width), style=f"bold {c.fg}")
        elif a.status == "errored":
            text.append(display_name.ljust(name_width), style=f"bold {c.error}")
        elif a.status == "off":
            text.append(display_name.ljust(name_width), style=c.fg_dim)
        else:
            text.append(display_name.ljust(name_width), style=c.fg)

        # Status label
        if is_live:
            text.append("live".ljust(10), style=c.primary)
        elif a.status == "errored":
            text.append("errored".ljust(10), style=c.error)
        elif a.status == "off":
            text.append("off".ljust(10), style=c.border)
        else:
            text.append("idle".ljust(10), style=c.fg_dim)

        # For live agents, all data columns use green
        data_style = c.primary if is_live else c.fg_muted

        # Last active
        if a.last_active:
            text.append(_relative_time(a.last_active).ljust(10), style=data_style)
        else:
            text.append("".ljust(10))

        # Total run count
        if a.total_trajectories > 0:
            total_label = self._total_label(a)
            run_word = "run" if total_label == "1" else "runs"
            text.append(f"{total_label} {run_word}".ljust(12), style=data_style)
        else:
            text.append("".ljust(12))

        # Last trajectory status
        if a.last_trajectory_status:
            ls = a.last_trajectory_status
            if ls == "failed":
                text.append("last: failed".ljust(18), style=f"bold {c.error}")
            elif ls == "running":
                text.append("last: running".ljust(18), style=c.primary)
            elif ls == "pending":
                if is_live:
                    text.append("last: starting".ljust(18), style=data_style)
                else:
                    text.append("last: pending".ljust(18), style=c.fg_dim)
            elif ls == "completed":
                text.append("last: completed".ljust(18), style=data_style)
            elif ls == "stale":
                text.append("last: timed out".ljust(18), style=c.fg_dim)
            else:
                text.append(f"last: {ls}".ljust(18), style=c.fg_dim)
        else:
            text.append("".ljust(18))

        # Denied badge
        if a.denied_count > 0:
            runs = a.denied_trajectory_count
            run_label = f" in {runs} run{'s' if runs != 1 else ''}" if runs > 0 else ""
            text.append(
                f"\u2717 {a.denied_count} denied{run_label}  ",
                style=f"bold {c.error}",
            )

        # Awaiting badge
        if a.awaiting_count > 0:
            text.append(
                f"\u26a0 {a.awaiting_count} awaiting", style=f"bold {c.warning}"
            )

        return text

    def action_show_filter(self) -> None:
        """Toggle the search filter input."""
        try:
            inp = self.query_one("#agent-filter", Input)
        except Exception:
            return
        self._filter_visible = not self._filter_visible
        inp.display = self._filter_visible
        if self._filter_visible:
            inp.focus()
        else:
            inp.value = ""
            self._filter_text = ""
            self._selected_index = 0
            self._rebuild()
            self.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update filter text as user types."""
        if event.input.id == "agent-filter":
            self._filter_text = event.value
            self._selected_index = 0
            self._rebuild()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Close filter on Enter."""
        if event.input.id == "agent-filter":
            self._filter_visible = False
            event.input.display = False
            self.focus()

    def key_escape(self) -> None:
        """Close filter on Escape (only if filter is open)."""
        if self._filter_visible:
            try:
                inp = self.query_one("#agent-filter", Input)
                inp.value = ""
                inp.display = False
            except Exception:
                pass
            self._filter_visible = False
            self._filter_text = ""
            self._selected_index = 0
            self._rebuild()
            self.focus()

    # -- Click + cursor navigation --

    def on_click(self, event: Click) -> None:
        """Handle mouse click: first click selects, second click opens."""
        for i, widget in enumerate(self._agent_widgets):
            if event.widget is widget:
                if i == self._selected_index:
                    # Already selected: open it
                    filtered = self._filtered_agents
                    if i < len(filtered):
                        self.post_message(self.AgentSelected(filtered[i]))
                else:
                    # Select this row
                    self._selected_index = i
                    self._rebuild()
                self.focus()
                event.stop()
                return

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        filtered = self._filtered_agents
        if filtered and self._selected_index < len(filtered) - 1:
            self._selected_index += 1
            self._rebuild()

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        if self._selected_index > 0:
            self._selected_index -= 1
            self._rebuild()

    def action_select(self) -> None:
        """Select the current agent."""
        filtered = self._filtered_agents
        if filtered and 0 <= self._selected_index < len(filtered):
            self.post_message(self.AgentSelected(filtered[self._selected_index]))
