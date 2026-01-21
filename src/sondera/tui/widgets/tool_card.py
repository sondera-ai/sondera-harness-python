from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import ListItem, Static

from sondera.types import Tool


class ToolCard(ListItem):
    """A reusable widget for displaying tool details as a ListItem."""

    def __init__(self, tool: Tool):
        super().__init__()
        self.tool = tool
        self.border_title = f"🛠 {tool.name}"

    def compose(self) -> ComposeResult:
        with Vertical(classes="tool-card-content"):
            yield Static(
                f"[bold]Description:[/bold] {self.tool.description}",
                classes="tool-description",
            )
            if self.tool.parameters:
                params_text = ", ".join(
                    f"[cyan]{p.name}[/cyan]: {p.type}" for p in self.tool.parameters
                )
                yield Static(
                    f"[bold]Parameters:[/bold] {params_text}", classes="tool-parameters"
                )
            if self.tool.response:
                yield Static(
                    f"[bold]Returns:[/bold] {self.tool.response}",
                    classes="tool-response",
                )
