"""Sondera SDK type definitions for agent interoperability and policy evaluation."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class Model(BaseModel):
    """Base model for all Sondera SDK types."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class Parameter(Model):
    """
    Parameter object allows the definition of input and output data types.

    Simple parameter type theory for now.
    """

    name: str
    """ Name of the parameter. For human-readable display or metadata.
    """
    description: str
    """ Description of the parameter. For human-readable display or metadata.
    """
    type: str
    """ Type of the parameter.
    """


class SourceCode(Model):
    language: str
    code: str


class Tool(Model):
    id: str | None = None
    """ Optional unique identifier for the tool. Auto-generated if not provided.
    """
    name: str
    """ Name of the tool. For human-readable display or metadata.
    """
    description: str
    """ Description of the tool. For human-readable display or metadata.
    """
    parameters: list[Parameter]
    """ The parameters that are used by the tool.
    """
    parameters_json_schema: str | None = None
    """ JSON schema for the tool parameters.
    """
    response: str | None = None
    """ The type that is returned by the tool.
    """
    response_json_schema: str | None = None
    """ JSON schema for the tool response.
    """
    source: SourceCode | None = None
    """ The source of the tool if available.
    """


class Agent(Model):
    id: str
    """ Unique identifier for the agent.
    """
    provider_id: str
    """ Identifier for the provider of the agent.
    """
    name: str
    """ Name of the agent. For human-readable display or metadata.
    """
    description: str
    """ Description of the agent. For human-readable display or metadata.
    """
    instruction: str
    """ Instruction or goal of the agent.
    """
    tools: list[Tool]


class TrajectoryStatus(Enum):
    """Status of the trajectory."""

    UNKNOWN = "unknown"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SUSPENDED = "suspended"
    FAILED = "failed"


class Stage(Enum):
    """Lifecycle stage of the step."""

    PRE_RUN = "pre_run"
    PRE_MODEL = "pre_model"
    POST_MODEL = "post_model"
    PRE_TOOL = "pre_tool"
    POST_TOOL = "post_tool"
    POST_RUN = "post_run"


class Role(Enum):
    """Role of the step."""

    USER = "user"
    MODEL = "model"
    TOOL = "tool"
    SYSTEM = "system"


class TrajectoryStep(Model):
    role: Role
    """ Role of the step.
    """
    state: dict[str, Any] = Field(default_factory=dict)
    """ State of the step.
    """
    stage: Stage
    """ Stage of the step.
    """
    created_at: datetime = Field(default_factory=datetime.now)
    """ Created at timestamp.
    """
    context: Any | None = None
    """ Context of the step.
    """
    content: Any
    """ Content of the step.
    """


class Trajectory(Model):
    id: str = Field(default_factory=lambda: f"traj-{uuid.uuid4()}")
    """ Unique identifier for the trajectory.
    """
    agent_id: str = Field(default_factory=lambda: "agent-1")
    """ Identifier for the agent that created the trajectory.
    """
    status: TrajectoryStatus = Field(default=TrajectoryStatus.PENDING)
    metadata: dict[str, Any] = Field(default_factory=dict)
    """ Metadata of the trajectory.
    """
    created_at: datetime = Field(default_factory=datetime.now)
    """ Created at timestamp.
    """
    updated_at: datetime = Field(default_factory=datetime.now)
    """ Updated at timestamp.
    """
    started_at: datetime | None = Field(default=None)
    """ Started at timestamp.
    """
    ended_at: datetime | None = Field(default=None)
    """ Ended at timestamp.
    """
    steps: list[TrajectoryStep] = Field(default_factory=list)

    @property
    def duration(self) -> float | None:
        """Calculate trajectory duration in seconds."""
        if self.started_at and self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return None

    @property
    def step_count(self) -> int:
        """Get the total number of steps."""
        return len(self.steps)

    @property
    def is_completed(self) -> bool:
        """Check if trajectory is in a terminal state."""
        return self.status in [TrajectoryStatus.COMPLETED, TrajectoryStatus.FAILED]

    @property
    def is_active(self) -> bool:
        """Check if trajectory is currently running."""
        return self.status == TrajectoryStatus.RUNNING

    def get_steps_by_role(self, role: Role) -> list[TrajectoryStep]:
        """Get all steps with a specific role."""
        return [step for step in self.steps if step.role == role]

    def get_steps_by_stage(self, stage: Stage) -> list[TrajectoryStep]:
        """Get all steps at a specific stage."""
        return [step for step in self.steps if step.stage == stage]


class PolicyEngineMode(Enum):
    """Policy engine mode."""

    MONITOR = "monitor"
    """Monitor policy. Run policies but allow all actions."""
    GOVERN = "govern"
    """Govern policy on all actions."""


class Decision(Enum):
    """Decision of the adjudication."""

    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"


class PolicyAnnotation(Model):
    """Annotation from a policy evaluation."""

    id: str
    """Unique identifier of the policy that produced this annotation."""
    description: str
    """Human-readable description of why this annotation was added."""
    custom: dict[str, str] = Field(default_factory=dict)
    """Custom key-value metadata from the policy."""


class Adjudication(Model):
    """Result of the adjudication."""

    decision: Decision
    """Whether the input is allowed."""
    reason: str
    """Reason for the adjudication decision."""
    annotations: list[PolicyAnnotation] = Field(default_factory=list)
    """Annotations from policy evaluations."""

    @property
    def is_denied(self) -> bool:
        """Check if is denied."""
        return self.decision == Decision.DENY

    @property
    def is_allowed(self) -> bool:
        """Check if allowed."""
        return self.decision == Decision.ALLOW

    @property
    def is_escalated(self) -> bool:
        """Check if result requires escalation."""
        return self.decision == Decision.ESCALATE


class AdjudicatedStep(Model):
    """Result of the adjudicated input."""

    mode: PolicyEngineMode
    """Mode of the adjudication."""
    adjudication: Adjudication
    """Adjudication of the input."""
    step: TrajectoryStep
    """Step of the adjudication."""

    @property
    def is_denied(self) -> bool:
        """Check if result is denied."""
        return (
            self.adjudication.decision == Decision.DENY
            and self.mode == PolicyEngineMode.GOVERN
        )

    @property
    def is_allowed(self) -> bool:
        """Check if result is allowed."""
        return self.adjudication.decision == Decision.ALLOW

    @property
    def is_escalated(self) -> bool:
        """Check if result requires escalation."""
        return (
            self.adjudication.decision == Decision.ESCALATE
            and self.mode == PolicyEngineMode.GOVERN
        )

    @property
    def message(self) -> str:
        """Get the adjudication reason in a friendly format."""
        decision = self.adjudication.decision.value.capitalize()
        return f"{decision}: {self.adjudication.reason}"


class AdjudicatedTrajectory(Trajectory):
    """Adjudicated trajectory with annotated steps."""

    steps: list[AdjudicatedStep] = Field(default_factory=list)  # type: ignore[assignment]
    """Steps of the adjudicated trajectory."""


class PromptContent(Model):
    """Prompt content type for trajectory steps."""

    content_type: Literal["prompt"] = "prompt"
    text: str


class ToolRequestContent(Model):
    """Tool request content type for trajectory steps."""

    content_type: Literal["tool_request"] = "tool_request"
    tool_id: str
    args: dict[str, Any]


class ToolResponseContent(Model):
    """Tool response content type for trajectory steps."""

    content_type: Literal["tool_response"] = "tool_response"
    tool_id: str
    response: Any


Content = PromptContent | ToolRequestContent | ToolResponseContent
"""Union type representing the content of a trajectory step.

Corresponds to the Content protobuf message which uses a oneof field
to represent different types of step content:
- PromptContent: Text prompts or messages
- ToolRequestContent: Requests to execute tools
- ToolResponseContent: Results from tool execution
"""


class AdjudicationRecord(Model):
    """Record of an adjudication event from the harness service.

    Represents a single adjudication (policy decision) that occurred during
    agent execution, linking the decision to its agent, trajectory, and step.
    """

    agent_id: str = Field(description="ID of the agent that triggered the adjudication")
    trajectory_id: str = Field(
        description="ID of the trajectory containing the adjudicated step"
    )
    step_id: str = Field(description="ID of the step that was adjudicated")
    adjudication: Adjudication = Field(
        description="The adjudication decision and reason"
    )
