from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.color import Color
from textual.theme import Theme
from textual.widget import Widget
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    ListView,
    TabbedContent,
    TabPane,
)

from sondera.harness.sondera.harness import SonderaRemoteHarness
from sondera.settings import SETTINGS
from sondera.tui.screens import AdjudicationScreen, AgentScreen, TrajectoryScreen
from sondera.tui.widgets import (
    AgentList,
    AgentRecord,
    RecentAdjudications,
    RecentTrajectories,
    Summary,
)
from sondera.types import Decision, TrajectoryStatus

sondera_theme = Theme(
    name="sondera",
    primary="#81DDB4",
    secondary="#81DDB4",
    accent="#81DDB4",
    foreground="#EAEAEA",
    background="#06110B",
    success="#A3BE8C",
    warning="#EBCB8B",
    error="#BF616A",
    surface="#06110B",
    panel="#054C53",
    dark=True,
    variables={"scrollbar": "#054C53", "scrollbar-background": "#06110B"},
)


class SonderaApp(App):
    """A Textual app for exploring Sondera agents and harness operations."""

    TITLE = "Sondera Harness"
    SUB_TITLE = "Trustworthy Agent Governance Console"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("e", "select_row", "Select"),
        Binding("1", "show_tab('trajectories-tab')", "Trajectories"),
        Binding("2", "show_tab('adjudications-tab')", "Adjudications"),
        Binding("3", "show_tab('agents-tab')", "Agents"),
        Binding("j", "cursor_down", "Move Down", show=False),
        Binding("k", "cursor_up", "Move Up", show=False),
        Binding("h", "cursor_left", "Move Left", show=False),
        Binding("l", "cursor_right", "Move Right", show=False),
        Binding("tab", "focus_next", "Next Widget", show=False),
        Binding("shift+tab", "focus_previous", "Previous Widget", show=False),
    ]

    SCREENS = {}

    def __init__(self, *args, **kwargs):
        """Initialize the app with shared resources."""
        super().__init__(*args, **kwargs)
        # Initialize the shared harness connection
        # This stays alive for the entire app lifetime
        self.harness = SonderaRemoteHarness(
            sondera_harness_endpoint=SETTINGS.sondera_harness_endpoint,
            sondera_api_key=SETTINGS.sondera_api_token,
        )

    def on_mount(self) -> None:
        """Mount the app and initialize shared resources."""
        self.register_theme(sondera_theme)
        self.theme = "sondera"
        self.screen.styles.background = Color(r=5, g=76, b=83, a=0.7)
        self.update_dataset()

    @work(exclusive=True)
    async def update_dataset(self) -> None:
        self.notify("Fetching agents, trajectories, and adjudications...")
        agents = await self.harness.list_agents()
        all_trajectories = []
        agent_records = []
        running = 0
        suspended = 0
        completed = 0
        failed = 0
        pending = 0
        for agent in agents:
            trajectories = await self.harness.list_trajectories(agent_id=agent.id)
            all_trajectories.extend(trajectories)
            agent_records.append(
                AgentRecord(
                    agent=agent,
                    total_trajectories=len(trajectories),
                )
            )
            for trajectory in trajectories:
                if trajectory.status == TrajectoryStatus.RUNNING:
                    running += 1
                elif trajectory.status == TrajectoryStatus.PENDING:
                    pending += 1
                elif trajectory.status == TrajectoryStatus.SUSPENDED:
                    suspended += 1
                elif trajectory.status == TrajectoryStatus.COMPLETED:
                    completed += 1
                elif trajectory.status == TrajectoryStatus.FAILED:
                    failed += 1
        agent_list = self.query_one(AgentList)
        agent_list.records = agent_records

        # Fetch adjudications
        adjudications, _ = await self.harness.list_adjudications(page_size=100)
        violations_count = sum(
            1 for adj in adjudications if adj.adjudication.decision == Decision.DENY
        )
        approved_count = sum(
            1 for adj in adjudications if adj.adjudication.decision == Decision.ALLOW
        )

        summary = self.query_one(Summary)
        summary.running = running
        summary.pending = pending
        summary.suspended = suspended
        summary.completed = completed
        summary.failed = failed
        summary.violations = violations_count
        summary.approved = approved_count

        all_trajectories.sort(key=lambda t: t.created_at, reverse=True)
        recent_trajectories = all_trajectories[:20]
        for trajectory in recent_trajectories:
            traj = await self.harness.get_trajectory(trajectory.id)
            if traj:
                trajectory.steps = traj.steps

        # Build agents map for provider lookup
        agents_map = {agent.id: agent.provider_id for agent in agents}

        recent_trajectories_widget = self.query_one(RecentTrajectories)
        recent_trajectories_widget.agents_map = agents_map
        recent_trajectories_widget.trajectories = recent_trajectories

        # Update recent adjudications
        adjudications_widget = self.query_one(RecentAdjudications)
        adjudications_widget.agents_map = agents_map
        adjudications_widget.adjudications = adjudications

    def compose(self) -> ComposeResult:
        yield Header()
        yield Summary(classes="card")
        with TabbedContent(id="main-tabs", classes="card"):
            with TabPane("Trajectories", id="trajectories-tab"):
                yield RecentTrajectories()
            with TabPane("Adjudications", id="adjudications-tab"):
                yield RecentAdjudications(id="recent-adjudications")
            with TabPane("Agents", id="agents-tab"):
                yield AgentList(id="agent-list")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        self.notify(f"Button pressed: {event.button.id}")

    def action_refresh(self) -> None:
        """Refresh the dataset."""
        self.update_dataset()

    def action_show_tab(self, tab: str) -> None:
        """Switch to a tab."""
        self.query_one("#main-tabs", TabbedContent).active = tab

    def _get_focused_table_or_list(self) -> DataTable | ListView | None:
        """Get the focused DataTable or ListView."""
        focused = self.focused
        if not focused:
            return None

        if isinstance(focused, (DataTable, ListView)):
            return focused

        # Check parent chain for containers
        parent = focused.parent
        while parent:
            if isinstance(parent, RecentTrajectories):
                return parent.query_one(DataTable)
            if isinstance(parent, RecentAdjudications):
                return parent.query_one(DataTable)
            if isinstance(parent, AgentList):
                return parent.query_one(ListView)
            parent = parent.parent

        return None

    def action_cursor_down(self) -> None:
        """Move cursor down in focused table or list."""
        if widget := self._get_focused_table_or_list():
            widget.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up in focused table or list."""
        if widget := self._get_focused_table_or_list():
            widget.action_cursor_up()

    def action_cursor_left(self) -> None:
        """Move cursor left in focused table."""
        if isinstance(widget := self._get_focused_table_or_list(), DataTable):
            widget.action_cursor_left()

    def action_cursor_right(self) -> None:
        """Move cursor right in focused table."""
        if isinstance(widget := self._get_focused_table_or_list(), DataTable):
            widget.action_cursor_right()

    def _get_focusable_widgets(self) -> list[DataTable | ListView]:
        """Get list of focusable widgets in order."""
        return [
            self.query_one(RecentTrajectories).query_one(DataTable),
            self.query_one("#recent-adjudications", RecentAdjudications).query_one(
                DataTable
            ),
            self.query_one("#agent-list", AgentList).query_one(ListView),
        ]

    def _find_current_index(
        self, widgets: list[DataTable | ListView], focused: Widget | None
    ) -> int | None:
        """Find index of currently focused widget."""
        if not focused:
            return None

        for i, widget in enumerate(widgets):
            if widget == focused:
                return i
            # Check parent chain
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

    def action_select_row(self) -> None:
        """Select the current row in the focused table or list."""
        focused_widget = self._get_focused_table_or_list()
        if isinstance(focused_widget, DataTable):
            # Check if focused on RecentTrajectories
            trajectories_widget = self.query_one(RecentTrajectories)
            if focused_widget == trajectories_widget.query_one(DataTable):
                if trajectory := trajectories_widget.get_selected_trajectory():
                    self.push_screen(TrajectoryScreen(trajectory))
                else:
                    self.notify("No trajectory selected")
                return

            # Check if focused on RecentAdjudications
            adjudications_widget = self.query_one(
                "#recent-adjudications", RecentAdjudications
            )
            if focused_widget == adjudications_widget.query_one(DataTable):
                if adjudication := adjudications_widget.get_selected_adjudication():
                    self.push_screen(AdjudicationScreen(agent_id=adjudication.agent_id))
                else:
                    self.notify("No adjudication selected")
                return

            self.notify("No item selected")
        elif isinstance(focused_widget, ListView):
            # Handle agent selection from AgentList
            agent_list = self.query_one(AgentList)
            if agent := agent_list.get_selected_agent():
                self.push_screen(AgentScreen(agent))
            else:
                self.notify("No agent selected")
