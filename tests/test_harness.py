"""Tests for SonderaRemoteHarness.

Unit tests use a mocked HarnessClient.
Integration tests (marked ``@pytest.mark.integration``) require a running
Sondera Harness service.  Run them with::

    uv run pytest -m integration
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sondera import (
    Adjudicated,
    Agent,
    Completed,
    Event,
    Failed,
    Prompt,
    Resumed,
    Started,
    Thought,
    ToolCall,
    ToolOutput,
    Trajectory,
)
from sondera import Decision as HCDecision
from sondera import PolicyMetadata as HCPolicyMetadata
from sondera.exceptions import (
    ConfigurationError,
    TrajectoryError,
    TrajectoryNotInitializedError,
)
from sondera.harness import SonderaRemoteHarness

_AGENT = Agent(id="a1", provider="p1")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def harness():
    """SonderaRemoteHarness with a mocked HarnessClient.

    The real HarnessClient is a Rust extension with read-only attributes,
    so we patch it to allow mocking individual methods in unit tests.
    """
    with patch("sondera.harness.sondera.harness.HarnessClient"):
        yield SonderaRemoteHarness(
            sondera_api_key="test-key"  # pragma: allowlist secret
        )


@pytest.fixture()
def initialized_harness(harness: SonderaRemoteHarness):
    """Harness pre-set with an active agent and trajectory."""
    harness._agent = Agent(id="agents/p1/a1", provider="p1")
    harness._trajectory_id = "traj-123"
    harness._client.adjudicate = AsyncMock(return_value=Adjudicated.allow())
    return harness


# ===========================================================================
# Unit tests
# ===========================================================================


class TestHarnessConstructor:
    def test_requires_api_key(self):
        with pytest.raises(ConfigurationError, match="sondera_api_key is required"):
            SonderaRemoteHarness(
                sondera_harness_endpoint="localhost:50051",
                sondera_api_key="",
            )

    def test_none_api_key_raises(self):
        with pytest.raises(ConfigurationError, match="sondera_api_key is required"):
            SonderaRemoteHarness(
                sondera_harness_endpoint="localhost:50051",
                sondera_api_key=None,
            )

    def test_initial_state_is_inactive(self, harness: SonderaRemoteHarness):
        assert harness.trajectory_id is None
        assert harness.agent is None


class TestInitialize:
    async def test_registers_agent_and_creates_trajectory(
        self, harness: SonderaRemoteHarness
    ):
        registered = Agent(id="agents/p1/a1", provider="p1")
        harness._client.create_agent = AsyncMock(return_value=registered)
        harness._client.adjudicate = AsyncMock(return_value=Adjudicated.allow())

        await harness.initialize(agent=_AGENT)

        harness._client.create_agent.assert_called_once_with(_AGENT)
        assert harness.agent == registered
        assert harness.trajectory_id is not None
        assert harness.trajectory_id.startswith("traj-")

    async def test_sends_started_event(self, harness: SonderaRemoteHarness):
        harness._client.create_agent = AsyncMock(return_value=_AGENT)
        harness._client.adjudicate = AsyncMock(return_value=Adjudicated.allow())

        await harness.initialize(agent=_AGENT)

        event: Event = harness._client.adjudicate.call_args[0][0]
        assert isinstance(event.event, Started)
        assert event.agent == _AGENT

    async def test_started_event_carries_session_id(
        self, harness: SonderaRemoteHarness
    ):
        harness._client.create_agent = AsyncMock(return_value=_AGENT)
        harness._client.adjudicate = AsyncMock(return_value=Adjudicated.allow())

        await harness.initialize(agent=_AGENT, session_id="sess-42")

        event: Event = harness._client.adjudicate.call_args[0][0]
        assert isinstance(event.event, Started)
        assert event.event.task == "sess-42"

    async def test_raises_without_agent(self, harness: SonderaRemoteHarness):
        with pytest.raises(AssertionError, match="Agent not provided"):
            await harness.initialize()


class TestResume:
    async def test_resumes_existing_trajectory(self, harness: SonderaRemoteHarness):
        harness._agent = _AGENT
        traj = MagicMock(spec=Trajectory)
        traj.agent = _AGENT.id
        harness._client.get_trajectory = AsyncMock(return_value=traj)
        harness._client.adjudicate = AsyncMock(return_value=Adjudicated.allow())

        await harness.resume("traj-existing")

        assert harness.trajectory_id == "traj-existing"
        event: Event = harness._client.adjudicate.call_args[0][0]
        assert isinstance(event.event, Resumed)

    async def test_raises_if_trajectory_already_active(
        self, initialized_harness: SonderaRemoteHarness
    ):
        with pytest.raises(RuntimeError, match="Already have active trajectory"):
            await initialized_harness.resume("traj-other")

    async def test_raises_if_trajectory_not_found(self, harness: SonderaRemoteHarness):
        harness._agent = _AGENT
        harness._client.get_trajectory = AsyncMock(return_value=None)

        with pytest.raises(TrajectoryError, match="not found"):
            await harness.resume("traj-missing")

    async def test_raises_if_agent_mismatch(self, harness: SonderaRemoteHarness):
        harness._agent = _AGENT
        traj = MagicMock(spec=Trajectory)
        traj.agent = "different-agent"
        harness._client.get_trajectory = AsyncMock(return_value=traj)

        with pytest.raises(TrajectoryError, match="belongs to agent"):
            await harness.resume("traj-wrong-agent")

    @pytest.mark.parametrize(
        ("attacker_id", "traj_agent"),
        [
            ("evil/a1", "a1"),
            ("a1", ""),
        ],
    )
    async def test_rejects_unauthorized_resume(
        self, harness: SonderaRemoteHarness, attacker_id: str, traj_agent: str
    ):
        """Agents must not resume trajectories they don't own."""
        harness._agent = Agent(id=attacker_id, provider="attacker")
        traj = MagicMock(spec=Trajectory)
        traj.agent = traj_agent
        harness._client.get_trajectory = AsyncMock(return_value=traj)
        harness._client.adjudicate = AsyncMock(return_value=Adjudicated.allow())

        with pytest.raises(TrajectoryError):
            await harness.resume("traj-unauthorized")


class TestFinalize:
    async def test_sends_completed_and_clears_trajectory(
        self, initialized_harness: SonderaRemoteHarness
    ):
        await initialized_harness.finalize()

        assert initialized_harness.trajectory_id is None
        event: Event = initialized_harness._client.adjudicate.call_args[0][0]
        assert isinstance(event.event, Completed)

    async def test_completed_event_carries_summary(
        self, initialized_harness: SonderaRemoteHarness
    ):
        await initialized_harness.finalize(summary="task complete")

        event: Event = initialized_harness._client.adjudicate.call_args[0][0]
        assert isinstance(event.event, Completed)
        assert event.event.summary == "task complete"

    async def test_completed_summary_defaults_to_none(
        self, initialized_harness: SonderaRemoteHarness
    ):
        await initialized_harness.finalize()

        event: Event = initialized_harness._client.adjudicate.call_args[0][0]
        assert event.event.summary is None

    async def test_raises_without_active_trajectory(
        self, harness: SonderaRemoteHarness
    ):
        with pytest.raises(TrajectoryNotInitializedError):
            await harness.finalize()


class TestFail:
    async def test_sends_failed_event_and_clears_trajectory(
        self, initialized_harness: SonderaRemoteHarness
    ):
        await initialized_harness.fail(reason="unhandled exception")

        assert initialized_harness.trajectory_id is None
        event: Event = initialized_harness._client.adjudicate.call_args[0][0]
        assert isinstance(event.event, Failed)
        assert event.event.reason == "unhandled exception"

    async def test_raises_without_active_trajectory(
        self, harness: SonderaRemoteHarness
    ):
        with pytest.raises(TrajectoryNotInitializedError):
            await harness.fail(reason="crash")

    async def test_clears_trajectory_even_if_adjudicate_raises(
        self, initialized_harness: SonderaRemoteHarness
    ):
        """trajectory_id must be cleared even when the remote call fails."""
        initialized_harness._client.adjudicate = AsyncMock(
            side_effect=RuntimeError("network error")
        )

        with pytest.raises(RuntimeError, match="network error"):
            await initialized_harness.fail(reason="crash")

        # trajectory_id must be cleared despite the error
        assert initialized_harness.trajectory_id is None


class TestAdjudicate:
    async def test_passes_event_through_to_client(
        self, initialized_harness: SonderaRemoteHarness
    ):
        expected = Adjudicated(HCDecision.Allow, reason="ok")
        initialized_harness._client.adjudicate = AsyncMock(return_value=expected)

        event = Event(
            agent=initialized_harness.agent,
            trajectory_id="traj-123",
            event=ToolCall(tool="Bash", arguments={"command": "ls"}),
        )
        result = await initialized_harness.adjudicate(event)

        assert result is expected
        initialized_harness._client.adjudicate.assert_called_once_with(event)

    async def test_returns_deny_with_policy_metadata(
        self, initialized_harness: SonderaRemoteHarness
    ):
        expected = Adjudicated(
            HCDecision.Deny,
            reason="blocked",
            metadata=[
                HCPolicyMetadata(policy_id="p1", description="no bash", metadata={})
            ],
        )
        initialized_harness._client.adjudicate = AsyncMock(return_value=expected)

        event = Event(
            agent=initialized_harness.agent,
            trajectory_id="traj-123",
            event=ToolCall(tool="Bash", arguments={"command": "rm -rf /"}),
        )
        result = await initialized_harness.adjudicate(event)

        assert result.decision == HCDecision.Deny
        assert result.reason == "blocked"
        assert len(result.metadata) == 1
        assert result.metadata[0].policy_id == "p1"

    async def test_raises_without_active_trajectory(
        self, harness: SonderaRemoteHarness
    ):
        event = MagicMock(spec=Event)
        with pytest.raises(RuntimeError, match="No active trajectory"):
            await harness.adjudicate(event)

    async def test_works_with_prompt_event(
        self, initialized_harness: SonderaRemoteHarness
    ):
        initialized_harness._client.adjudicate = AsyncMock(
            return_value=Adjudicated.allow()
        )

        event = Event(
            agent=initialized_harness.agent,
            trajectory_id="traj-123",
            event=Prompt.user("Hello"),
        )
        result = await initialized_harness.adjudicate(event)
        assert result.decision == HCDecision.Allow

    async def test_works_with_thought_event(
        self, initialized_harness: SonderaRemoteHarness
    ):
        initialized_harness._client.adjudicate = AsyncMock(
            return_value=Adjudicated.allow()
        )

        event = Event(
            agent=initialized_harness.agent,
            trajectory_id="traj-123",
            event=Thought("I should look up the docs"),
        )
        result = await initialized_harness.adjudicate(event)
        assert result.decision == HCDecision.Allow

    async def test_works_with_tool_output_event(
        self, initialized_harness: SonderaRemoteHarness
    ):
        initialized_harness._client.adjudicate = AsyncMock(
            return_value=Adjudicated.allow()
        )

        event = Event(
            agent=initialized_harness.agent,
            trajectory_id="traj-123",
            event=ToolOutput.from_success("Bash", "file.txt"),
        )
        result = await initialized_harness.adjudicate(event)
        assert result.decision == HCDecision.Allow


class TestAdjudicates:
    async def test_delegates_batch_to_client(
        self, initialized_harness: SonderaRemoteHarness
    ):
        expected = [
            Adjudicated(HCDecision.Allow, reason="ok"),
            Adjudicated(HCDecision.Deny, reason="blocked"),
        ]
        initialized_harness._client.adjudicates = AsyncMock(return_value=expected)

        events = [
            Event(
                agent=initialized_harness.agent,
                trajectory_id="traj-123",
                event=ToolCall(tool="Bash", arguments={"command": "ls"}),
            ),
            Event(
                agent=initialized_harness.agent,
                trajectory_id="traj-123",
                event=ToolCall(tool="Bash", arguments={"command": "rm -rf /"}),
            ),
        ]
        results = await initialized_harness.adjudicates(events)

        assert results is expected
        initialized_harness._client.adjudicates.assert_called_once_with(events)

    async def test_raises_without_active_trajectory(
        self, harness: SonderaRemoteHarness
    ):
        with pytest.raises(RuntimeError, match="No active trajectory"):
            await harness.adjudicates([MagicMock(spec=Event)])

    async def test_preserves_result_order(
        self, initialized_harness: SonderaRemoteHarness
    ):
        verdicts = [
            Adjudicated(HCDecision.Allow, reason="ok"),
            Adjudicated(HCDecision.Deny, reason="blocked"),
            Adjudicated(HCDecision.Allow, reason="ok"),
        ]
        initialized_harness._client.adjudicates = AsyncMock(return_value=verdicts)

        events = [MagicMock(spec=Event) for _ in range(3)]
        results = await initialized_harness.adjudicates(events)

        assert len(results) == 3
        assert results[0].decision == HCDecision.Allow
        assert results[1].decision == HCDecision.Deny
        assert results[2].decision == HCDecision.Allow


class TestListAdjudications:
    async def test_extracts_adjudicated_from_events(
        self, harness: SonderaRemoteHarness
    ):
        adj = Adjudicated(HCDecision.Deny, reason="blocked")

        adj_event = MagicMock(spec=Event)
        adj_event.event = adj

        other_event = MagicMock(spec=Event)
        other_event.event = ToolCall(tool="Bash", arguments={})

        response = MagicMock()
        response.events = [adj_event, other_event]
        response.next_page_token = ""
        harness._client.list_adjudications = AsyncMock(return_value=response)

        verdicts, token = await harness.list_adjudications(agent_id="a1")

        assert len(verdicts) == 1
        assert verdicts[0] is adj_event  # returns full Event, not bare Adjudicated
        assert token == ""

    async def test_empty_response(self, harness: SonderaRemoteHarness):
        response = MagicMock()
        response.events = []
        response.next_page_token = ""
        harness._client.list_adjudications = AsyncMock(return_value=response)

        verdicts, token = await harness.list_adjudications()
        assert verdicts == []

    async def test_passes_filter_for_agent_id(self, harness: SonderaRemoteHarness):
        response = MagicMock()
        response.events = []
        response.next_page_token = ""
        harness._client.list_adjudications = AsyncMock(return_value=response)

        await harness.list_adjudications(agent_id="agent-x", page_size=10)

        harness._client.list_adjudications.assert_called_once_with(
            page_size=10,
            page_token="",
            filter='agent_id="agent-x"',
        )


class TestAgentQueries:
    async def test_list_agents_returns_agents(self, harness: SonderaRemoteHarness):
        response = MagicMock()
        response.agents = [_AGENT]
        response.next_page_token = "next"  # noqa: S105
        harness._client.list_agents = AsyncMock(return_value=response)

        agents, token = await harness.list_agents()

        assert agents == [_AGENT]
        assert token == "next"  # noqa: S105

    async def test_list_agents_with_provider_filter(
        self, harness: SonderaRemoteHarness
    ):
        response = MagicMock()
        response.agents = []
        response.next_page_token = ""
        harness._client.list_agents = AsyncMock(return_value=response)

        await harness.list_agents(provider_id="anthropic")

        harness._client.list_agents.assert_called_once_with(
            page_size=50,
            page_token="",
            filter='provider_id="anthropic"',
        )

    async def test_get_agent_returns_agent(self, harness: SonderaRemoteHarness):
        harness._client.get_agent = AsyncMock(return_value=_AGENT)

        result = await harness.get_agent("a1")
        assert result == _AGENT

    async def test_get_agent_returns_none_on_error(self, harness: SonderaRemoteHarness):
        harness._client.get_agent = AsyncMock(side_effect=RuntimeError("not found"))

        result = await harness.get_agent("missing")
        assert result is None


class TestTrajectoryQueries:
    async def test_get_trajectory(self, harness: SonderaRemoteHarness):
        traj = MagicMock(spec=Trajectory)
        harness._client.get_trajectory = AsyncMock(return_value=traj)

        result = await harness.get_trajectory("traj-1")
        assert result is traj

    async def test_get_trajectory_returns_none_on_error(
        self, harness: SonderaRemoteHarness
    ):
        harness._client.get_trajectory = AsyncMock(
            side_effect=RuntimeError("not found")
        )

        result = await harness.get_trajectory("traj-missing")
        assert result is None

    async def test_list_trajectories_builds_filter(self, harness: SonderaRemoteHarness):
        response = MagicMock()
        response.trajectories = []
        response.next_page_token = ""
        harness._client.list_trajectories = AsyncMock(return_value=response)

        await harness.list_trajectories(
            agent_id="a1",
            status="running",
            session_id="sess-1",
        )

        harness._client.list_trajectories.assert_called_once_with(
            page_size=50,
            page_token="",
            filter='agent_id="a1" AND status="running" AND session_id="sess-1"',
        )

    async def test_list_trajectories_minimal_filter(
        self, harness: SonderaRemoteHarness
    ):
        response = MagicMock()
        response.trajectories = []
        response.next_page_token = ""
        harness._client.list_trajectories = AsyncMock(return_value=response)

        await harness.list_trajectories(agent_id="a1")

        harness._client.list_trajectories.assert_called_once_with(
            page_size=50,
            page_token="",
            filter='agent_id="a1"',
        )


# ===========================================================================
# Integration tests — real HarnessClient, real gRPC
# ===========================================================================


@pytest.fixture()
def live_harness():
    """SonderaRemoteHarness using default env settings (real client)."""
    return SonderaRemoteHarness()


@pytest.fixture()
def integration_agent():
    """Unique agent per test to avoid duplicate insert errors."""
    import uuid

    return Agent(id=f"test-agent-{uuid.uuid4().hex[:8]}", provider="sondera-sdk-tests")


@pytest.mark.integration
class TestIntegrationLifecycle:
    """Full round-trip against a live Harness service."""

    async def test_initialize_adjudicate_finalize(
        self, live_harness: SonderaRemoteHarness, integration_agent: Agent
    ):
        """Happy path: initialize, adjudicate multiple event types, finalize."""
        await live_harness.initialize(
            agent=integration_agent, session_id="integration-test"
        )
        assert live_harness.trajectory_id is not None
        assert live_harness.agent is not None
        tid = live_harness.trajectory_id
        agent = live_harness.agent

        # Prompt
        result = await live_harness.adjudicate(
            Event(agent=agent, trajectory_id=tid, event=Prompt.user("Hello"))
        )
        assert result.decision in (
            HCDecision.Allow,
            HCDecision.Deny,
            HCDecision.Escalate,
        )

        # ToolCall
        result = await live_harness.adjudicate(
            Event(
                agent=agent,
                trajectory_id=tid,
                event=ToolCall(tool="search", arguments={"q": "weather"}),
            )
        )
        assert result.decision is not None

        # ToolOutput
        result = await live_harness.adjudicate(
            Event(
                agent=agent,
                trajectory_id=tid,
                event=ToolOutput.from_success("search", "sunny, 72°F"),
            )
        )
        assert result.decision is not None

        await live_harness.finalize()
        assert live_harness.trajectory_id is None

    async def test_initialize_finalize_resume(
        self, live_harness: SonderaRemoteHarness, integration_agent: Agent
    ):
        """Initialize → finalize → resume the same trajectory."""
        await live_harness.initialize(agent=integration_agent, session_id="resume-test")
        tid = live_harness.trajectory_id
        assert tid is not None
        # Store the registered agent (server may add a resource prefix)
        agent = live_harness.agent

        await live_harness.finalize()
        assert live_harness.trajectory_id is None

        # Resume needs the registered agent identity
        await live_harness.resume(tid, agent=agent)
        assert live_harness.trajectory_id == tid

        result = await live_harness.adjudicate(
            Event(
                agent=live_harness.agent,
                trajectory_id=tid,
                event=Prompt.user("resumed message"),
            )
        )
        assert result.decision is not None

        await live_harness.finalize()
        assert live_harness.trajectory_id is None

    async def test_get_trajectory_after_finalize(
        self, live_harness: SonderaRemoteHarness, integration_agent: Agent
    ):
        """A finalized trajectory should be retrievable via get_trajectory."""
        await live_harness.initialize(agent=integration_agent, session_id="get-test")
        tid = live_harness.trajectory_id

        await live_harness.adjudicate(
            Event(
                agent=live_harness.agent,
                trajectory_id=tid,
                event=Prompt.user("hello"),
            )
        )
        await live_harness.finalize()

        traj = await live_harness.get_trajectory(tid)
        assert traj is not None
        # Server returns resource names with a "trajectories/" prefix
        assert traj.name.endswith(tid)
        assert traj.events is not None
        assert len(traj.events) > 0

    async def test_list_agents_includes_registered(
        self, live_harness: SonderaRemoteHarness, integration_agent: Agent
    ):
        """After initialize, the agent should appear in list_agents."""
        await live_harness.initialize(
            agent=integration_agent, session_id="list-agents-test"
        )
        agent = live_harness.agent

        # List without filter first to verify the API works
        agents, _ = await live_harness.list_agents()
        assert len(agents) > 0, "Expected at least one agent from list_agents"
        agent_ids = [a.id for a in agents]
        # Match by suffix — server may add "agents/" prefix
        base_id = agent.id.split("/")[-1]
        assert any(base_id in aid for aid in agent_ids)

        await live_harness.finalize()

    async def test_list_trajectories_includes_created(
        self, live_harness: SonderaRemoteHarness, integration_agent: Agent
    ):
        """After initialize, the trajectory should appear in list_trajectories."""
        await live_harness.initialize(
            agent=integration_agent, session_id="list-traj-test"
        )
        tid = live_harness.trajectory_id
        agent = live_harness.agent

        trajectories, _ = await live_harness.list_trajectories(agent_id=agent.id)
        traj_names = [t.name for t in trajectories]
        # Server returns resource names with a "trajectories/" prefix
        assert any(tid in name for name in traj_names)

        await live_harness.finalize()
