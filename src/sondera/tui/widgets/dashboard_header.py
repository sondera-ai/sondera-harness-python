"""Dashboard header: single-row severity stats and problem agent count."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

from sondera.tui.colors import get_theme_colors


class DashboardHeader(Widget):
    """Single-row header: denial/awaiting/live counts and problem agent count."""

    can_focus = False

    DEFAULT_CSS = """
    DashboardHeader {
        height: 1;
        padding: 0 1;
        background: $surface;
    }
    """

    violation_count = reactive(0)
    awaiting_count = reactive(0)
    live_count = reactive(0)
    total_agents = reactive(0)
    problem_agent_count = reactive(0)

    def render(self) -> Text:
        c = get_theme_colors(self.app)
        text = Text()

        # Brand
        text.append("SONDERA", style=f"bold {c.primary}")
        text.append("  ")

        # Denied count
        if self.violation_count > 0:
            text.append(
                f"\u2717 {self.violation_count} denied",
                style=f"bold {c.error}",
            )
        else:
            text.append("\u2713 0 denied", style=c.success)
        text.append("  ")

        # Awaiting (escalated)
        if self.awaiting_count > 0:
            text.append(
                f"\u26a0 {self.awaiting_count} awaiting", style=f"bold {c.warning}"
            )
        else:
            text.append("\u26a0 0 awaiting", style=c.fg_dim)
        text.append("  ")

        # Live agents
        if self.live_count > 0:
            text.append(f"\u25cf {self.live_count} live", style=f"bold {c.primary}")
        else:
            text.append("\u25cf 0 live", style=c.fg_dim)
        text.append("  ")

        # Total agents with problem count
        if self.problem_agent_count > 0:
            text.append(f"{self.total_agents} agents ", style=c.fg_dim)
            n = self.problem_agent_count
            text.append(
                f"({n} need{'s' if n == 1 else ''} attention)",
                style=f"bold {c.error}",
            )
        else:
            text.append(f"{self.total_agents} agents", style=c.fg_dim)

        return text

    def watch_violation_count(self) -> None:
        self.refresh()

    def watch_awaiting_count(self) -> None:
        self.refresh()

    def watch_live_count(self) -> None:
        self.refresh()

    def watch_total_agents(self) -> None:
        self.refresh()

    def watch_problem_agent_count(self) -> None:
        self.refresh()
