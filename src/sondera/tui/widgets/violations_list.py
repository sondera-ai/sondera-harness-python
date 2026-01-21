from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable

from sondera.types import AdjudicationRecord, Decision


class ViolationsList(Widget):
    """Widget displaying a list of violations/adjudications in a table format."""

    BORDER_TITLE = "Adjudications"

    adjudications: reactive[list[AdjudicationRecord]] = reactive([])

    HEADERS = ["Decision", "Agent", "Trajectory", "Step", "Reason", "Annotations"]

    def compose(self) -> ComposeResult:
        yield DataTable()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns(*self.HEADERS)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.can_focus = True

    def watch_adjudications(
        self,
        _old_adjudications: list[AdjudicationRecord],
        new_adjudications: list[AdjudicationRecord],
    ) -> None:
        table = self.query_one(DataTable)
        table.clear()
        for record in new_adjudications:
            decision = record.adjudication.decision
            if decision == Decision.DENY:
                decision_display = "❌ DENY"
            elif decision == Decision.ESCALATE:
                decision_display = "⚠️ ESCALATE"
            else:
                decision_display = "✅ ALLOW"

            reason = record.adjudication.reason
            reason_display = reason[:40] + "..." if len(reason) > 43 else reason

            # Format annotations as comma-separated policy IDs
            annotations = record.adjudication.annotations
            if annotations:
                ann_ids = [ann.id for ann in annotations]
                annotations_display = ", ".join(ann_ids)
                if len(annotations_display) > 30:
                    annotations_display = annotations_display[:27] + "..."
            else:
                annotations_display = "-"

            table.add_row(
                decision_display,
                record.agent_id[:12] + "..."
                if len(record.agent_id) > 15
                else record.agent_id,
                record.trajectory_id[:8] + "..."
                if len(record.trajectory_id) > 11
                else record.trajectory_id,
                record.step_id[:8] + "..."
                if len(record.step_id) > 11
                else record.step_id,
                reason_display,
                annotations_display,
            )

    def get_selected_adjudication(self) -> AdjudicationRecord | None:
        """Get the currently selected adjudication record from the table."""
        table = self.query_one(DataTable)
        cursor_row = table.cursor_row
        if cursor_row is not None and 0 <= cursor_row < len(self.adjudications):
            return self.adjudications[cursor_row]
        return None
