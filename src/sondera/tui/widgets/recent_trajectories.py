from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable

from sondera.types import AdjudicatedTrajectory


class RecentTrajectories(Widget):
    BORDER_TITLE = "Recent Trajectories"

    trajectories: reactive[list[AdjudicatedTrajectory]] = reactive([])
    agents_map: reactive[dict[str, str]] = reactive({})

    HEADERS = ["Id", "Agent", "Provider", "Status", "Turns", "Last Active"]

    def compose(self) -> ComposeResult:
        yield DataTable()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns(*self.HEADERS)
        table.cursor_type = "row"
        table.zebra_stripes = True
        # Ensure table can receive focus
        table.can_focus = True

    def watch_trajectories(
        self,
        _old_trajectories: list[AdjudicatedTrajectory],
        new_trajectories: list[AdjudicatedTrajectory],
    ) -> None:
        table = self.query_one(DataTable)
        table.clear()
        for trajectory in new_trajectories:
            provider = self.agents_map.get(trajectory.agent_id, "N/A")
            table.add_row(
                trajectory.id[:6] + "...",
                trajectory.agent_id,
                provider,
                trajectory.status.value,
                len(trajectory.steps),
                trajectory.updated_at.strftime("%Y-%m-%d %H:%M:%S")
                if trajectory.ended_at
                else "N/A",
            )

    def get_selected_trajectory(self) -> AdjudicatedTrajectory | None:
        """Get the currently selected trajectory from the table."""
        table = self.query_one(DataTable)
        cursor_row = table.cursor_row
        if cursor_row is not None and 0 <= cursor_row < len(self.trajectories):
            return self.trajectories[cursor_row]
        return None
