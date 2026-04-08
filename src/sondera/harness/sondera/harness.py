"""Async client for the Sondera Harness Service."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sondera.exceptions import (
    ConfigurationError,
    TrajectoryError,
    TrajectoryNotInitializedError,
)
from sondera.harness.abc import Harness as AbstractHarness
from sondera.settings import SETTINGS
from sondera.types import (
    Adjudicated,
    Agent,
    Completed,
    Event,
    Failed,
    HarnessClient,
    Resumed,
    Started,
    Trajectory,
    TrajectoryEventStream,
    TrajectoryStatus,
)


def _parse_dt(val: Any) -> datetime:
    """Parse a value to datetime, falling back to now(UTC)."""
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=UTC)
    if isinstance(val, str) and val:
        try:
            dt = datetime.fromisoformat(val)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            pass
    return datetime.now(tz=UTC)


class SonderaRemoteHarness(AbstractHarness):
    """gRPC-based Harness implementation backed by the Sondera Platform.

    Delegates all operations to a ``HarnessClient`` and exposes the Trajectory
    Event Model directly.  Callers build ``Event`` objects with typed payloads
    (``ToolCall``, ``Prompt``, ``Thought``, …) and receive ``Adjudicated``
    verdicts.

    Example:
        ```python
        from sondera.types import Agent, Event, ToolCall
        from sondera.harness import SonderaRemoteHarness

        harness = SonderaRemoteHarness(
            sondera_harness_endpoint="localhost:50051",
            sondera_api_key="<YOUR_API_TOKEN>",
            agent=Agent(id="my-agent", provider="my-provider"),
        )

        await harness.initialize()

        event = Event(
            agent=harness.agent,
            trajectory_id=harness.trajectory_id,
            event=ToolCall(tool="Bash", arguments={"command": "ls"}),
        )
        adjudicated = await harness.adjudicate(event)

        await harness.finalize()
        ```
    """

    def __init__(
        self,
        *,
        agent: Agent | None = None,
        sondera_harness_endpoint: str = SETTINGS.sondera_harness_endpoint,
        sondera_api_key: str | None = SETTINGS.sondera_api_token,
    ):
        """Initialize the harness.

        Args:
            agent: The ``Agent`` identity to govern.
            sondera_harness_endpoint: The endpoint of the Sondera Harness service.
            sondera_api_key: JWT token for authentication (required).

        Raises:
            ConfigurationError: If sondera_api_key is None or empty.
        """
        if not sondera_api_key:
            raise ConfigurationError(
                "sondera_api_key is required and cannot be None or empty"
            )

        self._sondera_api_key = sondera_api_key
        self._agent: Agent | None = agent

        # Ensure the endpoint has a scheme so the Rust gRPC client knows
        # whether to use TLS.  Bare hostnames (e.g. "harness.sondera.ai")
        # need "https://" prepended; localhost without a scheme gets "http://".
        endpoint = sondera_harness_endpoint
        if "://" not in endpoint:
            is_local = endpoint.split(":")[0] in {"localhost", "127.0.0.1", "[::1]"}
            endpoint = f"http://{endpoint}" if is_local else f"https://{endpoint}"
        self._sondera_harness_endpoint = endpoint

        self._client = HarnessClient(endpoint, sondera_api_key)

        # Current trajectory state
        self._trajectory_id: str | None = None

    # -- Lifecycle methods ----------------------------------------------------

    async def initialize(
        self,
        *,
        agent: Agent | None = None,
        session_id: str | None = None,
    ) -> None:
        """Initialize a new trajectory for the current execution."""
        if agent:
            self._agent = agent
        assert self._agent is not None, (
            "Agent not provided on initialization or in constructor."
        )
        # Register the agent. The platform returns the existing agent if
        # already registered (deduplicates by provider + id).
        registered = await self._client.create_agent(self._agent)
        self._agent = registered
        # Create trajectory by sending a Started event
        trajectory_id = f"traj-{uuid.uuid4()}"
        started = Started(agent=self._agent, task=session_id)
        event = Event(
            agent=self._agent,
            trajectory_id="",
            event=started,
        )
        await self._client.adjudicate(event)
        logging.debug(f"Agent {self._agent.id} registered and started")
        self._trajectory_id = trajectory_id  #
        logging.debug(
            f"Trajectory created for agent {self._agent.id}: {self._trajectory_id}"
        )

    async def resume(self, trajectory_id: str, *, agent: Agent | None = None) -> None:
        """Resume an existing trajectory for continued execution.

        Args:
            trajectory_id: The ID of the trajectory to resume.
            agent: Optional agent override.

        Raises:
            RuntimeError: If there is already an active trajectory.
            TrajectoryError: If the trajectory does not exist or belongs
                to a different agent.
        """
        if self._trajectory_id:
            raise RuntimeError(
                f"Already have active trajectory {self._trajectory_id}. Call finalize first."
            )

        if agent:
            self._agent = agent
        assert self._agent is not None, (
            "Agent not provided on initialization or in constructor."
        )

        # Verify the trajectory exists
        traj_data = await self._client.get_trajectory(trajectory_id)
        if traj_data is None:
            raise TrajectoryError(f"Trajectory {trajectory_id} not found")

        traj_agent_id = traj_data.agent
        if not traj_agent_id or traj_agent_id != self._agent.id:
            raise TrajectoryError(
                f"Trajectory {trajectory_id} belongs to agent {traj_agent_id!r}, not {self._agent.id!r}"
            )

        # Send Resumed event
        resumed = Resumed(resumed_by=self._agent.id)
        event = Event(
            agent=self._agent,
            trajectory_id=trajectory_id,
            event=resumed,
        )
        await self._client.adjudicate(event)
        self._trajectory_id = trajectory_id
        logging.debug(f"Resumed trajectory {trajectory_id} for agent {self._agent.id}")

    async def finalize(self, *, summary: str | None = None) -> None:
        """Finalize the current trajectory and save artifacts.

        Args:
            summary: Optional free-text summary of the completed trajectory turn.
        """
        if not self._trajectory_id:
            raise TrajectoryNotInitializedError()
        assert self._agent is not None

        # Send Completed event
        completed = Completed(summary=summary)
        event = Event(
            agent=self._agent,
            trajectory_id=self._trajectory_id,
            event=completed,
        )
        await self._client.adjudicate(event)

        # Clear trajectory ID to indicate no active trajectory
        self._trajectory_id = None

    async def fail(self, *, reason: str) -> None:
        """Mark the current trajectory as failed.

        Args:
            reason: Human-readable description of the failure cause.
        """
        if not self._trajectory_id:
            raise TrajectoryNotInitializedError()
        assert self._agent is not None

        failed = Failed(reason=reason)
        event = Event(
            agent=self._agent,
            trajectory_id=self._trajectory_id,
            event=failed,
        )
        try:
            await self._client.adjudicate(event)
        finally:
            self._trajectory_id = None

    async def adjudicate(
        self,
        event: Event,
    ) -> Adjudicated:
        """Adjudicate an event against configured policies.

        Args:
            event: An ``Event`` wrapping a typed payload and trajectory metadata.

        Returns:
            ``Adjudicated`` verdict from the policy engine.

        Raises:
            RuntimeError: If no active trajectory exists.
        """
        if not self._trajectory_id:
            raise RuntimeError("No active trajectory. Call initialize() first.")

        logging.debug(
            f"Adjudicating (trajectory_id: {self._trajectory_id}): "
            f"{event.event_type} {event.category}"
        )
        result = await self._client.adjudicate(event)
        logging.debug(
            f"Adjudication (trajectory_id:{self._trajectory_id}): {result.decision}"
        )
        return result

    async def adjudicates(
        self,
        events: list[Event],
    ) -> list[Adjudicated]:
        """Adjudicate a batch of events against configured policies.

        Args:
            events: A list of ``Event`` objects to evaluate.

        Returns:
            A list of ``Adjudicated`` verdicts, one per input event, in order.

        Raises:
            RuntimeError: If no active trajectory exists.
        """
        if not self._trajectory_id:
            raise RuntimeError("No active trajectory. Call initialize() first.")

        logging.debug(
            f"Adjudicating batch of {len(events)} events "
            f"(trajectory_id: {self._trajectory_id})"
        )
        results = await self._client.adjudicates(events)
        logging.debug(
            f"Batch adjudication complete (trajectory_id: {self._trajectory_id}): "
            f"{[r.decision for r in results]}"
        )
        return results

    # -- Query methods --------------------------------------------------------

    async def list_agents(
        self,
        provider_id: str | None = None,
        page_size: int = 50,
        page_token: str = "",
    ) -> tuple[list[Agent], str]:
        """List registered agents.

        Args:
            provider_id: Optional provider ID to filter agents.
            page_size: Maximum number of agents to return per page.
            page_token: Token for pagination (empty string for first page).

        Returns:
            Tuple of (list of Agent objects, next page token).
        """
        filter_expr = f'provider_id="{provider_id}"' if provider_id else ""
        response = await self._client.list_agents(
            page_size=page_size,
            page_token=page_token,
            filter=filter_expr,
        )
        return list(response.agents), response.next_page_token

    async def get_agent(self, agent_id: str) -> Agent | None:
        """Get a single agent by ID.

        Args:
            agent_id: The agent resource name.

        Returns:
            The Agent, or None if not found.
        """
        try:
            return await self._client.get_agent(agent_id)
        except RuntimeError:
            logging.debug("get_agent failed for %s", agent_id, exc_info=True)
            return None

    async def get_trajectory(self, trajectory_id: str) -> Trajectory | None:
        """Get a trajectory by ID with its events.

        Args:
            trajectory_id: The trajectory resource name.

        Returns:
            Trajectory with events populated, or None if not found.
        """
        try:
            return await self._client.get_trajectory(trajectory_id)
        except RuntimeError:
            logging.debug("get_trajectory failed for %s", trajectory_id, exc_info=True)
            return None

    async def list_trajectories(
        self,
        agent_id: str,
        status: TrajectoryStatus | None = None,
        page_size: int = 50,
        page_token: str = "",
        session_id: str | None = None,
    ) -> tuple[list[Trajectory], str]:
        """List trajectories for an agent.

        Args:
            agent_id: The agent ID to filter trajectories.
            status: Optional status to filter trajectories.
            page_size: Maximum number of trajectories to return per page.
            page_token: Token for pagination (empty string for first page).
            session_id: Optional session ID to filter by conversation.

        Returns:
            Tuple of (list of Trajectory objects, next page token).
        """
        # Build filter expression
        parts = [f'agent_id="{agent_id}"']
        if status is not None:
            parts.append(f'status="{status}"')
        if session_id is not None:
            parts.append(f'session_id="{session_id}"')
        filter_expr = " AND ".join(parts)

        response = await self._client.list_trajectories(
            page_size=page_size,
            page_token=page_token,
            filter=filter_expr,
        )
        return list(response.trajectories), response.next_page_token

    async def analyze_trajectories(
        self,
        agent_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        analytics: list[str] | None = None,
    ) -> dict[str, Any]:
        """Analyze trajectories for an agent (AIP-136 custom method).

        Args:
            agent_id: The agent ID to analyze trajectories for.
            start_time: Optional start time filter (inclusive).
            end_time: Optional end time filter (inclusive).
            analytics: List of analytics to compute.

        Returns:
            Dictionary containing analytics results.
        """
        # Build filter expression
        parts = [f'agent_id="{agent_id}"']
        if start_time is not None:
            parts.append(f'created_at>="{start_time.isoformat()}"')
        if end_time is not None:
            parts.append(f'created_at<="{end_time.isoformat()}"')
        filter_expr = " AND ".join(parts)

        response = await self._client.analyze_trajectories(
            filter=filter_expr,
            metrics=analytics or [],
        )
        return {
            "analytics": response.metrics,
            "trajectory_count": response.trajectory_count,
            "computed_at": _parse_dt(response.compute_time),
        }

    async def list_adjudications(
        self,
        agent_id: str | None = None,
        page_size: int = 50,
        page_token: str = "",
    ) -> tuple[list[Event], str]:
        """List adjudication events (deny/escalate only).

        Returns full Event objects so callers can access trajectory_id,
        agent context, and other metadata alongside the Adjudicated payload.

        Args:
            agent_id: Optional agent ID to filter adjudications.
            page_size: Maximum number of records to return per page.
            page_token: Token for pagination (empty string for first page).

        Returns:
            Tuple of (list of Event wrapping Adjudicated payloads, next page token).
        """
        filter_expr = f'agent_id="{agent_id}"' if agent_id else ""
        response = await self._client.list_adjudications(
            page_size=page_size,
            page_token=page_token,
            filter=filter_expr,
        )

        adj_events: list[Event] = [
            event for event in response.events if isinstance(event.event, Adjudicated)
        ]
        return adj_events, response.next_page_token

    async def stream_trajectories(
        self,
        filter: str = "",
    ) -> TrajectoryEventStream:
        """Open a server-streaming subscription for new trajectory events.

        Args:
            filter: Optional filter expression
                    (e.g., ``'agent = "agents/claude-code"'``).

        Returns:
            A :class:`TrajectoryEventStream` async iterator.
        """
        return await self._client.stream_trajectories(filter=filter)
