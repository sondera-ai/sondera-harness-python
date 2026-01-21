"""Sondera SDK exception hierarchy."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sondera.types import Adjudication, Stage


class SonderaError(Exception):
    """Base exception for all Sondera SDK errors."""

    pass


class ConfigurationError(SonderaError):
    """Raised when there is a configuration error.

    Examples:
        - Missing required API key
        - Invalid endpoint format
        - Missing required settings
    """

    pass


class AuthenticationError(SonderaError):
    """Raised when authentication fails.

    Examples:
        - Invalid or expired JWT token
        - Missing authentication credentials
        - Token lacks required claims
    """

    pass


class ConnectionError(SonderaError):
    """Raised when connection to the harness service fails.

    Examples:
        - Network unreachable
        - Service unavailable
        - TLS handshake failure
    """

    pass


class TrajectoryError(SonderaError):
    """Raised for trajectory-related errors.

    Examples:
        - Trajectory not initialized
        - Invalid trajectory state
        - Trajectory already finalized
    """

    pass


class TrajectoryNotInitializedError(TrajectoryError):
    """Raised when attempting operations without an active trajectory."""

    def __init__(self, message: str = "No active trajectory. Call initialize() first."):
        super().__init__(message)


class PolicyError(SonderaError):
    """Base exception for policy-related errors."""

    pass


class PolicyViolationError(PolicyError):
    """Raised when a policy violation blocks execution.

    Attributes:
        stage: The execution stage where the violation occurred
        reason: The policy violation reason
        adjudication: The full adjudication result
    """

    def __init__(
        self,
        stage: Stage,
        reason: str,
        adjudication: Adjudication | None = None,
    ):
        self.stage = stage
        self.reason = reason
        self.adjudication = adjudication
        super().__init__(f"Policy violation at {stage.value}: {reason}")


class PolicyEvaluationError(PolicyError):
    """Raised when policy evaluation fails.

    Examples:
        - Invalid policy syntax
        - Schema mismatch
        - Policy engine internal error
    """

    pass


class AgentError(SonderaError):
    """Raised for agent-related errors.

    Examples:
        - Invalid agent configuration
        - Agent not found
        - Agent registration failed
    """

    pass


class ToolError(SonderaError):
    """Raised for tool-related errors.

    Examples:
        - Tool not found
        - Invalid tool arguments
        - Tool execution blocked
    """

    def __init__(
        self,
        tool_name: str,
        message: str,
        *,
        tool_args: dict | None = None,
    ):
        self.tool_name = tool_name
        self.tool_args = tool_args
        super().__init__(f"Tool '{tool_name}': {message}")


class ToolBlockedError(ToolError):
    """Raised when a tool execution is blocked by policy."""

    def __init__(
        self,
        tool_name: str,
        reason: str,
        *,
        tool_args: dict | None = None,
    ):
        self.reason = reason
        super().__init__(tool_name, f"Blocked - {reason}", tool_args=tool_args)


class SerializationError(SonderaError):
    """Raised when serialization or deserialization fails.

    Examples:
        - Invalid protobuf message
        - JSON encoding error
        - Type conversion failure
    """

    pass
