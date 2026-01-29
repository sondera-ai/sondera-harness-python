"""Sondera Harness - Steer agents with rules, not prompts.

Wrap your agent, write Cedar policies, ship with confidence. When a policy
denies an action, the agent gets the reason why and adjusts. Agents self-correct
instead of failing. This is steering, not just blocking.

Same input, same verdict. Rules are deterministic, not probabilistic. Stop
debugging prompts and start writing policies.

Why Sondera Harness:
    - Steer, don't just block: Denied actions include explanations
    - Drop-in integration: Native middleware for LangGraph, ADK, Strands
    - Full observability: Trajectories capture every action and decision
    - Deterministic rules: Same input, same verdict, every time
    - Ship faster: Reliability, safety, security, and compliance built in

Harness Implementations:
    - CedarPolicyHarness: Local evaluation, no network calls, no dependencies
    - SonderaRemoteHarness: Team policies, dashboards, centralized audit logs

Framework Integrations:
    - sondera.langgraph: LangGraph middleware
    - sondera.adk: Google ADK plugin
    - sondera.strands: Strands lifecycle hooks

Example:
    >>> from sondera import CedarPolicyHarness, Agent, Tool
    >>> from sondera.harness.cedar.schema import agent_to_cedar_schema
    >>>
    >>> agent = Agent(
    ...     id="my-agent",
    ...     provider_id="local",
    ...     name="My_Agent",
    ...     description="A helpful assistant",
    ...     instruction="Help users with tasks",
    ...     tools=[Tool(name="Bash", description="Run commands", parameters=[])],
    ... )
    >>> policy = "permit(principal, action, resource);"
    >>> harness = CedarPolicyHarness(
    ...     policy_set=policy,
    ...     schema=agent_to_cedar_schema(agent),
    ... )
    >>> await harness.initialize(agent=agent)
"""

from sondera.exceptions import (
    AgentError,
    AuthenticationError,
    ConfigurationError,
    ConnectionError,
    PolicyError,
    PolicyEvaluationError,
    PolicyViolationError,
    SerializationError,
    SonderaError,
    ToolBlockedError,
    ToolError,
    TrajectoryError,
    TrajectoryNotInitializedError,
)
from sondera.harness import CedarPolicyHarness, Harness, SonderaRemoteHarness
from sondera.types import (
    AdjudicatedStep,
    AdjudicatedTrajectory,
    Adjudication,
    AdjudicationRecord,
    Agent,
    Content,
    Decision,
    Parameter,
    PolicyAnnotation,
    PolicyEngineMode,
    PromptContent,
    Role,
    SourceCode,
    Stage,
    Tool,
    ToolRequestContent,
    ToolResponseContent,
    Trajectory,
    TrajectoryStatus,
    TrajectoryStep,
)

__version__ = "0.6.0"

__all__ = [
    # Harness implementations
    "Harness",
    "SonderaRemoteHarness",
    "CedarPolicyHarness",
    # Core types
    "Agent",
    "Tool",
    "Parameter",
    "SourceCode",
    # Trajectory types
    "Trajectory",
    "TrajectoryStep",
    "TrajectoryStatus",
    "Stage",
    "Role",
    # Content types
    "Content",
    "PromptContent",
    "ToolRequestContent",
    "ToolResponseContent",
    # Policy types
    "PolicyEngineMode",
    # Adjudication types
    "Adjudication",
    "AdjudicatedStep",
    "AdjudicatedTrajectory",
    "AdjudicationRecord",
    "PolicyAnnotation",
    "Decision",
    # Exceptions
    "SonderaError",
    "ConfigurationError",
    "AuthenticationError",
    "ConnectionError",
    "TrajectoryError",
    "TrajectoryNotInitializedError",
    "PolicyError",
    "PolicyViolationError",
    "PolicyEvaluationError",
    "AgentError",
    "ToolError",
    "ToolBlockedError",
    "SerializationError",
]
