from pydantic import BaseModel
from textual.app import ComposeResult
from textual.containers import Horizontal, HorizontalScroll
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Digits, ListItem, ListView, Markdown, Sparkline, Static

from sondera.types import Agent


class AgentRecord(BaseModel):
    agent: Agent
    total_trajectories: int
    recent_trajectories: list[int] = [1, 2, 2, 1, 1, 4, 3, 1, 1, 8, 8, 2]


class AgentItem(ListItem):
    def __init__(self, element: AgentRecord):
        super().__init__()
        self.element = element
        self.border_title = self.element.agent.name

    def compose(self) -> ComposeResult:
        with HorizontalScroll():
            yield Static(self.element.agent.id, classes="column")
            yield Static(self.element.agent.provider_id or "", classes="column")
            yield Markdown(self.element.agent.description, classes="column")
            tools = ", ".join([tool.name for tool in self.element.agent.tools])
            yield Static(tools, classes="column")
            yield Digits(str(self.element.total_trajectories))
            yield Sparkline(
                self.element.recent_trajectories, summary_function=max, classes="column"
            )


class AgentList(Widget):
    BORDER_TITLE = "Agents"
    BORDER_SUBTITLE = "List of agents"

    records: reactive[list[AgentRecord]] = reactive([])

    def compose(self) -> ComposeResult:
        with Horizontal(classes="header"):
            yield Static("Id", classes="header-column")
            yield Static("Provider", classes="header-column")
            yield Static("Description", classes="header-column")
            yield Static("Tools", classes="header-column")
            yield Static("Total Trajectories", classes="header-column")
            yield Static("Recent Trajectories", classes="header-column")
        yield ListView()

    def on_mount(self) -> None:
        """Ensure ListView can receive focus."""
        list_view = self.query_one(ListView)
        list_view.can_focus = True

    def watch_records(
        self, _old_agents: list[AgentRecord], new_agents: list[AgentRecord]
    ) -> None:
        """Update the list view when agents change."""
        list_view = self.query_one(ListView)
        list_view.clear()
        for agent in new_agents:
            list_view.append(AgentItem(agent))

    def get_selected_agent(self) -> Agent | None:
        """Get the currently selected agent from the list."""
        list_view = self.query_one(ListView)
        if list_view.highlighted_child is not None and isinstance(
            list_view.highlighted_child, AgentItem
        ):
            return list_view.highlighted_child.element.agent
        return None
