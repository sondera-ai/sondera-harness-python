from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from sondera.types import (  # noqa: F401
    Adjudicated,
    Agent,
    Event,
    Trajectory,
    TrajectoryEventStream,
    TrajectoryStatus,
)


class Harness(ABC):
    """Abstract base class defining the interface for Sondera Harness implementations.

    This ABC defines the core contract for harness implementations that integrate
    with the Sondera Platform for agent governance, trajectory management, and
    real-time event adjudication.

    The interface uses the Trajectory Event Model directly.  Callers build
    ``Event`` objects wrapping typed payloads (``ToolCall``, ``Prompt``,
    ``Thought``, etc.) and receive ``Adjudicated`` verdicts.

    Subclasses must implement:
        - resume: Resume an existing trajectory for continued execution
        - initialize: Set up a new trajectory for agent execution
        - finalize: Complete and save the current trajectory
        - adjudicate: Submit a single event for policy evaluation
        - adjudicates: Submit a batch of events for policy evaluation

    Attributes:
        trajectory_id: The current active trajectory ID (None if no active trajectory)
        agent: The ``Agent`` identity being governed
               (may be None until initialize is called)
    """

    _trajectory_id: str | None
    _agent: Agent | None

    @property
    def trajectory_id(self) -> str | None:
        """Get the current trajectory ID."""
        return self._trajectory_id

    @property
    def agent(self) -> Agent | None:
        """Get the current agent."""
        return self._agent

    @abstractmethod
    async def resume(self, trajectory_id: str, *, agent: Agent | None = None) -> None:
        """Resume an existing trajectory for continued execution.

        Sends a ``Resumed`` lifecycle event and sets the active trajectory.

        Args:
            trajectory_id: The ID of the trajectory to resume.
            agent: Optional agent override. If provided, replaces the agent
                   set during construction.

        Raises:
            RuntimeError: If there is already an active trajectory.
            TrajectoryError: If the trajectory does not exist or belongs
                   to a different agent.
        """
        ...

    @abstractmethod
    async def initialize(
        self,
        *,
        agent: Agent | None = None,
        session_id: str | None = None,
    ) -> None:
        """Initialize a new trajectory for the current execution.

        This method should:
        1. Register the agent with the Sondera Platform if not already registered
        2. Create a new trajectory for tracking the agent's execution
        3. Store the trajectory ID for subsequent adjudication calls

        Args:
            agent: Optional agent to use for this trajectory. If provided, overrides
                   any agent set during construction.
            session_id: Optional session identifier to group trajectories belonging
                   to the same conversation. All trajectories with the same session_id
                   form an ordered sequence of turns.

        Raises:
            ValueError: If no agent is provided and none was set during construction
            RuntimeError: If connection to the harness service fails
        """
        ...

    @abstractmethod
    async def finalize(self, *, summary: str | None = None) -> None:
        """Finalize the current trajectory and save artifacts.

        This method should:
        1. Mark the trajectory as completed
        2. Persist any remaining trajectory data
        3. Clear the active trajectory state

        Args:
            summary: Optional free-text summary of the completed trajectory turn
                     forwarded to the ``Completed`` lifecycle event.

        Raises:
            ValueError: If no active trajectory exists (initialize not called)
            RuntimeError: If finalization fails
        """
        ...

    @abstractmethod
    async def fail(self, *, reason: str) -> None:
        """Mark the current trajectory as failed due to an unexpected error.

        Sends a ``Failed`` lifecycle event and clears the active trajectory.
        Call this instead of ``finalize`` when the agent encountered an
        unhandled exception so the platform can distinguish clean completions
        from error terminations.

        Args:
            reason: Human-readable description of the failure cause.

        Raises:
            ValueError: If no active trajectory exists (initialize not called).
        """
        ...

    @abstractmethod
    async def adjudicate(
        self,
        event: Event,
    ) -> Adjudicated:
        """Adjudicate a trajectory event against configured policies.

        Submits the event to the policy engine and returns an ``Adjudicated``
        verdict containing the decision (Allow, Deny, or Escalate), an
        optional human-readable reason, and policy metadata.

        The caller is responsible for constructing the ``Event`` with the
        appropriate payload (``ToolCall``, ``Prompt``, ``Thought``, etc.),
        ``Agent``, and ``trajectory_id``.

        Args:
            event: An ``Event`` wrapping a typed payload and trajectory metadata.

        Returns:
            ``Adjudicated`` containing the decision, reason, and policy metadata.

        Raises:
            RuntimeError: If no active trajectory exists (initialize not called).
        """
        ...

    @abstractmethod
    async def adjudicates(
        self,
        events: list[Event],
    ) -> list[Adjudicated]:
        """Adjudicate a batch of events against configured policies.

        Submits each event to the policy engine and returns one ``Adjudicated``
        verdict per input event, preserving order.

        Args:
            events: A list of ``Event`` objects to evaluate.

        Returns:
            A list of ``Adjudicated`` verdicts, one per input event,
            in the same order as the input.

        Raises:
            RuntimeError: If no active trajectory exists (initialize not called).
        """
        ...

    # -- Query methods (paginated methods return (items, next_page_token)) ----

    @abstractmethod
    async def list_agents(
        self,
        provider_id: str | None = None,
        page_size: int = 50,
        page_token: str = "",
    ) -> tuple[list[Agent], str]: ...

    @abstractmethod
    async def get_agent(self, agent_id: str) -> Agent | None: ...

    @abstractmethod
    async def list_trajectories(
        self,
        agent_id: str,
        status: TrajectoryStatus | None = None,
        page_size: int = 50,
        page_token: str = "",
        session_id: str | None = None,
    ) -> tuple[list[Trajectory], str]: ...

    @abstractmethod
    async def get_trajectory(self, trajectory_id: str) -> Trajectory | None:
        """Return a trajectory by ID with its events.

        Returns:
            ``Trajectory`` with events populated,
            or ``None`` if the trajectory does not exist.
        """
        ...

    @abstractmethod
    async def list_adjudications(
        self,
        agent_id: str | None = None,
        page_size: int = 50,
        page_token: str = "",
    ) -> tuple[list[Event], str]:
        """List adjudication events (deny/escalate only).

        Returns full ``Event`` objects (not bare ``Adjudicated`` payloads)
        so callers can access trajectory_id, agent, and other context.

        Returns:
            Tuple of (list of ``Event`` wrapping ``Adjudicated`` payloads,
            next page token).
        """
        ...

    @abstractmethod
    async def analyze_trajectories(
        self,
        agent_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        analytics: list[str] | None = None,
    ) -> dict[str, Any]:
        """Supported analytics: ``trajectory_count``."""
        ...

    @abstractmethod
    async def stream_trajectories(
        self,
        filter: str = "",
    ) -> TrajectoryEventStream:
        """Open a server-streaming subscription for new trajectory events.

        Returns a :class:`TrajectoryEventStream` async iterator that yields
        :class:`TrajectoryEventNotification` objects as they arrive.

        Args:
            filter: Optional filter expression
                    (e.g., ``'agent = "agents/claude-code"'``).

        Returns:
            A :class:`TrajectoryEventStream` async iterator.

        Raises:
            NotImplementedError: If the implementation does not support streaming.
        """
        ...
