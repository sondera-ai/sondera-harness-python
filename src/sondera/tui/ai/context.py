"""Screen-aware context extraction for /ask queries."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sondera.tui.app import SonderaApp
from sondera.tui.screens.agent import AgentScreen
from sondera.tui.screens.trajectory import TrajectoryScreen

# Truncation limits for context extraction
_MAX_AGENTS = 50
_MAX_VIOLATIONS = 30
_MAX_TRAJECTORIES = 30
_MAX_STEPS = 80
_TEXT_CAP = 200
_REASON_CAP = 150
_DESC_CAP = 300


def _enum_str(val: Any) -> str:
    """Extract string value from an Enum or return str(val)."""
    if hasattr(val, "value"):
        return str(val.value)
    return str(val)


def extract_dashboard_context(app: SonderaApp) -> str:
    """Build context from the dashboard's loaded data."""
    lines: list[str] = []
    lines.append(f"DASHBOARD VIEW: {len(app._agents)} agents monitored")
    lines.append("")

    # Agent summary (use computed statuses when available)
    lines.append("AGENTS:")
    if app._agent_statuses:
        for a in app._agent_statuses[:_MAX_AGENTS]:
            parts = [f"  - {a.agent.name}"]
            parts.append(f"status={a.status}")
            parts.append(f"trajectories={a.total_trajectories}")
            if a.has_more_trajectories:
                parts[-1] += "+"
            if a.live_count > 0:
                parts.append(f"live={a.live_count}")
            if a.denied_count > 0:
                parts.append(f"denied={a.denied_count}")
            if a.awaiting_count > 0:
                parts.append(f"awaiting={a.awaiting_count}")
            if a.last_trajectory_status:
                parts.append(f"last_run={a.last_trajectory_status}")
            if a.last_active:
                parts.append(f"last_active={a.last_active.isoformat()}")
            lines.append("  ".join(parts))
        if len(app._agent_statuses) > _MAX_AGENTS:
            lines.append(f"  ... and {len(app._agent_statuses) - _MAX_AGENTS} more")
    else:
        for agent in app._agents[:_MAX_AGENTS]:
            tools = ", ".join(t.name for t in agent.tools) if agent.tools else "none"
            lines.append(f"  - {agent.name} (id: {agent.id[:16]}, tools: {tools})")
        if len(app._agents) > _MAX_AGENTS:
            lines.append(f"  ... and {len(app._agents) - _MAX_AGENTS} more")
    lines.append("")

    # Violations
    violations = [
        adj
        for adj in app._adjudications
        if _enum_str(adj.adjudication.decision) in ("deny", "escalate")
    ]
    lines.append(f"RECENT VIOLATIONS ({len(violations)}):")
    for adj in violations[:_MAX_VIOLATIONS]:
        agent_name = app._agents_map.get(adj.agent_id, adj.agent_id[:16])
        decision = _enum_str(adj.adjudication.decision).upper()
        reason = adj.adjudication.reason[:_TEXT_CAP]
        policies = ", ".join(p.id for p in adj.adjudication.policies[:3])
        lines.append(f"  [{decision}] Agent: {agent_name}")
        lines.append(f"    Trajectory: {adj.trajectory_id}")
        lines.append(f"    Reason: {reason}")
        if policies:
            lines.append(f"    Policies: {policies}")
        if adj.step_index is not None:
            lines.append(f"    Step index: {adj.step_index}")
    if len(violations) > _MAX_VIOLATIONS:
        lines.append(f"  ... and {len(violations) - _MAX_VIOLATIONS} more violations")

    return "\n".join(lines)


def extract_agent_context(screen: AgentScreen) -> str:
    """Build context from the agent detail screen."""
    lines: list[str] = []
    agent = screen.agent
    lines.append(f"AGENT DETAIL: {agent.name}")
    lines.append(f"  ID: {agent.id}")
    if agent.description:
        lines.append(f"  Description: {agent.description[:_DESC_CAP]}")
    if agent.instruction:
        lines.append(f"  Instruction: {agent.instruction[:_DESC_CAP]}")
    if agent.tools:
        tool_names = ", ".join(t.name for t in agent.tools)
        lines.append(f"  Tools: {tool_names}")
    lines.append(f"  Denied: {screen._denied_count}")
    lines.append(f"  Escalated: {screen._awaiting_count}")
    lines.append(f"  Total trajectories: {screen._total_trajectories}")
    lines.append("")

    lines.append("TRAJECTORIES:")
    from sondera.tui.widgets.trajectory_feed import _trajectory_label

    for t in screen._all_trajectories[:_MAX_TRAJECTORIES]:
        status = _enum_str(t.status)
        steps = t.step_count
        label = _trajectory_label(t, max_len=60)
        violations = ""
        if t.deny_count > 0:
            violations += f" {t.deny_count} denied"
        if t.escalate_count > 0:
            violations += f" {t.escalate_count} escalated"
        lines.append(
            f'  - {t.id}  "{label}"  status={status}  steps={steps}{violations}'
        )
    if len(screen._all_trajectories) > _MAX_TRAJECTORIES:
        lines.append(
            f"  ... and {len(screen._all_trajectories) - _MAX_TRAJECTORIES} more"
        )

    return "\n".join(lines)


def extract_trajectory_context(screen: TrajectoryScreen) -> str:
    """Build context from the trajectory detail screen.

    Uses the screen's grouped steps (which match display numbering) rather
    than raw steps so that step numbers in AI responses match what the user
    sees on screen.
    """
    lines: list[str] = []
    t = screen.trajectory
    agent_name = screen.app._agents_map.get(t.agent_id, t.agent_id)  # type: ignore[attr-defined]
    lines.append(f"TRAJECTORY DETAIL: {t.id}")
    lines.append(f"  Agent: {agent_name} ({t.agent_id})")
    lines.append(f"  Status: {_enum_str(t.status)}")
    lines.append(f"  Steps: {len(screen._step_groups)}")
    lines.append(
        f"  Denied: {t.deny_count}  Escalated: {t.escalate_count}"
        f"  Allowed: {t.allow_count}"
    )
    # Compute duration from step timestamps (t.duration needs started_at/ended_at
    # which aren't always populated, but step timestamps are always present)
    duration = t.duration
    first_ts = None
    last_ts = None
    if t.steps:
        first_ts = t.steps[0].step.created_at
        last_ts = t.steps[-1].step.created_at
        if (
            duration is None
            and isinstance(first_ts, datetime)
            and isinstance(last_ts, datetime)
        ):
            secs = (last_ts - first_ts).total_seconds()
            if secs > 0:
                duration = secs
    if duration is not None:
        mins, secs = divmod(int(duration), 60)
        lines.append(f"  Duration: {mins}m {secs}s ({duration:.0f} seconds)")
    if isinstance(first_ts, datetime) and isinstance(last_ts, datetime):
        lines.append(f"  Time range: {first_ts.isoformat()} to {last_ts.isoformat()}")
    lines.append("")

    # Report which step the user is currently looking at
    selected_idx = getattr(screen, "_selected_index", 0)
    if 0 <= selected_idx < len(screen._step_groups):
        sel = screen._step_groups[selected_idx]
        sel_num = sel.display_index + 1
        lines.append(f"  Currently selected: step #{sel_num}")
    lines.append("")

    # Separate violation groups from allow groups so violations are always
    # included even when the trajectory exceeds _MAX_STEPS.
    violation_groups = [
        g
        for g in screen._step_groups
        if _enum_str(g.decision).upper() in ("DENY", "ESCALATE")
    ]
    allow_groups = [
        g for g in screen._step_groups if _enum_str(g.decision).upper() == "ALLOW"
    ]

    # Budget: always include all violations, fill remaining with allow steps
    allow_budget = max(_MAX_STEPS - len(violation_groups), 0)
    included = violation_groups + allow_groups[:allow_budget]
    included.sort(key=lambda g: g.display_index)

    lines.append("STEPS (as displayed, 1-indexed):")
    for group in included:
        display_num = group.display_index + 1  # 1-indexed to match UI
        decision = _enum_str(group.decision).upper()
        label = group.label
        tool_id = group.tool_id or ""
        preview = (group.preview or "")[:_TEXT_CAP]

        line = f"  #{display_num}: [{decision}] {label}"
        if tool_id:
            line += f"  {tool_id}"
        lines.append(line)
        if preview:
            lines.append(f"    {preview}")
        if decision != "ALLOW":
            if group.deny_reason:
                lines.append(f"    Reason: {group.deny_reason[:_REASON_CAP]}")
            if group.deny_policies:
                policies = ", ".join(p.id for p in group.deny_policies[:3])
                lines.append(f"    Policies: {policies}")

    omitted = len(screen._step_groups) - len(included)
    if omitted > 0:
        lines.append(f"  ... and {omitted} more ALLOW steps omitted")

    return "\n".join(lines)


def extract_config_context() -> str:
    """Build context about AI and platform configuration (no secrets)."""
    import sondera.settings as _settings

    s = _settings.SETTINGS
    lines = ["CONFIGURATION:"]
    lines.append(f"  AI Model: {s.ai_model}")
    lines.append(f"  AI Model (fast): {s.ai_model_fast}")

    key = s.active_api_key
    if key:
        lines.append("  AI API Key: configured")
    else:
        lines.append("  AI API Key: NOT SET (set AI_API_KEY in ~/.sondera/env)")

    endpoint = s.ai_api_base
    if endpoint:
        lines.append(f"  AI API Base: {endpoint}")

    lines.append(f"  AI Recording: {'enabled' if s.ai_harness_enabled else 'disabled'}")

    lines.append(f"  Sondera Endpoint: {s.sondera_harness_endpoint}")
    token = s.sondera_api_token
    lines.append(f"  Sondera API Token: {'configured' if token else 'NOT SET'}")

    return "\n".join(lines)


def extract_app_context(app: SonderaApp) -> str:
    """Build context about the app's current state (theme, etc.)."""
    lines = [f"CURRENT THEME: {app.theme}"]
    available = sorted(app._registered_themes.keys())
    lines.append(f"AVAILABLE THEMES: {', '.join(available)}")
    return "\n".join(lines)


def get_screen_context(app: SonderaApp) -> str:
    """Extract context from the currently active screen."""
    screen = app.screen
    if isinstance(screen, TrajectoryScreen):
        context = extract_trajectory_context(screen)
    elif isinstance(screen, AgentScreen):
        context = extract_agent_context(screen)
    else:
        context = extract_dashboard_context(app)

    context += "\n\n" + extract_config_context()
    context += "\n\n" + extract_app_context(app)
    return context
