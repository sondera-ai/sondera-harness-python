from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable

from sondera.types import AdjudicationRecord


class RecentAdjudications(Widget):
    BORDER_TITLE = "Recent Adjudications"

    adjudications: reactive[list[AdjudicationRecord]] = reactive([])
    agents_map: reactive[dict[str, str]] = reactive({})

    HEADERS = ["Id", "Agent", "Provider", "Decision", "Reason"]

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
            provider = self.agents_map.get(record.agent_id, "N/A")
            table.add_row(
                record.trajectory_id[:6] + "...",
                record.agent_id,
                provider,
                record.adjudication.decision.value.upper(),
                record.adjudication.reason[:30] + "..."
                if len(record.adjudication.reason) > 30
                else record.adjudication.reason,
            )

    def get_selected_adjudication(self) -> AdjudicationRecord | None:
        """Get the currently selected adjudication from the table."""
        table = self.query_one(DataTable)
        cursor_row = table.cursor_row
        if cursor_row is not None and 0 <= cursor_row < len(self.adjudications):
            return self.adjudications[cursor_row]
        return None
