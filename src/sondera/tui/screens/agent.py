from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import DataTable, Footer, Header, ListView, Tree

from sondera.types import AdjudicatedTrajectory, Agent

from ..widgets.agent_card import AgentCard
from ..widgets.recent_trajectories import RecentTrajectories
from .trajectory import TrajectoryScreen


class AgentScreen(Screen):
    app: "sondera.tui.app.SonderaApp"  # type: ignore[name-defined]  # noqa: UP037, F821
    """A screen for displaying agent details and trajectories."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back to Dashboard"),
        Binding("tab", "focus_next", "Next Widget", show=False),
        Binding("shift+tab", "focus_previous", "Previous Widget", show=False),
        Binding("j", "cursor_down", "Move Down", show=False),
        Binding("k", "cursor_up", "Move Up", show=False),
        Binding("e", "select_trajectory", "Select Trajectory"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, agent: Agent):
        super().__init__()
        self.agent = agent
        self.trajectories: list[AdjudicatedTrajectory] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(classes="panel"):
            yield AgentCard(agent=self.agent, id="agent-card", classes="card")
            yield RecentTrajectories(id="recent-trajectories", classes="card")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen."""
        self.sub_title = f"Agent: {self.agent.name}"
        self.load_trajectories()

    @work(exclusive=True)
    async def load_trajectories(self) -> None:
        """Load trajectories for this agent."""
        self.notify(f"Loading trajectories for {self.agent.name}...")
        trajectories = await self.app.harness.list_trajectories(agent_id=self.agent.id)
        trajectories.sort(key=lambda t: t.created_at, reverse=True)
        recent_trajectories = trajectories[:50]  # Limit to 50 most recent

        # Fetch full adjudicated trajectory details for each
        adjudicated_trajectories: list[AdjudicatedTrajectory] = []
        for trajectory in recent_trajectories:
            traj = await self.app.harness.get_trajectory(trajectory.id)
            if traj:
                adjudicated_trajectories.append(traj)

        self.trajectories = adjudicated_trajectories

        # Update the RecentTrajectories widget
        recent_trajectories = self.query_one("#recent-trajectories", RecentTrajectories)
        recent_trajectories.trajectories = self.trajectories

    def get_selected_trajectory(self) -> AdjudicatedTrajectory | None:
        """Get the currently selected trajectory from the RecentTrajectories widget."""
        recent_trajectories = self.query_one("#recent-trajectories", RecentTrajectories)
        return recent_trajectories.get_selected_trajectory()

    def action_select_trajectory(self) -> None:
        """Select the current trajectory and push TrajectoryScreen."""
        if trajectory := self.get_selected_trajectory():
            self.app.push_screen(TrajectoryScreen(trajectory))
        else:
            self.notify("No trajectory selected")

    def action_refresh(self) -> None:
        """Refresh trajectories."""
        self.load_trajectories()

    def _get_focusable_widgets(self) -> list[ListView | DataTable | Tree]:
        """Get list of focusable widgets in order."""
        widgets: list[ListView | DataTable | Tree] = []
        try:
            tools_list = self.query_one("#tools-list", ListView)
            widgets.append(tools_list)
        except Exception:
            pass  # Widget is optional; if not present, just skip it
        try:
            recent_trajectories = self.query_one(
                "#recent-trajectories", RecentTrajectories
            )
            # Get the DataTable from within the RecentTrajectories widget
            table = recent_trajectories.query_one(DataTable)
            widgets.append(table)
        except Exception:
            pass  # Widget is optional; if not present, just skip it
        return widgets

    def _find_current_index(
        self, widgets: list[ListView | DataTable | Tree], focused: Widget | None
    ) -> int | None:
        """Find index of currently focused widget."""
        if not focused:
            return None

        for i, widget in enumerate(widgets):
            if widget == focused:
                return i
            parent = focused.parent
            while parent:
                if parent == widget:
                    return i
                parent = parent.parent
        return None

    def action_focus_next(self) -> None:
        """Move focus to next focusable widget."""
        widgets = self._get_focusable_widgets()
        if not widgets:
            return

        current_index = self._find_current_index(widgets, self.focused)
        next_index = (
            (current_index + 1) % len(widgets) if current_index is not None else 0
        )
        widgets[next_index].focus()

    def action_focus_previous(self) -> None:
        """Move focus to previous focusable widget."""
        widgets = self._get_focusable_widgets()
        if not widgets:
            return

        current_index = self._find_current_index(widgets, self.focused)
        prev_index = (
            (current_index - 1) % len(widgets)
            if current_index is not None
            else len(widgets) - 1
        )
        widgets[prev_index].focus()

    def action_cursor_down(self) -> None:
        """Move cursor down in focused widget."""
        focused = self.focused
        if isinstance(focused, (DataTable, ListView)):
            focused.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up in focused widget."""
        focused = self.focused
        if isinstance(focused, (DataTable, ListView)):
            focused.action_cursor_up()
