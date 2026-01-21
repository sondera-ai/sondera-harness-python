from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import DataTable, Footer, Header

from sondera.types import AdjudicationRecord

from ..widgets.violation_panel import ViolationPanel
from ..widgets.violations_list import ViolationsList
from ..widgets.violations_summary import ViolationsSummary
from .trajectory import TrajectoryScreen


class AdjudicationScreen(Screen):
    app: "sondera.tui.app.SonderaApp"  # type: ignore[name-defined]  # noqa: UP037, F821
    """Screen for displaying adjudication/violation information.

    Shows:
    - Violations Summary: Count, by agent, by policy
    - Violations List: All adjudication records
    - Violation Panel: Detailed view of selected violation
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back to Dashboard"),
        Binding("tab", "focus_next", "Next Widget", show=False),
        Binding("shift+tab", "focus_previous", "Previous Widget", show=False),
        Binding("j", "cursor_down", "Move Down", show=False),
        Binding("k", "cursor_up", "Move Up", show=False),
        Binding("r", "refresh", "Refresh"),
        Binding("e", "select_row", "Select"),
    ]

    def __init__(self, agent_id: str | None = None):
        super().__init__()
        self.agent_id = agent_id
        self.adjudications: list[AdjudicationRecord] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(classes="adjudication-content"):
            with Vertical(id="adjudication-left-panel"):
                yield ViolationsSummary(id="violations-summary", classes="card")
                yield ViolationsList(id="violations-list", classes="card")
            yield ViolationPanel(id="violation-panel", classes="card")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen."""
        if self.agent_id:
            self.sub_title = f"Adjudications: {self.agent_id}"
        else:
            self.sub_title = "All Adjudications"
        self.load_adjudications()

    @work(exclusive=True)
    async def load_adjudications(self) -> None:
        """Load adjudications from the harness service."""
        self.notify("Loading adjudications...")
        try:
            adjudications, _ = await self.app.harness.list_adjudications(
                agent_id=self.agent_id, page_size=100
            )
            self.adjudications = adjudications

            # Update widgets
            summary = self.query_one("#violations-summary", ViolationsSummary)
            summary.adjudications = adjudications

            violations_list = self.query_one("#violations-list", ViolationsList)
            violations_list.adjudications = adjudications

            self.notify(f"Loaded {len(adjudications)} adjudications")
        except Exception as e:
            self.notify(f"Failed to load adjudications: {e}", severity="error")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection in the violations list."""
        violations_list = self.query_one("#violations-list", ViolationsList)
        if adjudication := violations_list.get_selected_adjudication():
            self.open_trajectory(adjudication.trajectory_id)

    @work(exclusive=True)
    async def open_trajectory(self, trajectory_id: str) -> None:
        """Fetch trajectory and push to TrajectoryScreen."""
        self.notify(f"Loading trajectory {trajectory_id[:8]}...")
        try:
            trajectory = await self.app.harness.get_trajectory(trajectory_id)
            if trajectory:
                self.app.push_screen(TrajectoryScreen(trajectory))
            else:
                self.notify("Trajectory not found", severity="error")
        except Exception as e:
            self.notify(f"Failed to load trajectory: {e}", severity="error")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle row highlight (cursor movement) in the violations list."""
        violations_list = self.query_one("#violations-list", ViolationsList)
        if adjudication := violations_list.get_selected_adjudication():
            panel = self.query_one("#violation-panel", ViolationPanel)
            panel.adjudication = adjudication

    def action_refresh(self) -> None:
        """Refresh adjudications."""
        self.load_adjudications()

    def _get_focusable_widgets(self) -> list[DataTable]:
        """Get list of focusable widgets in order."""
        widgets: list[DataTable] = []
        try:
            violations_list = self.query_one("#violations-list", ViolationsList)
            table = violations_list.query_one(DataTable)
            widgets.append(table)
        except Exception:
            pass
        return widgets

    def _find_current_index(
        self, widgets: list[DataTable], focused: Widget | None
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
        if isinstance(focused, DataTable):
            focused.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up in focused widget."""
        focused = self.focused
        if isinstance(focused, DataTable):
            focused.action_cursor_up()

    def action_select_row(self) -> None:
        """Select the current row and open the trajectory."""
        violations_list = self.query_one("#violations-list", ViolationsList)
        if adjudication := violations_list.get_selected_adjudication():
            self.open_trajectory(adjudication.trajectory_id)
        else:
            self.notify("No adjudication selected")
