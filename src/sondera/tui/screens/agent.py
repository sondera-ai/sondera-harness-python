from __future__ import annotations

import asyncio
import contextlib

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from sondera.tui.colors import get_theme_colors
from sondera.tui.events import correlate_events, parse_ts
from sondera.types import (
    Agent,
    Decision,
    Trajectory,
    TrajectoryEventStream,
)

from ..ai.panel import AskPanel
from ..mixins import SectionNavMixin
from ..widgets.pagination_bar import PaginationBar
from ..widgets.trajectory_feed import TrajectoryFeed, _count_violations, _is_stale
from .trajectory import TrajectoryScreen


class AgentScreen(SectionNavMixin, Screen):
    app: "sondera.tui.app.SonderaApp"  # type: ignore[name-defined]  # noqa: UP037, F821
    """A screen for displaying agent details and trajectories."""

    PAGE_SIZE = 20

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("down", "cursor_down", "Navigate", key_display="\u2191/\u2193"),
        Binding("up", "cursor_up", show=False),
        Binding("j", "vim_down", show=False),
        Binding("k", "vim_up", show=False),
        Binding("enter", "select_trajectory", "Open"),
        Binding("left", "page_prev", "Page", key_display="\u2190/\u2192"),
        Binding("right", "page_next", show=False),
        Binding("[", "page_prev", show=False),
        Binding("]", "page_next", show=False),
        Binding("i", "toggle_detail", "Info"),
        Binding("f", "filter_failed", "Failed"),
        Binding("d", "filter_denied", "Denied"),
        Binding("a", "filter_running", "Running"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
        Binding("tab", "next_section", show=False),
        Binding("shift+tab", "prev_section", show=False),
        Binding("slash", "noop", show=False),
        Binding("ctrl+grave_accent", "ask", "AI", key_display="ctrl+`"),
    ]

    def action_back(self) -> None:
        """Cancel AI stream if active, otherwise pop screen."""
        if self.app._ask_state.stream.is_streaming:
            with contextlib.suppress(Exception):
                self.query_one("#ask-panel", AskPanel).cancel_stream()
            return
        self.app.pop_screen()

    def action_noop(self) -> None:
        """Consume key so it doesn't bubble to the app."""

    def action_toggle_detail(self) -> None:
        """Toggle expanded agent detail (description + goal)."""
        self._show_detail = not self._show_detail
        self._update_summary()

    def _toggle_filter(self, name: str) -> None:
        """Toggle a status filter on/off and refresh the display."""
        if self._status_filter == name:
            self._status_filter = None
        else:
            self._status_filter = name
        self._apply_filter()
        feed = self.query_one("#trajectory-feed", TrajectoryFeed)
        feed.filter_label = self._status_filter or ""
        self._show_page(1)

    def action_filter_failed(self) -> None:
        self._toggle_filter("failed")

    def action_filter_denied(self) -> None:
        self._toggle_filter("denied")

    def action_filter_running(self) -> None:
        self._toggle_filter("running")

    def _matches_filter(self, t: Trajectory) -> bool:
        """Check if a trajectory matches the active filter."""
        f = self._status_filter
        if f is None:
            return True
        status = str(t.status or "unknown").lower()
        if f == "failed":
            return status == "failed"
        if f == "running":
            return status in {"running", "pending"} and not _is_stale(t)
        if f == "denied":
            denied, _ = _count_violations(t)
            return denied > 0
        return True

    def _apply_filter(self) -> None:
        """Rebuild display list from current filter."""
        if self._status_filter is None:
            self._display_trajectories = self._all_trajectories
            self._display_to_global = list(range(len(self._all_trajectories)))
        else:
            pairs = [
                (i, t)
                for i, t in enumerate(self._all_trajectories)
                if self._matches_filter(t)
            ]
            self._display_to_global = [i for i, _ in pairs]
            self._display_trajectories = [t for _, t in pairs]

    def __init__(
        self,
        agent: Agent,
        *,
        denied_count: int = 0,
        awaiting_count: int = 0,
        total_trajectories: int = 0,
    ):
        super().__init__()
        self.agent = agent
        self._denied_count = denied_count
        self._awaiting_count = awaiting_count
        self._total_trajectories = total_trajectories
        self._active_count = 0
        self._show_detail = False
        self._status_filter: str | None = None  # None | "failed" | "denied" | "running"
        self._policy_map: dict[str, str] = {}  # policy_id -> description
        # All trajectories (globally sorted), used for client-side pagination
        self._all_trajectories: list[Trajectory] = []
        # Filtered view: indices into _all_trajectories
        self._display_trajectories: list[Trajectory] = []
        self._display_to_global: list[int] = []
        self._current_page = 1
        # Visible slice for the current page
        self.trajectories: list[Trajectory] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="agent-summary")
        yield Static("\u2500" * 200, classes="dashboard-sep")
        yield TrajectoryFeed(id="trajectory-feed")
        yield Static("\u2500" * 200, classes="dashboard-sep")
        yield AskPanel(id="ask-panel")
        yield Footer()

    def _render_summary(self) -> Text:
        """Render the agent summary: compact 2-row layout, expandable detail."""
        c = get_theme_colors(self.app)
        agent = self.agent
        text = Text()

        # Row 1: name + provider + stats
        text.append(agent.id, style=f"bold {c.fg}")
        if agent.provider:
            text.append("  ")
            text.append(agent.provider, style=c.fg_muted)
        text.append("  ")
        if self._active_count > 0:
            text.append(f"● {self._active_count} running", style=f"bold {c.primary}")
            text.append("  ")
        total = self._total_trajectories
        if total > 0:
            text.append(f"{total} trajectories", style=c.fg)
            text.append("  ")
        if self._denied_count > 0:
            text.append(f"\u2717 {self._denied_count} denied", style=f"bold {c.error}")
            text.append("  ")
        if self._awaiting_count > 0:
            text.append(
                f"\u26a0 {self._awaiting_count} escalated",
                style=f"bold {c.warning}",
            )
            text.append("  ")
        if self._denied_count == 0 and self._awaiting_count == 0 and total > 0:
            text.append("\u2713 clean", style=c.success)

        # Row 2: policies
        if self._policy_map:
            text.append("\n")
            names = ", ".join(d if d else pid for pid, d in self._policy_map.items())
            label = "Policy" if len(self._policy_map) == 1 else "Policies"
            text.append(f"{label}: ", style=c.fg_muted)
            text.append(names, style=c.fg)

        return text

    def _update_summary(self) -> None:
        """Re-render the summary with current stats."""
        with contextlib.suppress(NoMatches):
            self.query_one("#agent-summary", Static).update(self._render_summary())

    def _recolor(self) -> None:
        """Re-render all Rich Text content with current theme colors."""
        self._update_summary()
        try:
            feed = self.query_one("#trajectory-feed", TrajectoryFeed)
            feed._rebuild()
        except Exception:
            pass
        with contextlib.suppress(Exception):
            self.query_one("#ask-panel", AskPanel)._recolor()

    def on_mount(self) -> None:
        """Initialize the screen."""
        self.sub_title = f"Agent: {self.agent.id}"
        self._update_summary()
        feed = self.query_one("#trajectory-feed", TrajectoryFeed)
        feed.denied_count = self._denied_count
        feed.awaiting_count = self._awaiting_count
        feed.focus()
        self.load_trajectories()
        self._fetch_full_agent()
        # Generate contextual suggestion for agent detail
        from sondera.tui.ai.panel import AskPanel

        with contextlib.suppress(Exception):
            self.query_one("#ask-panel", AskPanel).refresh_suggestion()

    @work(exclusive=True, group="agent-detail-fetch")
    async def _fetch_full_agent(self) -> None:
        """Fetch the full agent via get_agent()."""
        try:
            full = await self.app.harness.get_agent(self.agent.id)
            if full:
                self.agent = full
                self._update_summary()
        except Exception:
            pass

    @work(exclusive=True)
    async def load_trajectories(self) -> None:
        """Fetch all trajectories, sort by created_at desc, paginate client-side."""
        all_trajectories: list[Trajectory] = []
        page_token = ""
        while True:
            try:
                page, next_token = await self.app.harness.list_trajectories(
                    agent_id=self.agent.id,
                    page_size=250,
                    page_token=page_token,
                )
            except Exception as e:
                if not all_trajectories:
                    self.notify(f"Failed to load: {e}", severity="error")
                    return
                break
            all_trajectories.extend(page)
            if not next_token:
                break
            page_token = next_token

        # Sort globally by most recent activity descending
        all_trajectories.sort(key=lambda t: parse_ts(t.update_time), reverse=True)

        self._all_trajectories = all_trajectories
        self._total_trajectories = len(all_trajectories)

        # Update active count (exclude stale)
        self._active_count = sum(
            1
            for t in all_trajectories
            if str(t.status or "unknown").lower() in {"running", "pending"}
            and not _is_stale(t)
        )
        self._apply_filter()
        self._update_summary()

        # Show first page
        self._show_page(1)

        # Open a live stream for this agent now that the initial list is loaded
        self._stream_trajectory_events()

    def _show_page(self, page: int) -> None:
        """Display a client-side page immediately and enrich in background."""
        self._current_page = page
        display = self._display_trajectories
        total = len(display)
        total_pages = max(1, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        start = (page - 1) * self.PAGE_SIZE
        end = start + self.PAGE_SIZE
        page_slice = display[start:end]
        # Map page indices to _all_trajectories indices for enrichment
        global_indices = self._display_to_global[start:end]

        self.trajectories = page_slice
        feed = self.query_one("#trajectory-feed", TrajectoryFeed)
        feed.trajectories = page_slice

        bar = feed.query_one("#trajectories-pagination", PaginationBar)
        bar.set_total_items(total)
        bar.set_client_page(page, total_pages)

        # Enrich visible page in background (fills in step counts, policies)
        self._enrich_page(page_slice, global_indices, feed)

    @work(exclusive=True, group="agent-enrich-turns")
    async def _enrich_page(
        self,
        page_trajectories: list,
        global_indices: list[int],
        feed: TrajectoryFeed,
    ) -> None:
        """Fetch full trajectories for the current page, updating rows in-place."""
        from textual.worker import get_current_worker

        worker = get_current_worker()

        def _extract_policies(traj: Trajectory) -> None:
            """Extract policy metadata from trajectory events."""
            if not traj.events:
                return
            steps = correlate_events(traj.events)
            for step in steps:
                for p in step.policies:
                    if p.policy_id is not None:
                        self._policy_map[p.policy_id] = p.description or ""

        async def _enrich_one(i: int) -> None:
            if worker.is_cancelled:
                return

            traj = page_trajectories[i]
            gi = global_indices[i]

            # Skip already-enriched trajectories (e.g. paginating back)
            if traj.events:
                feed.update_enrichment(i, traj)
                _extract_policies(traj)
                return

            try:
                result = await self.app._throttled(
                    self.app.harness.get_trajectory(traj.name)
                )
                if worker.is_cancelled:
                    return
                if result:
                    self._all_trajectories[gi] = result
                    feed.update_enrichment(i, result)
                    _extract_policies(result)
                    self._update_summary()
                else:
                    feed.mark_enrichment_failed(i)
            except Exception:
                feed.mark_enrichment_failed(i)

        # Process already-cached items synchronously first (no network needed)
        to_fetch: list[int] = []
        for i in range(len(page_trajectories)):
            traj = page_trajectories[i]
            if traj.events:
                feed.update_enrichment(i, traj)
                _extract_policies(traj)
            else:
                to_fetch.append(i)

        if not to_fetch:
            return

        # Fetch all uncached trajectories concurrently (semaphore limits to 3 in-flight)
        await asyncio.gather(
            *[_enrich_one(i) for i in to_fetch], return_exceptions=True
        )

    @work(exclusive=True, group="agent-trajectory-stream")
    async def _stream_trajectory_events(self) -> None:
        """Subscribe to live trajectory events for this agent and update the feed.

        Opens a :class:`TrajectoryEventStream` filtered to this agent.  For each
        :class:`TrajectoryEventNotification` received the matching trajectory row is
        refreshed in-place; brand-new trajectories are prepended to the list.
        """
        from textual.worker import get_current_worker

        worker = get_current_worker()
        filter_expr = f'agent = "{self.agent.id}"'
        try:
            stream: TrajectoryEventStream = await self.app.harness.stream_trajectories(
                filter=filter_expr
            )
        except Exception:
            return

        async for notification in stream:
            if worker.is_cancelled:
                break

            traj_id = notification.trajectory_id  # type: ignore[union-attr]
            if not traj_id:
                continue

            try:
                updated: Trajectory | None = await self.app.harness.get_trajectory(
                    traj_id
                )
            except Exception:
                continue

            if updated is None:
                continue

            existing_idx = next(
                (i for i, t in enumerate(self._all_trajectories) if t.name == traj_id),
                None,
            )
            is_new = existing_idx is None
            if is_new:
                self._all_trajectories.insert(0, updated)
                self._total_trajectories += 1
            else:
                self._all_trajectories[existing_idx] = updated

            self._apply_filter()
            self._update_summary()

            try:
                feed = self.query_one("#trajectory-feed", TrajectoryFeed)
            except Exception:
                continue

            page_idx = next(
                (i for i, t in enumerate(self.trajectories) if t.name == traj_id),
                None,
            )
            if page_idx is not None:
                # Targeted row update — preserves scroll position and cursor
                self.trajectories[page_idx] = updated
                feed.update_enrichment(page_idx, updated)
            elif is_new:
                # New trajectory may belong on the current page — refresh it
                self._show_page(self._current_page)

    def action_refresh(self) -> None:
        """Re-fetch trajectories and restart the live stream."""
        try:
            feed = self.query_one("#trajectory-feed", TrajectoryFeed)
            feed.query_one("#trajectories-pagination", PaginationBar).reset()
        except Exception:
            pass
        self.load_trajectories()
        self._fetch_full_agent()

    @staticmethod
    def _first_denied_step(trajectory: Trajectory) -> int | None:
        """Return the index of the first denied EventStep, or None."""
        if not trajectory.events:
            return None
        steps = correlate_events(trajectory.events)
        for i, step in enumerate(steps):
            if step.decision == Decision.Deny:
                return i
        return None

    def action_select_trajectory(self) -> None:
        """Select the current trajectory and push TrajectoryScreen."""
        feed = self.query_one("#trajectory-feed", TrajectoryFeed)
        trajectory = feed.get_selected_trajectory()
        if trajectory is None:
            self.notify("No trajectory selected")
            return
        idx = feed._selected_index
        if 0 <= idx < len(self.trajectories):
            trajectory = self.trajectories[idx]
        if trajectory.events:
            initial = self._first_denied_step(trajectory)
            self.app.push_screen(TrajectoryScreen(trajectory, initial_step=initial))
        else:
            self._open_trajectory(trajectory.name)

    @work
    async def _open_trajectory(self, trajectory_id: str) -> None:
        """Fetch full trajectory on-demand (fallback before enrichment completes)."""
        try:
            traj = await self.app.harness.get_trajectory(trajectory_id)
            if traj:
                initial = self._first_denied_step(traj)
                self.app.push_screen(TrajectoryScreen(traj, initial_step=initial))
            else:
                self.notify("Trajectory not found", severity="error")
        except Exception as e:
            self.notify(f"Failed to load trajectory: {e}", severity="error")

    def on_pagination_bar_page_requested(
        self, event: PaginationBar.PageRequested
    ) -> None:
        # Client-side pagination: page_token is the page number as string
        try:
            page = int(event.page_token)
        except (ValueError, TypeError):
            page = 1
        self._show_page(page)

    def on_trajectory_feed_trajectory_selected(
        self, event: TrajectoryFeed.TrajectorySelected
    ) -> None:
        self.action_select_trajectory()

    def action_page_next(self) -> None:
        try:
            feed = self.query_one("#trajectory-feed", TrajectoryFeed)
            bar = feed.query_one("#trajectories-pagination", PaginationBar)
            if bar.has_next:
                bar._go_next()
        except Exception:
            pass

    def action_page_prev(self) -> None:
        try:
            feed = self.query_one("#trajectory-feed", TrajectoryFeed)
            bar = feed.query_one("#trajectories-pagination", PaginationBar)
            if bar.has_prev:
                bar._go_prev()
        except Exception:
            pass

    def _section_cycle(self) -> list:
        """Ordered focusable sections for tab cycling."""
        sections: list = []
        with contextlib.suppress(Exception):
            sections.append(self.query_one("#trajectory-feed", TrajectoryFeed))
        with contextlib.suppress(Exception):
            sections.append(self.query_one("#ask-panel", AskPanel))
        return sections

    def action_ask(self) -> None:
        """Toggle the AI ask panel open/closed."""
        with contextlib.suppress(Exception):
            panel = self.query_one("#ask-panel", AskPanel)
            panel.toggle_response()

    def on_ask_panel_dismissed(self, _msg: AskPanel.Dismissed) -> None:
        """Restore focus when ask panel closes."""
        with contextlib.suppress(Exception):
            self.query_one("#trajectory-feed", TrajectoryFeed).focus()

    def on_screen_resume(self) -> None:
        """Sync AskPanel state when returning to this screen."""
        with contextlib.suppress(Exception):
            self.query_one("#ask-panel", AskPanel)._sync_from_state()

    def action_cursor_down(self) -> None:
        feed = self.query_one("#trajectory-feed", TrajectoryFeed)
        feed.action_cursor_down()

    def action_cursor_up(self) -> None:
        feed = self.query_one("#trajectory-feed", TrajectoryFeed)
        feed.action_cursor_up()
