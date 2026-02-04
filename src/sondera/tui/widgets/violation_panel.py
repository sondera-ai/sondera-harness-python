from textual.app import ComposeResult
from textual.containers import Container, Grid, VerticalScroll
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Markdown, Static

from sondera.types import AdjudicationRecord, Decision


class ViolationPanel(Widget):
    """Widget displaying detailed information about a selected violation/adjudication."""

    BORDER_TITLE = "Violation Details"

    adjudication: reactive[AdjudicationRecord | None] = reactive(None, recompose=True)

    def compose(self) -> ComposeResult:
        if self.adjudication is None:
            yield Static(
                "Select an adjudication to view details", classes="empty-message"
            )
            return

        record = self.adjudication
        decision = record.adjudication.decision

        # Decision badge
        if decision == Decision.DENY:
            decision_class = "decision-deny"
            decision_text = "❌ DENIED"
        elif decision == Decision.ESCALATE:
            decision_class = "decision-escalate"
            decision_text = "⚠️ ESCALATED"
        else:
            decision_class = "decision-allow"
            decision_text = "✅ ALLOWED"

        yield Static(decision_text, classes=f"decision-badge {decision_class}")

        # Details grid
        with Grid(id="violation-details-grid"):
            yield Static("Agent ID:", classes="label")
            yield Static(record.agent_id, classes="value")

            yield Static("Trajectory ID:", classes="label")
            yield Static(record.trajectory_id, classes="value")

            yield Static("Step ID:", classes="label")
            yield Static(record.step_id, classes="value")

        # Reason section
        yield Static("[bold]Reason[/bold]", classes="section-header")
        with Container(classes="reason-container"):
            yield Markdown(record.adjudication.reason, classes="reason-text")

        # Policies section
        policies = record.adjudication.policies
        if policies:
            yield Static("[bold]Policies[/bold]", classes="section-header")
            with VerticalScroll(classes="annotations-container"):
                for policy in policies:
                    with Container(classes="annotation-card"):
                        yield Static(
                            f"[bold]{policy.id}[/bold]", classes="annotation-id"
                        )
                        if policy.description:
                            yield Static(
                                policy.description, classes="annotation-description"
                            )
                        if policy.custom:
                            with Grid(classes="annotation-custom-grid"):
                                for key, value in policy.custom.items():
                                    yield Static(f"{key}:", classes="label")
                                    yield Static(value, classes="value")
