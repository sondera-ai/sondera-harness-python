"""Sondera SDK for Python - Agent governance and policy enforcement.

This SDK provides tools for integrating AI agents with the Sondera Platform
for policy enforcement, guardrails, and governance.

Main Components:
    - Harness: Abstract base class for harness implementations
    - RemoteHarness: Production harness connecting to Sondera Platform
    - CedarPolicyEngine: Local policy-as-code engine using Cedar

Framework Integrations:
    - sondera.langgraph: LangGraph/LangChain middleware
    - sondera.adk: Google ADK plugin
    - sondera.strands: Strands Agent SDK hook

Example:
    >>> from sondera import SonderaRemoteHarness, Agent
    >>> harness = SonderaRemoteHarness(sondera_api_key="<YOUR_SONDERA_API_KEY>")
    >>> agent = Agent(
    ...     id="my-agent",
    ...     provider_id="langchain",
    ...     name="My Agent",
    ...     description="A helpful assistant",
    ...     instruction="Be helpful and concise",
    ...     tools=[],
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
    Agent,
    Content,
    Decision,
    Parameter,
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
