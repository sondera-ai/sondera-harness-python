import asyncio
import contextlib
import json
import time
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from textual import events, work
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.screen import Screen
from textual.theme import Theme
from textual.widgets import Footer, Header, Static

import sondera.settings as _settings
from sondera.harness import Harness, SonderaRemoteHarness
from sondera.tui.ai.panel import AskInput, AskPanel, AskSessionState
from sondera.tui.colors import ThemeColors, get_theme_colors
from sondera.tui.events import correlate_events, parse_ts, violations_from_events
from sondera.tui.mixins import SectionNavMixin
from sondera.tui.screens import AgentScreen, TrajectoryScreen
from sondera.tui.widgets.agents_feed import AgentsFeed, AgentStatus
from sondera.tui.widgets.dashboard_header import DashboardHeader
from sondera.tui.widgets.trajectory_feed import _is_stale
from sondera.tui.widgets.violations_feed import ViolationsFeed
from sondera.types import Adjudicated, Agent, Decision, Event, TrajectoryEventStream


def _agent_id(agent: Agent | str | None) -> str:
    """Extract the agent ID string from an Agent object or a plain resource name."""
    if agent is None:
        return ""
    return agent if isinstance(agent, str) else agent.id


def _ensure_agent(agent: Agent | str | None) -> Agent | None:
    """Coerce a plain agent resource-name string into a minimal Agent object."""
    if agent is None:
        return None
    if isinstance(agent, str):
        return Agent(id=agent, provider="unknown")
    return agent


sondera_dark = Theme(
    name="sondera-dark",
    primary="#81DDB4",
    secondary="#81DDB4",
    accent="#81DDB4",
    foreground="#EAEAEA",
    background="#06110B",
    success="#A3BE8C",
    warning="#EBCB8B",
    error="#BF616A",
    surface="#06110B",
    panel="#054C53",
    dark=True,
    variables={
        "scrollbar": "#054C53",
        "scrollbar-background": "#06110B",
    },
)

sondera_light = Theme(
    name="sondera-light",
    primary="#569378",
    secondary="#569378",
    accent="#569378",
    foreground="#06110B",
    background="#EAEAEA",
    success="#4D6A3A",
    warning="#7A6835",
    error="#BF616A",
    surface="#EAEAEA",
    panel="#D6D6D6",
    dark=False,
    variables={
        "scrollbar": "#D6D6D6",
        "scrollbar-background": "#EAEAEA",
    },
)


def _compute_agent_status(
    agent,
    trajectories: list,
    denied_count: int,
    denied_traj_count: int,
    awaiting_count: int,
    has_more_trajectories: bool = False,
) -> AgentStatus:
    """Derive an AgentStatus from a trajectory list and pre-computed violation counts."""
    running = sum(
        1
        for t in trajectories
        if str(t.status or "unknown").lower() in {"running", "pending"}
        and not _is_stale(t)
    )
    failed = sum(
        1 for t in trajectories if str(t.status or "unknown").lower() == "failed"
    )
    completed = sum(
        1 for t in trajectories if str(t.status or "unknown").lower() == "completed"
    )
    if running > 0:
        status = "live"
    elif failed > 0:
        status = "errored"
    elif trajectories:
        status = "idle"
    else:
        status = "off"
    last_active = max(
        (max(parse_ts(t.update_time), parse_ts(t.create_time)) for t in trajectories),
        default=None,
    )
    sorted_trajs = sorted(
        trajectories, key=lambda t: parse_ts(t.update_time), reverse=True
    )
    last_traj_status = None
    if sorted_trajs:
        latest = sorted_trajs[0]
        ls = str(latest.status or "unknown").lower()
        last_traj_status = (
            "stale" if ls in {"running", "pending"} and _is_stale(latest) else ls
        )
    return AgentStatus(
        agent=agent,
        status=status,
        live_count=running,
        total_trajectories=len(trajectories),
        has_more_trajectories=has_more_trajectories,
        denied_count=denied_count,
        denied_trajectory_count=denied_traj_count,
        awaiting_count=awaiting_count,
        last_active=last_active,
        completed_count=completed,
        failed_count=failed,
        last_trajectory_status=last_traj_status,
    )


class SonderaApp(SectionNavMixin, App):
    """Mission Control dashboard for Sondera governance monitoring."""

    TITLE = "Sondera Harness"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("1", "show_dashboard", "Home", priority=True, show=False),
        Binding("down", "cursor_down", "Navigate", key_display="\u2191/\u2193"),
        Binding("up", "cursor_up", show=False),
        Binding("j", "vim_down", show=False),
        Binding("k", "vim_up", show=False),
        Binding("enter", "select_item", "Open", key_display="\u23ce"),
        Binding("tab", "next_section", "Section", key_display="tab"),
        Binding("shift+tab", "prev_section", show=False),
        Binding(
            "slash",
            "filter_agents",
            "Filter",
            key_display="/",
        ),
        Binding("a", "jump_to_agent", "Agent", show=False),
        Binding("escape", "escape_action", show=False),
        Binding("ctrl+grave_accent", "ask", "AI", key_display="ctrl+`"),
        Binding("s", "screensaver", show=False),
    ]

    SCREENS = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._all_trajectories: list = []
        self._agents: list = []
        self._agents_map: dict[str, str] = {}
        self._adjudications: list = []
        self._seen_adj_ids: set[str] = set()
        self._agent_statuses: list = []
        self._agents_by_id: dict = {}
        self._ask_state = AskSessionState()
        self._last_activity = time.monotonic()

        # Harness is created lazily on first use to avoid blocking the
        # constructor with an eager gRPC connection attempt.
        self._harness: Harness | None = None

    PAGE_SIZE = 20
    _grpc_sem: asyncio.Semaphore | None = None

    @property
    def harness(self) -> Harness:
        """Lazily create the harness on first access."""
        if self._harness is None:
            self._harness = SonderaRemoteHarness(
                sondera_harness_endpoint=_settings.SETTINGS.sondera_harness_endpoint,
                sondera_api_key=_settings.SETTINGS.sondera_api_token,
            )
        return self._harness

    @property
    def _semaphore(self) -> asyncio.Semaphore:
        if self._grpc_sem is None:
            self._grpc_sem = asyncio.Semaphore(10)
        return self._grpc_sem

    async def _throttled(self, coro):
        async with self._semaphore:
            return await coro

    @property
    def theme_colors(self) -> ThemeColors:
        """Return the semantic color palette for the active theme."""
        return get_theme_colors(self)

    def get_css_variables(self) -> dict[str, str]:
        """Inject custom CSS variables into the theme."""
        variables = super().get_css_variables()
        variables["prompt-blue"] = self.theme_colors.prompt_blue
        variables["model-muted"] = self.theme_colors.fg_secondary
        return variables

    _PREFS_PATH = Path("~/.sondera/tui_prefs.json").expanduser()

    def _load_theme_pref(self) -> str:
        """Load persisted theme name, defaulting to sondera-dark."""
        with contextlib.suppress(Exception):
            data = json.loads(self._PREFS_PATH.read_text())
            name = data.get("theme", "sondera-dark")
            if name in self._registered_themes:
                return name
        return "sondera-dark"

    def _save_theme_pref(self, theme_name: str) -> None:
        """Persist theme choice to ~/.sondera/tui_prefs.json."""
        with contextlib.suppress(Exception):
            self._PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
            data: dict = {}
            with contextlib.suppress(Exception):
                data = json.loads(self._PREFS_PATH.read_text())
            data["theme"] = theme_name
            self._PREFS_PATH.write_text(json.dumps(data))

    def watch_theme(self, theme_name: str) -> None:
        """Rebuild Rich Text content and persist theme choice."""
        # Dashboard widgets
        for cls in (ViolationsFeed, AgentsFeed):
            with contextlib.suppress(Exception):
                self.query_one(cls)._rebuild()
        # DashboardHeader uses render() so just refresh it
        with contextlib.suppress(Exception):
            self.query_one(DashboardHeader).refresh()
        # Dashboard AskPanel
        with contextlib.suppress(Exception):
            self.query_one("#ask-panel", AskPanel)._recolor()
        # Pushed screens (TrajectoryScreen, AgentScreen)
        screen = self.screen
        recolor = getattr(screen, "_recolor", None)
        if recolor is not None:
            with contextlib.suppress(Exception):
                recolor()
        self._save_theme_pref(theme_name)

    def on_mount(self) -> None:
        self.register_theme(sondera_dark)
        self.register_theme(sondera_light)
        # Alphabetize the theme list in command palette
        self._registered_themes = dict(sorted(self._registered_themes.items()))
        self.theme = self._load_theme_pref()
        self.update_dataset()
        self.set_interval(5.0, self._check_idle)

    def _check_idle(self) -> None:
        """Trigger screensaver if idle timeout has elapsed."""
        timeout = _settings.SETTINGS.screensaver_timeout
        if timeout <= 0:
            return
        # Don't launch if screensaver is already showing
        from sondera.tui.screens.screensaver import ScreensaverScreen

        if isinstance(self.screen, ScreensaverScreen):
            return
        if time.monotonic() - self._last_activity >= timeout:
            self.action_screensaver()

    def _bump_activity(self) -> None:
        self._last_activity = time.monotonic()

    def on_key(self, _event: events.Key) -> None:
        """Any key press resets the idle timer."""
        self._last_activity = time.monotonic()

    def on_click(self, _event: events.Click) -> None:
        """Any click resets the idle timer."""
        self._last_activity = time.monotonic()

    def pop_screen(self):
        """Pop a screen and sync AskPanel state."""
        self._bump_activity()
        result = super().pop_screen()
        # Sync AskPanel on the now-visible screen with shared state
        with contextlib.suppress(Exception):
            self.screen.query_one("#ask-panel", AskPanel)._sync_from_state()
        return result

    def compose(self) -> ComposeResult:
        yield Header()
        yield DashboardHeader(id="header")
        yield Static("\u2500" * 200, id="sep-1", classes="dashboard-sep")
        yield ViolationsFeed(id="violations-feed")
        yield Static("\u2500" * 200, id="sep-2", classes="dashboard-sep")
        yield AgentsFeed(id="agents-feed")
        yield Static("\u2500" * 200, id="sep-3", classes="dashboard-sep")
        yield AskPanel(id="ask-panel")
        yield Footer()

    @work(exclusive=True)
    async def update_dataset(self) -> None:
        """Load dashboard data on startup in two phases for fast initial render."""
        # Phase 1: Agents + adjudications in parallel
        try:
            agents_result, adj_result = await asyncio.gather(
                self._throttled(self.harness.list_agents(page_size=250)),
                self._throttled(self.harness.list_adjudications(page_size=250)),
            )
        except Exception as e:
            self.notify(f"{e}", severity="error", timeout=5)
            return

        agents, agents_next = agents_result
        try:
            while agents_next:
                more_agents, agents_next = await self._throttled(
                    self.harness.list_agents(page_size=250, page_token=agents_next)
                )
                agents.extend(more_agents)
        except Exception:
            pass

        adj_events, _adj_next = adj_result

        agents_map = {agent.id: agent.id for agent in agents}
        self._agents = agents
        self._agents_map = agents_map
        self._agents_by_id = {agent.id: agent for agent in agents}
        self._adjudications = adj_events  # list[Event] wrapping Adjudicated
        self._seen_adj_ids = {ev.event_id for ev in adj_events if ev.event_id}

        # Build violation records from adjudication events
        violation_records = violations_from_events(adj_events)

        # Update violations feed
        violations_feed = self.query_one(ViolationsFeed)
        violations_feed.agents_map = agents_map
        violations_feed.violations = violation_records

        # Update header counts
        header = self.query_one(DashboardHeader)
        header.violation_count = sum(
            1 for v in violation_records if v.decision == Decision.Deny
        )
        header.awaiting_count = sum(
            1 for v in violation_records if v.decision == Decision.Escalate
        )
        header.total_agents = len(agents)

        # Auto-focus the most relevant feed
        if violation_records:
            violations_feed.focus()
        else:
            self.query_one(AgentsFeed).focus()
        with contextlib.suppress(Exception):
            self.query_one("#ask-panel", AskPanel).refresh_suggestion()

        # Phase 2: Trajectories in background (for agent status)
        self._load_trajectories()

    @work(exclusive=True, group="load-trajectories")
    async def _load_trajectories(self) -> None:
        """Fetch trajectories for all agents, then render the agents feed once."""
        from textual.worker import get_current_worker

        worker = get_current_worker()
        agents = self._agents

        # Fetch all agents' trajectories concurrently (semaphore limits to 3 in-flight)
        first_page_tasks = [
            self._throttled(
                self.harness.list_trajectories(agent_id=agent.id, page_size=50)
            )
            for agent in agents
        ]
        first_results = await asyncio.gather(*first_page_tasks, return_exceptions=True)
        if worker.is_cancelled:
            return

        all_trajectories = []

        # Build per-agent denied/awaiting counts from adjudication Events
        agent_denied: Counter[str] = Counter()
        agent_awaiting: Counter[str] = Counter()
        agent_denied_trajectories: dict[str, set[str]] = {}
        for adj_ev in self._adjudications:
            adj_payload = adj_ev.event  # Adjudicated
            agent_aid = _agent_id(adj_ev.agent)
            traj_tid = adj_ev.trajectory_id or ""
            if (
                isinstance(adj_payload, Adjudicated)
                and adj_payload.decision == Decision.Deny
            ):
                agent_denied[agent_aid] += 1
                agent_denied_trajectories.setdefault(agent_aid, set()).add(traj_tid)
            elif (
                isinstance(adj_payload, Adjudicated)
                and adj_payload.decision == Decision.Escalate
            ):
                agent_awaiting[agent_aid] += 1

        # Build trajectory timestamp map for violations feed
        trajectory_times: dict[str, datetime] = {}

        agent_statuses: list[AgentStatus] = []
        live_count = 0
        problem_agent_count = 0

        for agent, result in zip(agents, first_results, strict=True):
            denied = agent_denied[agent.id]
            awaiting = agent_awaiting[agent.id]
            denied_traj_count = len(agent_denied_trajectories.get(agent.id, set()))

            if isinstance(result, BaseException):
                if denied > 0 or awaiting > 0:
                    problem_agent_count += 1
                agent_statuses.append(
                    _compute_agent_status(
                        agent=agent,
                        trajectories=[],
                        denied_count=denied,
                        denied_traj_count=denied_traj_count,
                        awaiting_count=awaiting,
                    )
                )
                continue

            trajectories, next_token = result
            all_trajectories.extend(trajectories)

            # Build trajectory time map
            for t in trajectories:
                trajectory_times[t.name] = max(
                    parse_ts(t.update_time), parse_ts(t.create_time)
                )

            if denied > 0 or awaiting > 0:
                problem_agent_count += 1

            a_status = _compute_agent_status(
                agent=agent,
                trajectories=trajectories,
                denied_count=denied,
                denied_traj_count=denied_traj_count,
                awaiting_count=awaiting,
                has_more_trajectories=bool(next_token),
            )
            if a_status.status == "live":
                live_count += 1
            agent_statuses.append(a_status)

        if worker.is_cancelled:
            return

        # Resolve exact counts for agents showing "50+"
        overflow = [
            (i, a) for i, a in enumerate(agent_statuses) if a.has_more_trajectories
        ]
        if overflow:
            count_tasks = [
                self._throttled(
                    self.harness.analyze_trajectories(
                        agent_id=a.agent.id, analytics=["trajectory_count"]
                    )
                )
                for _, a in overflow
            ]
            count_results = await asyncio.gather(*count_tasks, return_exceptions=True)
            if worker.is_cancelled:
                return
            for (_, a), result in zip(overflow, count_results, strict=True):
                if isinstance(result, BaseException):
                    continue
                count = result.get("trajectory_count", 0)
                if count:
                    a.total_trajectories = count
                    a.has_more_trajectories = False

        all_trajectories.sort(key=lambda t: parse_ts(t.create_time), reverse=True)
        self._all_trajectories = all_trajectories

        # Sort by most recently active at top
        _epoch = datetime(2000, 1, 1, tzinfo=UTC)
        agent_statuses.sort(key=lambda a: -(a.last_active or _epoch).timestamp())

        # Store for context extraction (AI Assist)
        self._agent_statuses = agent_statuses

        # Single update: render agents feed once with all data
        agents_feed = self.query_one(AgentsFeed)
        agents_feed.agents = agent_statuses

        # Update header
        header = self.query_one(DashboardHeader)
        header.live_count = live_count
        header.problem_agent_count = problem_agent_count

        # Update violations feed with trajectory timestamps
        violations_feed = self.query_one(ViolationsFeed)
        violations_feed.trajectory_times = trajectory_times

        # Begin streaming live updates from this point forward
        self._stream_dashboard_events()

    @work(exclusive=True, group="dashboard-stream")
    async def _stream_dashboard_events(self) -> None:
        """Stream all trajectory events and apply incremental updates to dashboard state."""
        from textual.worker import get_current_worker

        worker = get_current_worker()
        try:
            stream: TrajectoryEventStream = await self.harness.stream_trajectories()
        except Exception:
            return

        async for notification in stream:
            if worker.is_cancelled:
                break
            traj_id = notification.trajectory_id  # type: ignore[union-attr]
            if not traj_id:
                continue
            event = notification.event  # type: ignore[union-attr]
            if event is not None:
                self._ingest_adjudication(event)
            await self._refresh_agent_from_trajectory(traj_id)

    def _ingest_adjudication(self, event: Event) -> None:
        """Append a Deny/Escalate adjudication event to state and refresh the violations feed."""
        if not isinstance(event.event, Adjudicated):
            return
        if event.event.decision not in (Decision.Deny, Decision.Escalate):
            return
        event_id = event.event_id or ""
        if event_id in self._seen_adj_ids:
            return
        self._seen_adj_ids.add(event_id)
        self._adjudications.append(event)

        violation_records = violations_from_events(self._adjudications)
        with contextlib.suppress(Exception):
            self.query_one(ViolationsFeed).violations = violation_records
        with contextlib.suppress(Exception):
            header = self.query_one(DashboardHeader)
            header.violation_count = sum(
                1 for v in violation_records if v.decision == Decision.Deny
            )
            header.awaiting_count = sum(
                1 for v in violation_records if v.decision == Decision.Escalate
            )

    async def _refresh_agent_from_trajectory(self, traj_id: str) -> None:
        """Fetch one trajectory, upsert it, and recompute its agent's dashboard row."""
        try:
            trajectory = await self._throttled(self.harness.get_trajectory(traj_id))
        except Exception:
            return
        if not trajectory:
            return

        raw_agent = trajectory.agent
        if not raw_agent:
            return
        agent = _ensure_agent(raw_agent)
        agent_id = _agent_id(raw_agent)

        # Upsert into _all_trajectories
        for i, t in enumerate(self._all_trajectories):
            if t.name == trajectory.name:
                self._all_trajectories[i] = trajectory
                break
        else:
            self._all_trajectories.append(trajectory)

        # All known trajectories for this agent
        agent_trajectories = [
            t for t in self._all_trajectories if _agent_id(t.agent) == agent_id
        ]

        # Per-agent violation counts from current adjudications
        denied_count = 0
        denied_traj_ids: set[str] = set()
        awaiting_count = 0
        for adj_ev in self._adjudications:
            if _agent_id(adj_ev.agent) != agent_id:
                continue
            adj_payload = adj_ev.event
            if isinstance(adj_payload, Adjudicated):
                if adj_payload.decision == Decision.Deny:
                    denied_count += 1
                    denied_traj_ids.add(adj_ev.trajectory_id or "")
                elif adj_payload.decision == Decision.Escalate:
                    awaiting_count += 1

        with contextlib.suppress(Exception):
            agents_feed = self.query_one(AgentsFeed)
            current = list(agents_feed.agents)
            has_more = next(
                (a.has_more_trajectories for a in current if a.agent.id == agent_id),
                False,
            )
            new_status = _compute_agent_status(
                agent=agent,
                trajectories=agent_trajectories,
                denied_count=denied_count,
                denied_traj_count=len(denied_traj_ids),
                awaiting_count=awaiting_count,
                has_more_trajectories=has_more,
            )
            for i, a in enumerate(current):
                if a.agent.id == agent_id:
                    current[i] = new_status
                    break
            else:
                current.append(new_status)
            _epoch = datetime(2000, 1, 1, tzinfo=UTC)
            current.sort(key=lambda a: -(a.last_active or _epoch).timestamp())
            agents_feed.agents = current

            header = self.query_one(DashboardHeader)
            header.live_count = sum(1 for a in current if a.status == "live")
            header.problem_agent_count = sum(
                1 for a in current if a.denied_count > 0 or a.awaiting_count > 0
            )
            self._agent_statuses = current

        # Update trajectory timestamps for the violations feed
        with contextlib.suppress(Exception):
            violations_feed = self.query_one(ViolationsFeed)
            times = dict(violations_feed.trajectory_times)
            for t in agent_trajectories:
                times[t.name] = max(parse_ts(t.update_time), parse_ts(t.create_time))
            violations_feed.trajectory_times = times

    # -- Navigation handlers --

    def on_violations_feed_violation_selected(
        self, msg: ViolationsFeed.ViolationSelected
    ) -> None:
        self._open_trajectory(
            msg.record.trajectory_id,
            jump_to_decision=msg.record.decision,
            step_index=msg.record.step_index,
        )

    def on_violations_feed_agent_jump_requested(
        self, msg: ViolationsFeed.AgentJumpRequested
    ) -> None:
        """Quick-jump to agent screen from a violation row."""
        agent = self._agents_by_id.get(msg.agent_id)
        if agent:
            # Find the matching agent status for denied/awaiting counts
            agents_feed = self.query_one(AgentsFeed)
            for a_status in agents_feed.agents:
                if a_status.agent.id == msg.agent_id:
                    self.push_screen(
                        AgentScreen(
                            a_status.agent,
                            denied_count=a_status.denied_count,
                            awaiting_count=a_status.awaiting_count,
                            total_trajectories=a_status.total_trajectories,
                        )
                    )
                    return
            # Fallback: use agent without status data
            self.push_screen(AgentScreen(agent))

    def on_agents_feed_agent_selected(self, msg: AgentsFeed.AgentSelected) -> None:
        status = msg.agent_status
        self.push_screen(
            AgentScreen(
                status.agent,
                denied_count=status.denied_count,
                awaiting_count=status.awaiting_count,
                total_trajectories=status.total_trajectories,
            )
        )

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        # Filter built-in commands (Textual sorts alphabetically)
        _HIDDEN = {"Maximize"}
        for cmd in super().get_system_commands(screen):
            if cmd.title not in _HIDDEN:
                yield cmd
        yield SystemCommand(
            "Configuration",
            "Configure Sondera platform and AI provider settings",
            self.action_open_config,
        )
        yield SystemCommand(
            "Dashboard",
            "Return to the main dashboard",
            self.action_show_dashboard,
        )
        yield SystemCommand(
            "Refresh",
            "Refresh data from Sondera platform",
            self.action_refresh,
        )
        yield SystemCommand(
            "Flying Agents",
            "Launch the Flying Agents screensaver",
            self.action_screensaver,
        )

    def action_open_config(self) -> None:
        """Open the configuration modal."""
        from sondera.tui.screens.config import ConfigModal

        self.push_screen(ConfigModal(), callback=self._on_config_result)

    def _on_config_result(self, changed: bool | None) -> None:
        """Reinitialize harness if config was saved."""
        if changed:
            self._harness = SonderaRemoteHarness(
                sondera_harness_endpoint=_settings.SETTINGS.sondera_harness_endpoint,
                sondera_api_key=_settings.SETTINGS.sondera_api_token,
            )
            self._bump_activity()  # Reset idle timer with new timeout
            self.update_dataset()
            self.notify("Configuration saved", timeout=3)

    def action_refresh(self) -> None:
        """Re-fetch all dashboard data and restart the live stream."""
        self._bump_activity()
        self.update_dataset()

    def action_screensaver(self) -> None:
        """Launch the screensaver."""
        from sondera.tui.screens.screensaver import ScreensaverScreen

        if isinstance(self.screen, ScreensaverScreen):
            return
        self.push_screen(ScreensaverScreen(self._agent_statuses))

    def action_show_dashboard(self) -> None:
        """Pop back to the dashboard."""
        while len(self.screen_stack) > 1:
            self.pop_screen()

    def _section_cycle(self) -> list:
        """Return the ordered list of focusable sections."""
        sections = []
        with contextlib.suppress(Exception):
            sections.append(self.query_one(ViolationsFeed))
        with contextlib.suppress(Exception):
            sections.append(self.query_one(AgentsFeed))
        with contextlib.suppress(Exception):
            sections.append(self.query_one("#ask-panel", AskPanel))
        return sections

    def _on_section_change(self) -> None:
        self._bump_activity()

    def action_filter_agents(self) -> None:
        """Toggle the agent search filter (type '/' if ask input is focused)."""
        try:
            ask_input = self.screen.query_one("#ask-input", AskInput)
            if ask_input.has_focus:
                ask_input.insert("/")
                return
        except Exception:
            pass
        with contextlib.suppress(Exception):
            agents_feed = self.query_one(AgentsFeed)
            agents_feed.action_show_filter()

    def action_jump_to_agent(self) -> None:
        """Jump to agent from selected violation."""
        feed = self._focused_feed()
        if isinstance(feed, ViolationsFeed):
            feed.action_jump_to_agent()

    def action_escape_action(self) -> None:
        """Escape on dashboard: cancel AI stream or close chat panel."""
        self._bump_activity()
        if self._ask_state.stream.is_streaming:
            with contextlib.suppress(Exception):
                self.query_one("#ask-panel", AskPanel).cancel_stream()
            return
        # Close chat panel if open
        with contextlib.suppress(Exception):
            panel = self.query_one("#ask-panel", AskPanel)
            if panel.has_response:
                panel.toggle_response()

    def action_ask(self) -> None:
        """Toggle the AI ask panel open/closed."""
        self._bump_activity()
        with contextlib.suppress(Exception):
            panel = self.query_one("#ask-panel", AskPanel)
            panel.toggle_response()

    def on_ask_panel_dismissed(self, _msg: AskPanel.Dismissed) -> None:
        """Restore focus when ask response is closed."""
        feed = self._focused_feed()
        if feed:
            feed.focus()

    def _focused_feed(self) -> ViolationsFeed | AgentsFeed | None:
        """Return whichever feed widget currently has focus."""
        for cls in (ViolationsFeed, AgentsFeed):
            with contextlib.suppress(Exception):
                w = self.query_one(cls)
                if w.has_focus or w.has_focus_within:
                    return w
        # Fallback: focus and return the first feed with content
        with contextlib.suppress(Exception):
            vf = self.query_one(ViolationsFeed)
            if vf.violations:
                vf.focus()
                return vf
        with contextlib.suppress(Exception):
            af = self.query_one(AgentsFeed)
            if af.agents:
                af.focus()
                return af
        return None

    def action_cursor_down(self) -> None:
        self._bump_activity()
        feed = self._focused_feed()
        if feed is None:
            return
        if isinstance(feed, ViolationsFeed):
            visible = feed._visible_violations
            if visible and feed._selected_index >= len(visible) - 1:
                # At bottom of violations: flow into agents
                agents_feed = self.query_one(AgentsFeed)
                if agents_feed.agents:
                    agents_feed._selected_index = 0
                    agents_feed.focus()
                    return
            feed.action_cursor_down()
        else:
            feed.action_cursor_down()

    def action_cursor_up(self) -> None:
        self._bump_activity()
        feed = self._focused_feed()
        if feed is None:
            return
        if isinstance(feed, AgentsFeed):
            if feed._selected_index <= 0:
                # At top of agents: flow into violations
                violations_feed = self.query_one(ViolationsFeed)
                visible = violations_feed._visible_violations
                if visible:
                    violations_feed._selected_index = len(visible) - 1
                    violations_feed.focus()
                    return
            feed.action_cursor_up()
        else:
            feed.action_cursor_up()

    def action_select_item(self) -> None:
        self._bump_activity()
        feed = self._focused_feed()
        if feed is not None:
            feed.action_select()

    @work
    async def _open_trajectory(
        self,
        trajectory_id: str,
        *,
        jump_to_decision: Decision | None = None,
        step_index: int | None = None,
    ) -> None:
        """Fetch full trajectory details and open the trajectory screen."""
        try:
            trajectory = await self._throttled(
                self.harness.get_trajectory(trajectory_id)
            )
            if trajectory:
                initial_step = None
                if step_index is not None:
                    initial_step = step_index
                elif jump_to_decision and trajectory.events:
                    steps = correlate_events(trajectory.events)
                    for i, s in enumerate(steps):
                        if s.decision == jump_to_decision:
                            initial_step = i
                            break
                self.push_screen(
                    TrajectoryScreen(trajectory, initial_step=initial_step)
                )
            else:
                self.notify("Trajectory not found", severity="error")
        except Exception as e:
            self.notify(f"Failed to load trajectory: {e}", severity="error")


if __name__ == "__main__":
    app = SonderaApp()
    app.run()
