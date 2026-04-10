"""Integration tests for SonderaProvider with mock harness.

Tests cover the new API where:
- govern() mutates the agent in place (returns None)
- GovernedAgent is deleted
- Custom exceptions replaced by Pydantic AI natives
- POST_TOOL deny returns redacted string instead of raising
- HarnessErrorPolicy controls fail-open/fail-closed behavior
- enable_escalation controls Escalate handling
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.exceptions import ModelRetry, SkipToolExecution

from pydantic_ai import Agent as PydanticAgent
from sondera import Adjudicated, Agent, Decision, Mode
from sondera.harness import Harness
from sondera.pydantic.provider import SonderaProvider
from sondera.pydantic.toolset import (
    _POST_TOOL_REDACTED,
    HarnessErrorPolicy,
    SonderaGovernedToolset,
    Strategy,
)


class _MockHooks:
    """Mock hooks object that captures the wrap_run-decorated function.

    After ``govern()`` runs, ``hooks.lifecycle_fn`` holds the async lifecycle
    function that would normally be called by the Pydantic AI agent on each run.
    Tests can invoke it directly to validate initialize/finalize/fail behavior.
    """

    def __init__(self) -> None:
        self.lifecycle_fn = None

    def wrap_run(self, fn):
        """Decorator that captures the function for later testing."""
        self.lifecycle_fn = fn
        return fn


def _make_toolsets_writable(agent: PydanticAgent) -> None:
    """Monkey-patch the agent so ``agent.toolsets = [...]`` works.

    In the installed pydantic-ai version ``toolsets`` is a read-only property.
    The new API that ``govern()`` targets supports assignment. We store the
    original value in ``_toolsets_override`` and replace the class-level
    property with one that delegates to that attribute when set.
    """
    cls = type(agent)
    if isinstance(cls.__dict__.get("toolsets"), property) and not hasattr(
        cls, "_original_toolsets_prop"
    ):
        original_prop = cls.__dict__["toolsets"]
        cls._original_toolsets_prop = original_prop  # type: ignore[attr-defined]

        def _get(self):
            return getattr(self, "_toolsets_override", None) or original_prop.fget(self)

        def _set(self, value):
            self._toolsets_override = value

        cls.toolsets = property(_get, _set)  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_harness() -> MagicMock:
    """Create a mock harness that allows everything by default."""
    harness = MagicMock(spec=Harness)
    harness.initialize = AsyncMock()
    harness.finalize = AsyncMock()
    harness.fail = AsyncMock()
    harness.adjudicate = AsyncMock(
        return_value=Adjudicated(Decision.Allow, reason="Allowed")
    )
    harness.agent = Agent(
        id="test-agent",
        provider="pydantic-ai",
    )
    harness.trajectory_id = "traj-123"
    return harness


@pytest.fixture
def pydantic_agent() -> PydanticAgent:
    """Create a simple Pydantic AI agent with one tool.

    Adds a mock ``hooks`` attribute so that ``govern()`` can register its
    ``wrap_run`` decorator without requiring a version of pydantic-ai that
    ships the hooks API.
    """

    agent = PydanticAgent("test")

    @agent.tool_plain
    def get_weather(city: str) -> str:
        """Get weather for a city."""
        return f"Sunny in {city}"

    # The hooks.wrap_run API is newer than the installed pydantic-ai version.
    # Provide a capturing mock so govern() can decorate and tests can invoke
    # the lifecycle function directly.
    if not hasattr(agent, "hooks"):
        agent.hooks = _MockHooks()  # type: ignore[attr-defined]

    # Make agent.toolsets writable so govern() can replace them with governed
    # toolsets. In newer pydantic-ai versions toolsets has a setter; in the
    # installed version it's a read-only property. We store the original list
    # and monkey-patch the class property to support assignment.
    _make_toolsets_writable(agent)

    return agent


def _first_governed_toolset(
    pydantic_agent: PydanticAgent,
    mock_harness: MagicMock,
    *,
    strategy: Strategy = Strategy.BLOCK,
    harness_error_policy: HarnessErrorPolicy = HarnessErrorPolicy.FAIL_CLOSED,
    enable_escalation: bool = False,
    include_tool_args_in_escalation: bool = False,
) -> SonderaGovernedToolset:
    """Build a SonderaGovernedToolset from the first toolset of the agent."""
    ts = pydantic_agent.toolsets[0]
    return SonderaGovernedToolset(
        ts,
        harness=mock_harness,
        strategy=strategy,
        harness_error_policy=harness_error_policy,
        enable_escalation=enable_escalation,
        include_tool_args_in_escalation=include_tool_args_in_escalation,
    )


# ---------------------------------------------------------------------------
# Tests: build_agent_card
# ---------------------------------------------------------------------------


class TestBuildAgentCard:
    def test_build_agent_card_from_pydantic_agent(self, pydantic_agent: PydanticAgent):
        """Build AgentCard from Pydantic AI agent and verify tool inventory."""
        provider = SonderaProvider()
        card = provider.build_agent_card(
            pydantic_agent, agent_id="weather-agent", name="Weather Bot"
        )

        assert card.id == "weather-agent"
        assert card.provider == "pydantic-ai"
        assert card.card is not None
        react_card = card.card.react_card
        assert react_card is not None
        tool_names = [t.name for t in react_card.tools]
        assert "get_weather" in tool_names


# ---------------------------------------------------------------------------
# Tests: govern() returns None and mutates agent
# ---------------------------------------------------------------------------


class TestGovernMutatesAgent:
    def test_govern_returns_none(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """govern() should return None (mutates agent in place)."""
        agent_card = Agent(id="test", provider="pydantic-ai")
        provider = SonderaProvider()
        result = provider.govern(
            pydantic_agent, harness=mock_harness, agent_card=agent_card
        )
        assert result is None

    def test_govern_replaces_toolsets(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """govern() should wrap all toolsets with SonderaGovernedToolset."""
        agent_card = Agent(id="test", provider="pydantic-ai")
        provider = SonderaProvider()
        provider.govern(pydantic_agent, harness=mock_harness, agent_card=agent_card)
        for ts in pydantic_agent.toolsets:
            assert isinstance(ts, SonderaGovernedToolset)


# ---------------------------------------------------------------------------
# Tests: governed lifecycle with ALLOW
# ---------------------------------------------------------------------------


class TestGovernedRunAllow:
    @pytest.mark.asyncio
    async def test_full_lifecycle(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """Full governed run with ALLOW: initialize, handler, finalize."""
        agent_card = Agent(id="test", provider="pydantic-ai")
        provider = SonderaProvider()
        provider.govern(pydantic_agent, harness=mock_harness, agent_card=agent_card)

        # The lifecycle function was captured by _MockHooks.wrap_run.
        lifecycle_fn = pydantic_agent.hooks.lifecycle_fn  # type: ignore[attr-defined]
        assert lifecycle_fn is not None

        mock_result = MagicMock()
        mock_result.output = "It's sunny!"
        handler = AsyncMock(return_value=mock_result)

        result = await lifecycle_fn(MagicMock(), handler=handler)

        assert result.output == "It's sunny!"
        mock_harness.initialize.assert_awaited_once()
        mock_harness.finalize.assert_awaited_once()
        mock_harness.fail.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: governed run with DENY + STEER (Govern mode)
# ---------------------------------------------------------------------------


class TestGovernedRunDenySteer:
    @pytest.mark.asyncio
    async def test_deny_steer_raises_model_retry_in_govern_mode(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """DENY with STEER strategy in Govern mode should raise ModelRetry."""
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(
                Decision.Deny, reason="Blocked by policy", mode=Mode.Govern
            )
        )

        governed_ts = _first_governed_toolset(
            pydantic_agent, mock_harness, strategy=Strategy.STEER
        )
        mock_ctx = MagicMock()
        mock_tool = MagicMock()
        with pytest.raises(ModelRetry, match="Policy requires a different approach"):
            await governed_ts.call_tool(
                "get_weather", {"city": "London"}, mock_ctx, mock_tool
            )


# ---------------------------------------------------------------------------
# Tests: governed run with BLOCK (Govern mode)
# ---------------------------------------------------------------------------


class TestGovernedRunBlock:
    @pytest.mark.asyncio
    async def test_deny_block_raises_skip_tool_execution_in_govern_mode(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """DENY with BLOCK strategy in Govern mode should raise SkipToolExecution."""
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(
                Decision.Deny, reason="Forbidden", mode=Mode.Govern
            )
        )

        governed_ts = _first_governed_toolset(
            pydantic_agent, mock_harness, strategy=Strategy.BLOCK
        )
        mock_ctx = MagicMock()
        mock_tool = MagicMock()
        with pytest.raises(SkipToolExecution) as exc_info:
            await governed_ts.call_tool(
                "get_weather", {"city": "London"}, mock_ctx, mock_tool
            )
        assert exc_info.value.result == "Tool call denied by policy."


# ---------------------------------------------------------------------------
# Tests: Mode awareness -- Monitor mode allows despite DENY
# ---------------------------------------------------------------------------


class TestModeAwareness:
    @pytest.mark.asyncio
    async def test_monitor_mode_deny_allows_execution(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """DENY in Monitor mode should log but allow execution to proceed."""
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(Decision.Deny, reason="Would be blocked")
        )

        governed_ts = _first_governed_toolset(
            pydantic_agent, mock_harness, strategy=Strategy.BLOCK
        )
        mock_ctx = MagicMock()
        mock_tool = MagicMock()
        with patch.object(
            governed_ts.wrapped, "call_tool", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = "Sunny in London"
            result = await governed_ts.call_tool(
                "get_weather", {"city": "London"}, mock_ctx, mock_tool
            )
        assert result == "Sunny in London"

    @pytest.mark.asyncio
    async def test_steer_mode_deny_allows_execution(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """DENY in Steer mode should log but allow execution to proceed."""
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(Decision.Deny, reason="Steered", mode=Mode.Steer)
        )

        governed_ts = _first_governed_toolset(
            pydantic_agent, mock_harness, strategy=Strategy.BLOCK
        )
        mock_ctx = MagicMock()
        mock_tool = MagicMock()
        with patch.object(
            governed_ts.wrapped, "call_tool", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = "Sunny in London"
            result = await governed_ts.call_tool(
                "get_weather", {"city": "London"}, mock_ctx, mock_tool
            )
        assert result == "Sunny in London"

    @pytest.mark.asyncio
    async def test_post_tool_monitor_mode_deny_allows(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """Post-tool DENY in Monitor mode should allow result through."""
        pre_allow = Adjudicated(Decision.Allow, reason="OK")
        post_deny_monitor = Adjudicated(Decision.Deny, reason="Output flagged")
        mock_harness.adjudicate = AsyncMock(side_effect=[pre_allow, post_deny_monitor])

        governed_ts = _first_governed_toolset(
            pydantic_agent, mock_harness, strategy=Strategy.BLOCK
        )
        mock_ctx = MagicMock()
        mock_tool = MagicMock()
        with patch.object(
            governed_ts.wrapped, "call_tool", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = "Sunny in London"
            result = await governed_ts.call_tool(
                "get_weather", {"city": "London"}, mock_ctx, mock_tool
            )
        assert result == "Sunny in London"

    @pytest.mark.asyncio
    async def test_post_tool_govern_mode_deny_returns_redacted_string(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """Post-tool DENY in Govern mode should return the redacted string, not raise."""
        pre_allow = Adjudicated(Decision.Allow, reason="OK")
        post_deny_govern = Adjudicated(
            Decision.Deny, reason="Output blocked", mode=Mode.Govern
        )
        mock_harness.adjudicate = AsyncMock(side_effect=[pre_allow, post_deny_govern])

        governed_ts = _first_governed_toolset(
            pydantic_agent, mock_harness, strategy=Strategy.BLOCK
        )
        mock_ctx = MagicMock()
        mock_tool = MagicMock()
        with patch.object(
            governed_ts.wrapped, "call_tool", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = "Sunny in London"
            result = await governed_ts.call_tool(
                "get_weather", {"city": "London"}, mock_ctx, mock_tool
            )
        assert result == _POST_TOOL_REDACTED
        assert "redacted by policy" in result
        assert "Do not retry" in result


# ---------------------------------------------------------------------------
# Tests: Escalate handling
# ---------------------------------------------------------------------------


class TestEscalateHandling:
    @pytest.mark.asyncio
    async def test_escalate_with_escalation_enabled_raises_approval_required(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """ESCALATE with enable_escalation=True raises pydantic_ai ApprovalRequired."""
        from pydantic_ai.exceptions import ApprovalRequired

        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(Decision.Escalate, reason="Needs human approval")
        )

        governed_ts = _first_governed_toolset(
            pydantic_agent,
            mock_harness,
            enable_escalation=True,
            include_tool_args_in_escalation=True,
        )
        mock_ctx = MagicMock()
        mock_tool = MagicMock()
        with pytest.raises(ApprovalRequired) as exc_info:
            await governed_ts.call_tool(
                "get_weather", {"city": "London"}, mock_ctx, mock_tool
            )
        metadata = exc_info.value.metadata
        assert metadata["tool_name"] == "get_weather"
        assert "Needs human approval" in metadata["reason"]
        assert metadata["tool_args"] == {"city": "London"}
        assert "sondera_call_id" in metadata

    @pytest.mark.asyncio
    async def test_escalate_without_escalation_raises_runtime_error(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """ESCALATE with enable_escalation=False (default) raises RuntimeError."""
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(Decision.Escalate, reason="Needs approval")
        )

        governed_ts = _first_governed_toolset(
            pydantic_agent,
            mock_harness,
            enable_escalation=False,
        )
        mock_ctx = MagicMock()
        mock_tool = MagicMock()
        with pytest.raises(RuntimeError, match="escalation is not enabled"):
            await governed_ts.call_tool(
                "get_weather", {"city": "London"}, mock_ctx, mock_tool
            )

    @pytest.mark.asyncio
    async def test_escalate_redacts_tool_args_by_default(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """With enable_escalation=True but include_tool_args_in_escalation=False, args are redacted."""
        from pydantic_ai.exceptions import ApprovalRequired

        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(Decision.Escalate, reason="Approval needed")
        )

        governed_ts = _first_governed_toolset(
            pydantic_agent,
            mock_harness,
            enable_escalation=True,
            include_tool_args_in_escalation=False,
        )
        mock_ctx = MagicMock()
        mock_tool = MagicMock()
        with pytest.raises(ApprovalRequired) as exc_info:
            await governed_ts.call_tool(
                "get_weather", {"city": "London"}, mock_ctx, mock_tool
            )
        metadata = exc_info.value.metadata
        assert "<redacted" in metadata["tool_args"]


# ---------------------------------------------------------------------------
# Tests: exception during run -> harness.fail()
# ---------------------------------------------------------------------------


class TestGovernedRunException:
    @pytest.mark.asyncio
    async def test_exception_calls_harness_fail(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """Exception during handler should call harness.fail(reason=...)."""
        agent_card = Agent(id="test", provider="pydantic-ai")
        provider = SonderaProvider()
        provider.govern(pydantic_agent, harness=mock_harness, agent_card=agent_card)

        lifecycle_fn = pydantic_agent.hooks.lifecycle_fn  # type: ignore[attr-defined]
        handler = AsyncMock(side_effect=RuntimeError("Model exploded"))

        with pytest.raises(RuntimeError, match="Model exploded"):
            await lifecycle_fn(MagicMock(), handler=handler)

        mock_harness.initialize.assert_awaited_once()
        mock_harness.fail.assert_awaited_once()
        fail_kwargs = mock_harness.fail.call_args.kwargs
        assert "Model exploded" in fail_kwargs["reason"]
        mock_harness.finalize.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: HarnessErrorPolicy
# ---------------------------------------------------------------------------


class TestHarnessErrorPolicy:
    @pytest.mark.asyncio
    async def test_fail_closed_raises_runtime_error_on_harness_error(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """FAIL_CLOSED: harness communication error raises RuntimeError."""
        mock_harness.adjudicate = AsyncMock(
            side_effect=ConnectionError("harness unreachable")
        )

        governed_ts = _first_governed_toolset(
            pydantic_agent,
            mock_harness,
            harness_error_policy=HarnessErrorPolicy.FAIL_CLOSED,
        )
        mock_ctx = MagicMock()
        mock_tool = MagicMock()
        with pytest.raises(RuntimeError, match="fail-closed"):
            await governed_ts.call_tool(
                "get_weather", {"city": "London"}, mock_ctx, mock_tool
            )

    @pytest.mark.asyncio
    async def test_fail_open_logs_and_proceeds_on_harness_error(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """FAIL_OPEN: harness communication error logs warning, tool executes."""
        mock_harness.adjudicate = AsyncMock(
            side_effect=ConnectionError("harness unreachable")
        )

        governed_ts = _first_governed_toolset(
            pydantic_agent,
            mock_harness,
            harness_error_policy=HarnessErrorPolicy.FAIL_OPEN,
        )
        mock_ctx = MagicMock()
        mock_tool = MagicMock()
        with patch.object(
            governed_ts.wrapped, "call_tool", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = "Sunny in London"
            result = await governed_ts.call_tool(
                "get_weather", {"city": "London"}, mock_ctx, mock_tool
            )
        assert result == "Sunny in London"
        mock_call.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_auth_error_always_fail_closed(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """Authentication errors should always fail-closed regardless of policy."""
        from sondera.exceptions import AuthenticationError

        mock_harness.adjudicate = AsyncMock(
            side_effect=AuthenticationError("bad token")
        )

        governed_ts = _first_governed_toolset(
            pydantic_agent,
            mock_harness,
            harness_error_policy=HarnessErrorPolicy.FAIL_OPEN,
        )
        mock_ctx = MagicMock()
        mock_tool = MagicMock()
        with pytest.raises(RuntimeError, match="authentication error"):
            await governed_ts.call_tool(
                "get_weather", {"city": "London"}, mock_ctx, mock_tool
            )

    @pytest.mark.asyncio
    async def test_post_tool_fail_open_returns_result(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """FAIL_OPEN: post-tool harness error returns the original result."""
        pre_allow = Adjudicated(Decision.Allow, reason="OK")
        mock_harness.adjudicate = AsyncMock(
            side_effect=[pre_allow, ConnectionError("harness unreachable")]
        )

        governed_ts = _first_governed_toolset(
            pydantic_agent,
            mock_harness,
            harness_error_policy=HarnessErrorPolicy.FAIL_OPEN,
        )
        mock_ctx = MagicMock()
        mock_tool = MagicMock()
        with patch.object(
            governed_ts.wrapped, "call_tool", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = "Sunny in London"
            result = await governed_ts.call_tool(
                "get_weather", {"city": "London"}, mock_ctx, mock_tool
            )
        assert result == "Sunny in London"


# ---------------------------------------------------------------------------
# Tests: acknowledge_fail_open
# ---------------------------------------------------------------------------


class TestAcknowledgeFailOpen:
    def test_fail_open_without_acknowledge_raises_value_error(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """FAIL_OPEN without acknowledge_fail_open=True should raise ValueError."""
        agent_card = Agent(id="test", provider="pydantic-ai")
        provider = SonderaProvider(harness_error_policy=HarnessErrorPolicy.FAIL_OPEN)
        with pytest.raises(ValueError, match="acknowledge_fail_open"):
            provider.govern(
                pydantic_agent,
                harness=mock_harness,
                agent_card=agent_card,
                acknowledge_fail_open=False,
            )

    def test_fail_open_with_acknowledge_succeeds(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """FAIL_OPEN with acknowledge_fail_open=True should succeed."""
        agent_card = Agent(id="test", provider="pydantic-ai")
        provider = SonderaProvider(harness_error_policy=HarnessErrorPolicy.FAIL_OPEN)
        # Should not raise
        provider.govern(
            pydantic_agent,
            harness=mock_harness,
            agent_card=agent_card,
            acknowledge_fail_open=True,
        )
        for ts in pydantic_agent.toolsets:
            assert isinstance(ts, SonderaGovernedToolset)

    def test_fail_closed_does_not_require_acknowledge(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """FAIL_CLOSED should not require acknowledge_fail_open."""
        agent_card = Agent(id="test", provider="pydantic-ai")
        provider = SonderaProvider(harness_error_policy=HarnessErrorPolicy.FAIL_CLOSED)
        # Should not raise
        provider.govern(pydantic_agent, harness=mock_harness, agent_card=agent_card)


# ---------------------------------------------------------------------------
# Tests: session_id passthrough
# ---------------------------------------------------------------------------


class TestSessionId:
    @pytest.mark.asyncio
    async def test_session_id_from_provider(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """session_id set on SonderaProvider should propagate to harness.initialize()."""
        agent_card = Agent(id="test", provider="pydantic-ai")
        provider = SonderaProvider(session_id="sess-provider")
        provider.govern(pydantic_agent, harness=mock_harness, agent_card=agent_card)

        lifecycle_fn = pydantic_agent.hooks.lifecycle_fn  # type: ignore[attr-defined]
        handler = AsyncMock(return_value=MagicMock(output="ok"))
        await lifecycle_fn(MagicMock(), handler=handler)

        init_kwargs = mock_harness.initialize.call_args.kwargs
        assert init_kwargs["session_id"] == "sess-provider"

    @pytest.mark.asyncio
    async def test_session_id_override_in_govern(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """session_id in govern() should override provider-level session_id."""
        agent_card = Agent(id="test", provider="pydantic-ai")
        provider = SonderaProvider(session_id="sess-provider")
        provider.govern(
            pydantic_agent,
            harness=mock_harness,
            agent_card=agent_card,
            session_id="sess-govern-override",
        )

        lifecycle_fn = pydantic_agent.hooks.lifecycle_fn  # type: ignore[attr-defined]
        handler = AsyncMock(return_value=MagicMock(output="ok"))
        await lifecycle_fn(MagicMock(), handler=handler)

        init_kwargs = mock_harness.initialize.call_args.kwargs
        assert init_kwargs["session_id"] == "sess-govern-override"


# ---------------------------------------------------------------------------
# Tests: call_id uniqueness
# ---------------------------------------------------------------------------


class TestCallIdUniqueness:
    @pytest.mark.asyncio
    async def test_call_ids_are_unique(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """Each tool call should generate a unique call_id."""
        call_ids: list[str] = []

        allow_result = Adjudicated(Decision.Allow, reason="OK")

        async def capture_call_id(event):
            if hasattr(event.event, "call_id") and event.event.call_id:
                call_ids.append(event.event.call_id)
            return allow_result

        mock_harness.adjudicate = AsyncMock(side_effect=capture_call_id)

        governed_ts = _first_governed_toolset(
            pydantic_agent, mock_harness, strategy=Strategy.BLOCK
        )
        mock_ctx = MagicMock()
        mock_tool = MagicMock()

        with patch.object(
            governed_ts.wrapped, "call_tool", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = "result"
            await governed_ts.call_tool(
                "get_weather", {"city": "London"}, mock_ctx, mock_tool
            )
            await governed_ts.call_tool(
                "get_weather", {"city": "London"}, mock_ctx, mock_tool
            )

        # Each call generates a pre-tool and post-tool event, both sharing the same call_id.
        # We should have 4 captured call_ids: 2 unique pairs.
        assert len(call_ids) == 4
        pre_tool_ids = [call_ids[0], call_ids[2]]
        assert pre_tool_ids[0] != pre_tool_ids[1], (
            "call_ids must be unique across calls"
        )


# ---------------------------------------------------------------------------
# Tests: non-serializable tool output
# ---------------------------------------------------------------------------


class TestNonSerializableOutput:
    @pytest.mark.asyncio
    async def test_non_serializable_output_does_not_crash(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """Tool output that cannot be JSON-serialized should fall back to str()."""
        governed_ts = _first_governed_toolset(
            pydantic_agent, mock_harness, strategy=Strategy.BLOCK
        )
        mock_ctx = MagicMock()
        mock_tool = MagicMock()

        with patch.object(
            governed_ts.wrapped, "call_tool", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = object()  # not JSON-serializable
            result = await governed_ts.call_tool(
                "get_weather", {"city": "London"}, mock_ctx, mock_tool
            )
            assert result is not None


# ---------------------------------------------------------------------------
# Tests: default strategy
# ---------------------------------------------------------------------------


class TestDefaultStrategy:
    def test_provider_default_strategy_is_block(self):
        """SonderaProvider default strategy should be BLOCK."""
        provider = SonderaProvider()
        assert provider._strategy == Strategy.BLOCK

    def test_provider_default_harness_error_policy_is_fail_closed(self):
        """SonderaProvider default harness_error_policy should be FAIL_CLOSED."""
        provider = SonderaProvider()
        assert provider._harness_error_policy == HarnessErrorPolicy.FAIL_CLOSED

    def test_provider_default_enable_escalation_is_false(self):
        """SonderaProvider default enable_escalation should be False."""
        provider = SonderaProvider()
        assert provider._enable_escalation is False


# ---------------------------------------------------------------------------
# Tests: toolset ID
# ---------------------------------------------------------------------------


class TestGovernedToolsetId:
    def test_governed_toolset_id(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """SonderaGovernedToolset.id should be prefixed with 'sondera-governed-'."""
        governed_ts = _first_governed_toolset(pydantic_agent, mock_harness)
        assert governed_ts.id is not None
        assert governed_ts.id.startswith("sondera-governed-")


# ---------------------------------------------------------------------------
# Tests: bypass when agent/trajectory_id is None
# ---------------------------------------------------------------------------


class TestBypassWhenUninitialized:
    @pytest.mark.asyncio
    async def test_no_adjudication_when_agent_is_none(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """When harness.agent is None, tool calls bypass adjudication entirely."""
        mock_harness.agent = None

        governed_ts = _first_governed_toolset(
            pydantic_agent, mock_harness, strategy=Strategy.BLOCK
        )
        mock_ctx = MagicMock()
        mock_tool = MagicMock()

        with patch.object(
            governed_ts.wrapped, "call_tool", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = "Sunny in London"
            result = await governed_ts.call_tool(
                "get_weather", {"city": "London"}, mock_ctx, mock_tool
            )
        assert result == "Sunny in London"
        mock_harness.adjudicate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_adjudication_when_trajectory_id_is_none(
        self, pydantic_agent: PydanticAgent, mock_harness: MagicMock
    ):
        """When harness.trajectory_id is None, tool calls bypass adjudication."""
        mock_harness.trajectory_id = None

        governed_ts = _first_governed_toolset(
            pydantic_agent, mock_harness, strategy=Strategy.BLOCK
        )
        mock_ctx = MagicMock()
        mock_tool = MagicMock()

        with patch.object(
            governed_ts.wrapped, "call_tool", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = "Sunny in London"
            result = await governed_ts.call_tool(
                "get_weather", {"city": "London"}, mock_ctx, mock_tool
            )
        assert result == "Sunny in London"
        mock_harness.adjudicate.assert_not_awaited()
