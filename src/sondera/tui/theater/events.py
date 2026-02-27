"""Events for trajectory theater playback."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from textual.message import Message

from sondera.types import Decision, Role, Stage


@dataclass
class StepEvent(Message):
    """Event emitted when a trajectory step is played.

    This message is posted by TrajectoryPlayer when advancing through
    trajectory steps. Plugins subscribe to this event to update their
    visualizations.
    """

    step_index: int
    """Zero-based index of the current step."""

    total_steps: int
    """Total number of steps in the trajectory."""

    stage: Stage
    """Agent loop stage (PRE_MODEL, POST_MODEL, PRE_TOOL, POST_TOOL, etc.)."""

    role: Role
    """Actor role (USER, MODEL, TOOL, SYSTEM)."""

    decision: Decision
    """Policy decision for this step (ALLOW, DENY, ESCALATE)."""

    reason: str
    """Reason for the adjudication decision."""

    content: Any
    """Step content (PromptContent, ToolRequestContent, or ToolResponseContent)."""

    timestamp: datetime
    """When the step was created."""

    delta_ms: int
    """Milliseconds since the previous step. Zero for first step."""

    policy_ids: list[str] = field(default_factory=list)
    """IDs of policies that triggered this decision."""

    @property
    def progress(self) -> float:
        """Progress through the trajectory as a fraction (0.0 to 1.0)."""
        if self.total_steps <= 1:
            return 1.0
        return self.step_index / (self.total_steps - 1)

    @property
    def is_first(self) -> bool:
        """True if this is the first step."""
        return self.step_index == 0

    @property
    def is_last(self) -> bool:
        """True if this is the last step."""
        return self.step_index == self.total_steps - 1

    @property
    def is_tool_call(self) -> bool:
        """True if this step involves a tool."""
        return self.role == Role.TOOL

    @property
    def is_denied(self) -> bool:
        """True if this step was denied by policy."""
        return self.decision == Decision.DENY

    @property
    def is_escalated(self) -> bool:
        """True if this step requires escalation."""
        return self.decision == Decision.ESCALATE


@dataclass
class PlaybackReset(Message):
    """Event emitted when playback is reset to the beginning."""

    pass


@dataclass
class PlaybackComplete(Message):
    """Event emitted when playback reaches the end."""

    total_steps: int
    """Total number of steps that were played."""
