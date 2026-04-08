"""Violations feed: grouped violation rows with DENY/ESCALATE sections."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import ScrollableContainer
from textual.css.query import NoMatches
from textual.events import Click
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from sondera.tui.colors import get_theme_colors
from sondera.tui.events import ViolationRecord
from sondera.tui.util import relative_time as _relative_time
from sondera.types import Decision

MAX_VISIBLE_GROUPS = 10


@dataclass
class ViolationGroup:
    """Violations grouped by agent + decision + reason."""

    records: list[ViolationRecord]
    agent_id: str
    agent_name: str
    decision: Decision
    reason: str
    count: int
    policy_id: str
    policy_description: str
    trajectory_ids: set[str] = field(default_factory=set)


class ViolationsFeed(Widget):
    """Violations section: grouped, with DENY/ESCALATE sections and inline expansion."""

    can_focus = True

    DEFAULT_CSS = """
    ViolationsFeed {
        height: auto;
        max-height: 24;
    }
    ViolationsFeed #violations-header {
        height: 1;
        padding: 0 1;
    }
    ViolationsFeed #violations-container {
        height: auto;
        max-height: 22;
        scrollbar-size: 0 0;
    }
    ViolationsFeed .violation-row {
        height: 1;
        padding: 0 1;
    }
    ViolationsFeed .violation-row.--selected {
        background: $primary 12%;
    }
    ViolationsFeed .violation-detail {
        height: 1;
        padding: 0 1;
        background: $primary 5%;
    }
    ViolationsFeed .section-label {
        height: 1;
        padding: 0 1;
    }
    ViolationsFeed .view-all-row {
        height: 1;
        padding: 0 1;
    }
    """

    violations: reactive[list[ViolationRecord]] = reactive(list, always_update=True)
    agents_map: reactive[dict[str, str]] = reactive(dict, always_update=True)
    # Trajectory timestamps: trajectory_id -> most recent timestamp
    trajectory_times: reactive[dict[str, datetime]] = reactive(dict, always_update=True)

    class ViolationSelected(Message):
        """Posted when user presses Enter on a violation."""

        def __init__(self, record: ViolationRecord) -> None:
            self.record = record
            super().__init__()

    class AgentJumpRequested(Message):
        """Posted when user presses 'a' to jump to the agent."""

        def __init__(self, agent_id: str) -> None:
            self.agent_id = agent_id
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._selected_index: int = 0
        self._row_widgets: list[Static] = []
        self._has_focus: bool = False
        # Built groups (for navigation)
        self._deny_groups: list[ViolationGroup] = []
        self._escalate_groups: list[ViolationGroup] = []
        self._flat_groups: list[ViolationGroup] = []

    def on_focus(self, _event) -> None:
        self._has_focus = True
        self._rebuild()
        # Deactivate sibling feed
        try:
            from sondera.tui.widgets.agents_feed import AgentsFeed

            sibling = self.screen.query_one(AgentsFeed)
            if sibling._has_focus:
                sibling._has_focus = False
                sibling._rebuild()
        except (NoMatches, ImportError):
            pass

    def compose(self) -> ComposeResult:
        yield Static(id="violations-header")
        container = ScrollableContainer(id="violations-container")
        container.can_focus = False
        yield container

    @property
    def _visible_violations(self) -> list[ViolationGroup]:
        """Get the flat list of visible groups (for cursor navigation)."""
        return self._flat_groups[:MAX_VISIBLE_GROUPS]

    def watch_violations(
        self,
        old_violations: list[ViolationRecord],
        new_violations: list[ViolationRecord],
    ) -> None:
        # Preserve selection by matching group identity across refreshes
        old_groups = self._flat_groups
        if old_groups and 0 <= self._selected_index < len(old_groups):
            prev = old_groups[self._selected_index]
            prev_key = (prev.agent_id, prev.decision, prev.reason)
            # Rebuild groups first so we can search the new list
            self._deny_groups, self._escalate_groups = self._build_groups()
            self._flat_groups = self._deny_groups + self._escalate_groups
            for i, g in enumerate(self._flat_groups):
                if (g.agent_id, g.decision, g.reason) == prev_key:
                    self._selected_index = i
                    break
            else:
                self._selected_index = 0
        else:
            self._selected_index = 0
        self._rebuild()

    def watch_agents_map(self) -> None:
        self._rebuild()

    def watch_trajectory_times(self) -> None:
        self._rebuild()

    def _build_groups(
        self,
    ) -> tuple[list[ViolationGroup], list[ViolationGroup]]:
        """Group violations by (agent_id, decision, reason) into DENY and ESCALATE lists."""
        groups_map: dict[tuple, list[ViolationRecord]] = defaultdict(list)
        for record in self.violations:
            key = (
                record.agent_id,
                str(record.decision),
                record.reason,
            )
            groups_map[key].append(record)

        deny_groups: list[ViolationGroup] = []
        escalate_groups: list[ViolationGroup] = []

        for (agent_id, _decision_val, reason), records in groups_map.items():
            decision = records[0].decision
            agent_name = self.agents_map.get(agent_id) or agent_id[:16]
            policy_id = ""
            policy_desc = ""
            if records[0].policies:
                p = records[0].policies[0]
                policy_id = p.policy_id or ""
                policy_desc = p.description or ""

            group = ViolationGroup(
                records=records,
                agent_id=agent_id,
                agent_name=agent_name,
                decision=decision,
                reason=reason,
                count=len(records),
                policy_id=policy_id,
                policy_description=policy_desc,
                trajectory_ids={r.trajectory_id for r in records},
            )

            if decision == Decision.Deny:
                deny_groups.append(group)
            elif decision == Decision.Escalate:
                escalate_groups.append(group)

        return deny_groups, escalate_groups

    def _rebuild(self) -> None:
        """Rebuild all violation rows with DENY/ESCALATE sections."""
        try:
            header = self.query_one("#violations-header", Static)
            container = self.query_one("#violations-container", ScrollableContainer)
        except Exception:
            return

        total_count = len(self.violations)
        self._deny_groups, self._escalate_groups = self._build_groups()

        # Flat list for cursor navigation: DENY groups then ESCALATE groups
        self._flat_groups = self._deny_groups + self._escalate_groups

        c = get_theme_colors(self.app)

        # Update header
        header_text = Text()
        header_text.append("RECENT VIOLATIONS", style=f"bold {c.fg}")
        header_text.append(f" ({total_count})", style=c.fg_dim)
        header.update(header_text)

        # Rebuild rows
        container.remove_children()
        self._row_widgets = []

        if not self._flat_groups:
            empty = Static(Text("  \u2713 No policy violations", style=c.success))
            empty.add_class("violation-row")
            container.mount(empty)
            return

        flat_idx = 0
        has_both = bool(self._deny_groups) and bool(self._escalate_groups)

        # DENIED section
        if self._deny_groups:
            if has_both:
                deny_count = sum(g.count for g in self._deny_groups)
                section = Text()
                section.append(f"  DENIED ({deny_count})", style=f"bold {c.error}")
                section_widget = Static(section)
                section_widget.add_class("section-label")
                container.mount(section_widget)

            for group in self._deny_groups:
                is_selected = flat_idx == self._selected_index
                self._mount_group_row(container, group, is_selected, flat_idx)
                flat_idx += 1

        # AWAITING REVIEW section (only shown when escalations exist)
        if self._escalate_groups:
            if has_both:
                escalate_count = sum(g.count for g in self._escalate_groups)
                section = Text()
                section.append(
                    f"  AWAITING REVIEW ({escalate_count})",
                    style=f"bold {c.warning}",
                )
                section_widget = Static(section)
                section_widget.add_class("section-label")
                container.mount(section_widget)

            for group in self._escalate_groups:
                is_selected = flat_idx == self._selected_index
                self._mount_group_row(container, group, is_selected, flat_idx)
                flat_idx += 1

    def _mount_group_row(
        self,
        container: ScrollableContainer,
        group: ViolationGroup,
        is_selected: bool,
        flat_idx: int,
    ) -> None:
        """Mount a violation group row and optional inline detail."""
        row_text = self._render_group_row(group, is_selected)
        widget = Static(row_text)
        widget.add_class("violation-row")
        if is_selected and self._has_focus:
            widget.add_class("--selected")
        container.mount(widget)
        self._row_widgets.append(widget)

        # Inline detail for selected row (only when focused)
        if is_selected and self._has_focus:
            details = self._render_group_detail(group)
            for detail_text in details:
                d = Static(detail_text)
                d.add_class("violation-detail")
                container.mount(d)

    def _render_group_row(self, group: ViolationGroup, is_selected: bool) -> Text:
        """Render a single violation group row."""
        c = get_theme_colors(self.app)
        text = Text()

        # Cursor
        if is_selected and self._has_focus:
            text.append("\u25b8 ", style=f"bold {c.primary}")
        else:
            text.append("  ")

        # Decision icon
        if group.decision == Decision.Deny:
            text.append("\u2717 ", style=f"bold {c.error}")
        elif group.decision == Decision.Escalate:
            text.append("\u26a0 ", style=f"bold {c.warning}")

        # Agent name
        name_padded = group.agent_name[:22].ljust(22)
        text.append(name_padded, style=f"bold {c.fg}")

        # Reason preview (truncated)
        reason_preview = group.reason[:40] if group.reason else ""
        text.append(reason_preview.ljust(42), style=c.fg_secondary)

        # Count badge
        if group.count > 1:
            text.append(f"\u00d7{group.count}", style=f"bold {c.fg}")
            text.append("  ")

        # Trajectory count (how many distinct runs)
        run_count = len(group.trajectory_ids)
        if run_count > 1:
            text.append(f"in {run_count} runs", style=c.fg_muted)
            text.append("  ")

        # Relative time from trajectory map (if available)
        best_time = self._best_time_for_group(group)
        if best_time:
            text.append(_relative_time(best_time), style=c.fg_muted)

        return text

    def _best_time_for_group(self, group: ViolationGroup) -> datetime | None:
        """Get the most recent trajectory time for a group."""
        if not self.trajectory_times:
            return None
        times = [
            self.trajectory_times[tid]
            for tid in group.trajectory_ids
            if tid in self.trajectory_times
        ]
        return max(times) if times else None

    def _render_group_detail(self, group: ViolationGroup) -> list[Text]:
        """Render 2-3 inline detail lines for the selected violation group."""
        c = get_theme_colors(self.app)
        lines: list[Text] = []

        # Line 1: Policy + agent
        line1 = Text()
        line1.append("   \u251c\u2500 ", style=c.fg_dim)
        if group.policy_description:
            line1.append(group.policy_description, style=c.fg)
        elif group.policy_id:
            line1.append(f"Policy: {group.policy_id}", style=c.fg)
        else:
            line1.append("Policy: unknown", style=c.fg_dim)
        line1.append("  Agent: ", style=c.fg_dim)
        line1.append(group.agent_name, style=c.fg)
        line1.append("  ", style="")
        line1.append("[\u23ce] view trajectory", style=c.fg_muted)
        line1.append("  ", style="")
        line1.append("[a] go to agent", style=c.fg_muted)
        lines.append(line1)

        # Line 2: Full reason
        line2 = Text()
        line2.append("   \u2514\u2500 ", style=c.fg_dim)
        reason = group.reason or "No reason provided"
        line2.append(f'"{reason}"', style=c.fg_secondary)
        lines.append(line2)

        return lines

    def on_click(self, event: Click) -> None:
        """Handle mouse click: first click selects, second click opens."""
        visible = self._visible_violations
        for i, widget in enumerate(self._row_widgets):
            if event.widget is widget:
                if i == self._selected_index:
                    # Already selected: open it
                    if i < len(visible):
                        self.post_message(self.ViolationSelected(visible[i].records[0]))
                else:
                    # Select this row
                    self._selected_index = i
                    self._rebuild()
                self.focus()
                event.stop()
                return

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        visible = self._visible_violations
        if visible and self._selected_index < len(visible) - 1:
            self._selected_index += 1
            self._rebuild()

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        if self._selected_index > 0:
            self._selected_index -= 1
            self._rebuild()

    def action_select(self) -> None:
        """Select the current violation (open adjudication detail)."""
        visible = self._visible_violations
        if visible and 0 <= self._selected_index < len(visible):
            self.post_message(
                self.ViolationSelected(visible[self._selected_index].records[0])
            )

    def action_jump_to_agent(self) -> None:
        """Jump to the agent detail screen for the selected violation."""
        visible = self._visible_violations
        if visible and 0 <= self._selected_index < len(visible):
            group = visible[self._selected_index]
            self.post_message(self.AgentJumpRequested(group.agent_id))
