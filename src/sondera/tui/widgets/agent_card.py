from textual.app import ComposeResult
from textual.containers import Grid, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import ListView, Static

from sondera.types import Agent

from .tool_card import ToolCard


class AgentCard(Widget):
    """A reusable widget for displaying agent details in a grid layout."""

    BORDER_TITLE = "Agent Details"

    agent: reactive[Agent | None] = reactive(None)

    def __init__(self, agent: Agent | None = None, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent

    def compose(self) -> ComposeResult:
        with Vertical(id="agent-card-container"):
            with Grid(id="agent-details-grid", classes="agent-details-grid"):
                yield Static("[bold]ID:[/bold]", classes="label")
                yield Static(
                    self.agent.id if self.agent else "N/A",
                    id="agent-id",
                    classes="value",
                )

                yield Static("[bold]Name:[/bold]", classes="label")
                yield Static(
                    self.agent.name if self.agent else "N/A",
                    id="agent-name",
                    classes="value",
                )

                yield Static("[bold]Provider:[/bold]", classes="label")
                yield Static(
                    self.agent.provider_id if self.agent else "N/A",
                    id="agent-provider",
                    classes="value",
                )

                yield Static("[bold]Description:[/bold]", classes="label")
                yield Static(
                    self.agent.description if self.agent else "N/A",
                    id="agent-description",
                    classes="value description",
                )

                yield Static("[bold]Instruction:[/bold]", classes="label")
                yield Static(
                    self.agent.instruction if self.agent else "N/A",
                    id="agent-instruction",
                    classes="value instruction",
                )

            yield Static("[bold]Tools[/bold]", classes="section-header")
            yield ListView(id="tools-list")

    def on_mount(self) -> None:
        """Populate tools list on mount."""
        self._update_tools_list()

    def watch_agent(self, _old_agent: Agent | None, new_agent: Agent | None) -> None:
        """Update display when agent changes."""
        if new_agent:
            self._update_agent_details(new_agent)
            self._update_tools_list()

    def _update_agent_details(self, agent: Agent) -> None:
        """Update the agent detail fields."""
        try:
            self.query_one("#agent-id", Static).update(agent.id)
            self.query_one("#agent-name", Static).update(agent.name)
            self.query_one("#agent-provider", Static).update(agent.provider_id)
            self.query_one("#agent-description", Static).update(agent.description)
            self.query_one("#agent-instruction", Static).update(agent.instruction)
        except Exception:
            pass  # Widgets may not be mounted yet during reactive updates

    def _update_tools_list(self) -> None:
        """Update the tools ListView."""
        try:
            tools_list = self.query_one("#tools-list", ListView)
            tools_list.clear()
            if self.agent and self.agent.tools:
                for tool in self.agent.tools:
                    tools_list.append(ToolCard(tool))
        except Exception:
            pass  # Widget may not be mounted yet during reactive updates
