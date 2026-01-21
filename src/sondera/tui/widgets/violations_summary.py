from collections import Counter

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Digits, Static

from sondera.types import AdjudicationRecord, Decision


class ViolationsSummary(Widget):
    """Widget displaying violations statistics.

    Shows:
    - Total violations count
    - Violations grouped by agent
    - Violations grouped by policy
    """

    BORDER_TITLE = "Violations Summary"

    adjudications: reactive[list[AdjudicationRecord]] = reactive([], recompose=True)

    def _get_violations(self) -> list[AdjudicationRecord]:
        """Filter adjudications to only include violations (DENY decisions)."""
        return [
            adj
            for adj in self.adjudications
            if adj.adjudication.decision == Decision.DENY
        ]

    def _get_escalations(self) -> list[AdjudicationRecord]:
        """Filter adjudications to include escalations."""
        return [
            adj
            for adj in self.adjudications
            if adj.adjudication.decision == Decision.ESCALATE
        ]

    def _count_by_agent(self, violations: list[AdjudicationRecord]) -> Counter:
        """Count violations by agent ID."""
        return Counter(v.agent_id for v in violations)

    def _count_by_policy(self, violations: list[AdjudicationRecord]) -> Counter:
        """Count violations by policy (from reason field)."""
        # Extract policy identifier from reason - typically first word or phrase
        return Counter(v.adjudication.reason.split(":")[0].strip() for v in violations)

    def compose(self) -> ComposeResult:
        violations = self._get_violations()
        escalations = self._get_escalations()
        total_adjudications = len(self.adjudications)
        allowed = total_adjudications - len(violations) - len(escalations)

        # Overall counts
        yield Static("[bold]Overview[/bold]", classes="section-header")
        with Horizontal(classes="summary-row"):
            with Container(classes="summary-item"):
                yield Static("Total Adjudications")
                yield Digits(str(total_adjudications), classes="summary-digit")
            with Container(classes="summary-item"):
                yield Static("Allowed", classes="stat-allowed")
                yield Digits(str(allowed), classes="summary-digit digit-allowed")
            with Container(classes="summary-item"):
                yield Static("Violations", classes="stat-violations")
                yield Digits(
                    str(len(violations)), classes="summary-digit digit-violations"
                )
            with Container(classes="summary-item"):
                yield Static("Escalated", classes="stat-escalated")
                yield Digits(
                    str(len(escalations)), classes="summary-digit digit-escalated"
                )

        # Violations by Agent
        yield Static("[bold]Violations by Agent[/bold]", classes="section-header")
        by_agent = self._count_by_agent(violations)
        if by_agent:
            with Horizontal(classes="summary-row"):
                for agent_id, count in by_agent.most_common(5):
                    with Container(classes="summary-item"):
                        display_id = (
                            agent_id[:12] + "..." if len(agent_id) > 15 else agent_id
                        )
                        yield Static(display_id, classes="agent-label")
                        yield Digits(str(count), classes="summary-digit")
        else:
            yield Static("No violations by agent", classes="empty-message")

        # Violations by Policy/Reason
        yield Static("[bold]Violations by Policy[/bold]", classes="section-header")
        by_policy = self._count_by_policy(violations)
        if by_policy:
            with Horizontal(classes="summary-row"):
                for policy, count in by_policy.most_common(5):
                    with Container(classes="summary-item"):
                        display_policy = (
                            policy[:15] + "..." if len(policy) > 18 else policy
                        )
                        yield Static(display_policy, classes="policy-label")
                        yield Digits(str(count), classes="summary-digit")
        else:
            yield Static("No violations by policy", classes="empty-message")
