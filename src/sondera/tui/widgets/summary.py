from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Digits, Sparkline, Static


class Summary(Widget):
    BORDER_TITLE = "Summary"

    running = reactive(0, recompose=True)
    suspended = reactive(0, recompose=True)
    completed = reactive(0, recompose=True)
    failed = reactive(0, recompose=True)
    pending = reactive(0, recompose=True)

    violations = reactive(0, recompose=True)
    approved = reactive(0, recompose=True)

    def compose(self) -> ComposeResult:
        with Horizontal(classes="summary-section"):
            yield Static("[bold]Trajectories[/bold]", classes="section-label")
            with Container(classes="stat"):
                yield Static("Running", classes="stat-label")
                yield Digits(str(self.running), classes="stat-running")
            with Container(classes="stat"):
                yield Static("Suspended", classes="stat-label")
                yield Digits(str(self.suspended), classes="stat-suspended")
            with Container(classes="stat"):
                yield Static("Completed", classes="stat-label")
                yield Digits(str(self.completed), classes="stat-completed")
            with Container(classes="stat"):
                yield Static("Pending", classes="stat-label")
                yield Digits(str(self.pending), classes="stat-pending")
            with Container(classes="stat"):
                yield Static("Failed", classes="stat-label")
                yield Digits(str(self.failed), classes="stat-failed")
        with Horizontal(classes="summary-section"):
            yield Static("[bold]Policies[/bold]", classes="section-label")
            with Container(classes="stat"):
                yield Static("Violations", classes="stat-label")
                yield Digits(str(self.violations), classes="stat-violations")
            with Container(classes="stat"):
                yield Static("Approved", classes="stat-label")
                yield Digits(str(self.approved), classes="stat-approved")
        with Horizontal(classes="summary-section"):
            yield Static("[bold]Utility[/bold]", classes="section-label")
            with Container(classes="stat"):
                yield Static("Tokens: 0 tokens", classes="stat-label")
                yield Sparkline(
                    [0, 0, 100, 200, 300, 400, 500, 600, 700, 800], summary_function=max
                )
            with Container(classes="stat"):
                yield Static("Cost: $0", classes="stat-label")
                yield Sparkline(
                    [0, 0, 100, 200, 300, 400, 500, 600, 700, 800], summary_function=max
                )
