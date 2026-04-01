"""Trajectory event correlation and display types.

The Trajectory Event Model represents action events and their adjudication
verdicts as separate ``Event`` objects.  This
module provides:

- ``EventStep`` – correlates an action Event with its Adjudicated verdict
- ``correlate_events`` – builds EventStep list from a raw Event stream
- ``ViolationRecord`` / ``violations_from_events`` – violation extraction
- ``parse_ts`` – robust ISO-8601 timestamp parsing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cached_property
from typing import Any

from sondera.types import (
    Adjudicated,
    Decision,
    Event,
    FileOperation,
    FileOperationResult,
    GuardrailResults,
    Mode,
    PolicyMetadata,
    Prompt,
    Scanned,
    ShellCommand,
    ShellCommandOutput,
    Steering,
    Thought,
    ToolCall,
    ToolOutput,
    WebFetch,
    WebFetchOutput,
)

# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------


def parse_ts(val: Any) -> datetime:
    """Parse an ISO-8601 string (or passthrough datetime) to a tz-aware datetime."""
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=UTC)
    if isinstance(val, str) and val:
        try:
            dt = datetime.fromisoformat(val)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            pass
    return datetime.now(tz=UTC)


# ---------------------------------------------------------------------------
# EventStep – the core bridge between the Event stream and the TUI
# ---------------------------------------------------------------------------

# Event types that represent lifecycle, not agent actions
_LIFECYCLE_EVENT_TYPES = frozenset(
    {"started", "completed", "resumed", "failed", "suspended", "terminated", "snapshot"}
)

# Adjudicated is also skipped from the "action" perspective; it's consumed
# as the verdict paired with the preceding action.
# Scanned is skipped too; it's correlated back to its source event by ID.
_SKIP_EVENT_TYPES = _LIFECYCLE_EVENT_TYPES | {"adjudicated", "scanned"}

_CONTENT_TYPE_MAP: dict[str, str] = {
    "tool_call": "tool_request",
    "tool_output": "tool_response",
    "prompt": "prompt",
    "thought": "prompt",
    "shell_command": "tool_request",
    "shell_command_output": "tool_response",
    "file_operation": "tool_request",
    "file_operation_result": "tool_response",
    "web_fetch": "tool_request",
    "web_fetch_output": "tool_response",
}


def _default_adjudication() -> Adjudicated:
    return Adjudicated.allow()


@dataclass
class EventStep:
    """An action Event paired with its Adjudicated verdict and optional Scanned context.

    In the Trajectory Event Model action events and their verdicts are
    separate ``Event`` objects; ``EventStep`` correlates them for rendering.
    A ``Scanned`` result (LLM-based analysis) may also be attached when
    the platform has enriched the event with semantic context.
    """

    event: Event
    adjudication: Adjudicated = field(default_factory=_default_adjudication)
    scanned: Scanned | None = None

    # ---- Convenience properties ----

    @property
    def decision(self) -> Decision:
        return self.adjudication.decision

    @property
    def reason(self) -> str:
        return self.adjudication.reason or ""

    @property
    def policies(self) -> list[PolicyMetadata]:
        return self.adjudication.metadata or []

    @property
    def mode(self) -> Mode | None:
        return self.adjudication.mode

    @property
    def steering(self) -> Steering | None:
        return self.adjudication.steering

    @property
    def guardrails(self) -> GuardrailResults | None:
        return self.adjudication.guardrails

    @property
    def deny_message(self) -> str:
        return self.adjudication.deny_message("Blocked by policy")

    @property
    def policy_context(self) -> str | None:
        return self.adjudication.format_policy_context()

    @property
    def timestamp(self) -> datetime:
        return parse_ts(self.event.timestamp)

    @property
    def event_type(self) -> str:
        return self.event.event_type or ""

    @property
    def payload(self) -> Any:
        return self.event.event

    # ---- Content-type mapping ----

    @property
    def content_type(self) -> str:
        """Map event_type to display content_type labels."""
        return _CONTENT_TYPE_MAP.get(self.event_type, self.event_type)

    @property
    def tool_id(self) -> str:
        p = self.payload
        if isinstance(p, ToolCall):
            return p.tool
        if isinstance(p, ToolOutput):
            return p.call_id or "tool_output"
        if isinstance(p, (ShellCommand, ShellCommandOutput)):
            return "Shell"
        if isinstance(p, (FileOperation, FileOperationResult)):
            return "FileOperation"
        if isinstance(p, (WebFetch, WebFetchOutput)):
            return "WebFetch"
        return self.event_type

    @property
    def text(self) -> str:
        p = self.payload
        if isinstance(p, Prompt):
            return p.content or ""
        if isinstance(p, Thought):
            return p.thought or ""
        return ""

    @property
    def args(self) -> dict[str, Any]:
        p = self.payload
        if isinstance(p, ToolCall):
            return p.arguments or {}
        if isinstance(p, ShellCommand):
            d: dict[str, Any] = {"command": p.command}
            if p.working_dir:
                d["working_dir"] = p.working_dir
            return d
        if isinstance(p, FileOperation):
            d = {"path": p.path, "operation": str(p.operation)}
            if p.content:
                d["content"] = p.content
            return d
        if isinstance(p, WebFetch):
            d = {"url": p.url}
            if p.prompt:
                d["prompt"] = p.prompt
            return d
        return {}

    @property
    def response(self) -> Any:
        p = self.payload
        if isinstance(p, ToolOutput):
            if p.error:
                return {"error": p.error}
            return p.output
        if isinstance(p, ShellCommandOutput):
            return {
                "stdout": p.stdout or "",
                "stderr": p.stderr or "",
                "exit_code": p.exit_code,
            }
        if isinstance(p, FileOperationResult):
            if p.error:
                return {"error": p.error}
            return p.content
        if isinstance(p, WebFetchOutput):
            return {"url": p.url or "", "result": p.result or "", "code": p.code}
        return None

    @property
    def role(self) -> str:
        if self.event_type == "prompt":
            actor = self.event.actor
            if actor and str(actor.actor_type).lower() == "human":
                return "user"
            p = self.payload
            if isinstance(p, Prompt) and str(p.role).lower() == "user":
                return "user"
            return "model"
        if self.event_type == "thought":
            return "model"
        if self.event_type in (
            "tool_call",
            "tool_output",
            "shell_command",
            "shell_command_output",
            "file_operation",
            "file_operation_result",
            "web_fetch",
            "web_fetch_output",
        ):
            return "tool"
        return "system"

    @property
    def stage(self) -> str:
        ct = self.content_type
        if ct == "tool_request":
            return "pre_tool"
        if ct == "tool_response":
            return "post_tool"
        if ct == "prompt":
            if self.role == "user":
                return "pre_model"
            return "post_model"
        return ""

    # ---- Scanned context properties ----

    @cached_property
    def scan_result(self) -> dict | None:
        """Raw result dict from the Scanned object, or None (cached per instance)."""
        if self.scanned is None:
            return None
        r = self.scanned.result
        return r if isinstance(r, dict) else None

    @property
    def scan_intent(self) -> str | None:
        """Agent intent label from scan (e.g. 'investigate', 'implement')."""
        r = self.scan_result
        return r.get("intent") if r else None

    @property
    def scan_description(self) -> str | None:
        """Human-readable description of what the event is doing."""
        r = self.scan_result
        return r.get("description") if r else None


def correlate_events(events: list[Event]) -> list[EventStep]:
    """Build EventSteps by pairing action events with adjudication verdicts and scan context.

    For each non-lifecycle event, looks ahead for an ``adjudicated`` event
    to pair it with.  Un-paired actions get a default ALLOW adjudication.

    ``Scanned`` events (LLM-based analysis) are indexed by ``source_event_id``
    and attached to the corresponding ``EventStep`` after the initial pass.
    """
    steps: list[EventStep] = []
    # Build source_event_id -> Scanned index from all scanned events
    scanned_by_source: dict[str, Scanned] = {}
    for ev in events:
        et = (ev.event_type or "").lower()
        if et == "scanned":
            payload = ev.event
            if isinstance(payload, Scanned) and payload.source_event_id:
                scanned_by_source[payload.source_event_id] = payload

    n = len(events)
    i = 0
    while i < n:
        ev = events[i]
        et = (ev.event_type or "").lower()

        if et in _SKIP_EVENT_TYPES:
            i += 1
            continue

        # Look for adjudication in the next event
        adj = _default_adjudication()
        if i + 1 < n:
            nxt = events[i + 1]
            if (nxt.event_type or "").lower() == "adjudicated" and isinstance(
                nxt.event, Adjudicated
            ):
                adj = nxt.event
                i += 1  # consume the adjudicated event

        # Attach Scanned context if available for this event's ID
        scanned = scanned_by_source.get(ev.event_id) if ev.event_id else None
        steps.append(EventStep(event=ev, adjudication=adj, scanned=scanned))
        i += 1

    return steps


# ---------------------------------------------------------------------------
# ViolationRecord
# ---------------------------------------------------------------------------


@dataclass
class ViolationRecord:
    """Display-friendly violation record built from an adjudication Event."""

    agent_id: str
    trajectory_id: str
    event_id: str
    decision: Decision
    reason: str
    policies: list[PolicyMetadata] = field(default_factory=list)
    step_index: int | None = None


def violations_from_events(events: list[Event]) -> list[ViolationRecord]:
    """Build ViolationRecords from Events wrapping Adjudicated payloads."""
    records: list[ViolationRecord] = []
    for i, ev in enumerate(events):
        if not isinstance(ev.event, Adjudicated):
            continue
        adj = ev.event
        if adj.decision not in (Decision.Deny, Decision.Escalate):
            continue
        records.append(
            ViolationRecord(
                agent_id=(ev.agent if isinstance(ev.agent, str) else ev.agent.id)
                if ev.agent
                else "",
                trajectory_id=ev.trajectory_id or "",
                event_id=ev.event_id or "",
                decision=adj.decision,
                reason=adj.reason or "",
                policies=adj.metadata or [],
                step_index=i,
            ),
        )
    return records
