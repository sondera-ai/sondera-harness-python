"""Tests for SonderaProvider with native pydantic-ai Hooks API.

These tests drive the four hook callables registered by ``govern()`` directly,
using a mock harness. The hook callables are extracted from the agent's
``_root_capability`` via ``_extract_sondera_hooks`` rather than running a full
agent loop -- this keeps the tests focused on adjudication behaviour without
requiring a model to actually be called.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic_ai.capabilities import Hooks
from pydantic_ai.exceptions import (
    ApprovalRequired,
    ModelRetry,
    SkipToolExecution,
)

from pydantic_ai import Agent as PydanticAgent
from sondera import Adjudicated, Agent, Decision, HarnessErrorPolicy, Mode, Strategy
from sondera.harness import Harness
from sondera.pydantic.provider import (
    _POST_TOOL_REDACTED,
    SonderaProvider,
)

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_harness() -> MagicMock:
    """Create a mock harness that allows everything by default."""
    harness = MagicMock(spec=Harness)
    harness.initialize = AsyncMock()
    harness.finalize = AsyncMock()
    harness.fail = AsyncMock()
    harness.adjudicate = AsyncMock(
        return_value=Adjudicated(Decision.ALLOW, reason="Allowed")
    )
    harness.agent = Agent(id="test-agent", provider="pydantic-ai")
    harness.trajectory_id = "traj-123"
    return harness


@pytest.fixture
def pydantic_agent() -> PydanticAgent:
    """Create a simple Pydantic AI agent with one tool."""
    agent = PydanticAgent("test")

    @agent.tool_plain
    def get_weather(city: str) -> str:
        """Get weather for a city."""
        return f"Sunny in {city}"

    return agent


@pytest.fixture
def agent_card() -> Agent:
    return Agent(id="test", provider="pydantic-ai")


def _extract_sondera_hooks(agent: PydanticAgent) -> Hooks:
    """Extract the Hooks instance registered by ``provider.govern()``."""
    root = agent._root_capability  # noqa: SLF001
    for sub in getattr(root, "capabilities", []):
        if isinstance(sub, Hooks):
            return sub
    raise AssertionError("No Sondera Hooks capability found on agent")


def _hook_func(hooks: Hooks, key: str) -> Any:
    """Pull the first registered handler for a hook key."""
    entries = hooks._registry.get(key)  # noqa: SLF001
    assert entries, f"No handler registered for {key}"
    return entries[0].func


def _tool_call_part(name: str = "get_weather", call_id: str = "call-1") -> Any:
    """Build a minimal stand-in for ``ToolCallPart``."""
    part = MagicMock()
    part.tool_name = name
    part.tool_call_id = call_id
    return part


# ---------------------------------------------------------------------------
# build_agent_card
# ---------------------------------------------------------------------------


class TestBuildAgentCard:
    def test_build_agent_card_from_pydantic_agent(self, pydantic_agent: PydanticAgent):
        provider = SonderaProvider()
        card = provider.build_agent_card(
            pydantic_agent, agent_id="weather-agent", name="Weather Bot"
        )
        assert card.id == "weather-agent"
        assert card.provider == "pydantic-ai"
        react_card = card.card.react_card
        assert react_card is not None
        assert "get_weather" in [t.name for t in react_card.tools]


# ---------------------------------------------------------------------------
# govern() mutation, idempotency, fail-open ack
# ---------------------------------------------------------------------------


class TestGovernMutatesAgent:
    def test_govern_returns_none(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        provider = SonderaProvider()
        assert (
            provider.govern(pydantic_agent, harness=mock_harness, agent_card=agent_card)
            is None
        )

    def test_govern_attaches_hooks_capability(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        SonderaProvider().govern(
            pydantic_agent, harness=mock_harness, agent_card=agent_card
        )
        hooks = _extract_sondera_hooks(pydantic_agent)
        registry = hooks._registry  # noqa: SLF001
        assert "wrap_run" in registry
        assert "before_model_request" in registry
        assert "after_model_request" in registry
        assert "wrap_tool_execute" in registry

    def test_govern_places_hooks_outermost(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        """Sondera hooks must be the OUTERMOST entry in the composed capability.

        ``CombinedCapability`` builds wrap chains by iterating
        ``reversed(self.capabilities)``, so the first entry in the list is the
        outermost wrapper. If any pre-existing capability short-circuits
        without invoking its inner handler, only outer hooks fire. Putting
        Sondera anywhere except first would create a policy-bypass surface.
        """
        SonderaProvider().govern(
            pydantic_agent, harness=mock_harness, agent_card=agent_card
        )
        root = pydantic_agent._root_capability  # noqa: SLF001
        assert isinstance(root.capabilities[0], Hooks), (
            f"Sondera Hooks must be the first (outermost) capability; got "
            f"{type(root.capabilities[0]).__name__} first."
        )

    def test_govern_marks_agent(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        SonderaProvider().govern(
            pydantic_agent, harness=mock_harness, agent_card=agent_card
        )
        assert pydantic_agent._sondera_governed is True


class TestGovernIdempotency:
    """Issue 4 regression: second govern() must raise loudly."""

    def test_second_govern_raises_runtime_error(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        provider = SonderaProvider()
        provider.govern(pydantic_agent, harness=mock_harness, agent_card=agent_card)
        with pytest.raises(RuntimeError, match="already been applied"):
            provider.govern(pydantic_agent, harness=mock_harness, agent_card=agent_card)


class TestAcknowledgeFailOpen:
    def test_fail_open_requires_acknowledgement(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        provider = SonderaProvider(harness_error_policy=HarnessErrorPolicy.FAIL_OPEN)
        with pytest.raises(ValueError, match="acknowledge_fail_open"):
            provider.govern(pydantic_agent, harness=mock_harness, agent_card=agent_card)

    def test_fail_open_with_ack_succeeds(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        provider = SonderaProvider(harness_error_policy=HarnessErrorPolicy.FAIL_OPEN)
        provider.govern(
            pydantic_agent,
            harness=mock_harness,
            agent_card=agent_card,
            acknowledge_fail_open=True,
        )
        assert pydantic_agent._sondera_governed is True

    def test_fail_closed_does_not_require_acknowledge(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        """Default FAIL_CLOSED never trips the ack guard, even without it set."""
        provider = SonderaProvider(harness_error_policy=HarnessErrorPolicy.FAIL_CLOSED)
        provider.govern(pydantic_agent, harness=mock_harness, agent_card=agent_card)
        assert pydantic_agent._sondera_governed is True


# ---------------------------------------------------------------------------
# wrap_run lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_full_lifecycle_calls_initialize_and_finalize(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        SonderaProvider().govern(
            pydantic_agent, harness=mock_harness, agent_card=agent_card
        )
        lifecycle = _hook_func(_extract_sondera_hooks(pydantic_agent), "wrap_run")

        handler = AsyncMock(return_value="ok")
        result = await lifecycle(MagicMock(), handler=handler)

        assert result == "ok"
        mock_harness.initialize.assert_awaited_once()
        mock_harness.finalize.assert_awaited_once()
        mock_harness.fail.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_exception_calls_harness_fail(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        SonderaProvider().govern(
            pydantic_agent, harness=mock_harness, agent_card=agent_card
        )
        lifecycle = _hook_func(_extract_sondera_hooks(pydantic_agent), "wrap_run")

        handler = AsyncMock(side_effect=RuntimeError("Model exploded"))
        with pytest.raises(RuntimeError, match="Model exploded"):
            await lifecycle(MagicMock(), handler=handler)

        mock_harness.initialize.assert_awaited_once()
        mock_harness.fail.assert_awaited_once()
        assert "Model exploded" in mock_harness.fail.call_args.kwargs["reason"]
        mock_harness.finalize.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_provider_session_id_passed_to_initialize(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        SonderaProvider(session_id="provider-session").govern(
            pydantic_agent, harness=mock_harness, agent_card=agent_card
        )
        lifecycle = _hook_func(_extract_sondera_hooks(pydantic_agent), "wrap_run")
        await lifecycle(MagicMock(), handler=AsyncMock(return_value="ok"))
        assert (
            mock_harness.initialize.call_args.kwargs["session_id"] == "provider-session"
        )

    @pytest.mark.asyncio
    async def test_govern_session_id_overrides_provider(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        SonderaProvider(session_id="provider-session").govern(
            pydantic_agent,
            harness=mock_harness,
            agent_card=agent_card,
            session_id="govern-session",
        )
        lifecycle = _hook_func(_extract_sondera_hooks(pydantic_agent), "wrap_run")
        await lifecycle(MagicMock(), handler=AsyncMock(return_value="ok"))
        assert (
            mock_harness.initialize.call_args.kwargs["session_id"] == "govern-session"
        )


# ---------------------------------------------------------------------------
# wrap_tool_execute
# ---------------------------------------------------------------------------


def _governed(
    agent: PydanticAgent,
    harness: MagicMock,
    card: Agent,
    *,
    strategy: Strategy = Strategy.BLOCK,
    harness_error_policy: HarnessErrorPolicy = HarnessErrorPolicy.FAIL_CLOSED,
    enable_escalation: bool = False,
    include_tool_args_in_escalation: bool = False,
    acknowledge_fail_open: bool = False,
) -> Any:
    """Apply ``govern()`` and return the wrap_tool_execute hook function."""
    provider = SonderaProvider(
        strategy=strategy,
        harness_error_policy=harness_error_policy,
        enable_escalation=enable_escalation,
        include_tool_args_in_escalation=include_tool_args_in_escalation,
    )
    provider.govern(
        agent,
        harness=harness,
        agent_card=card,
        acknowledge_fail_open=acknowledge_fail_open,
    )
    return _hook_func(_extract_sondera_hooks(agent), "wrap_tool_execute")


class TestToolHookAllow:
    @pytest.mark.asyncio
    async def test_allow_returns_handler_result(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        tool_hook = _governed(pydantic_agent, mock_harness, agent_card)
        handler = AsyncMock(return_value="Sunny in London")
        result = await tool_hook(
            MagicMock(),
            call=_tool_call_part(),
            tool_def=MagicMock(),
            args={"city": "London"},
            handler=handler,
        )
        assert result == "Sunny in London"
        handler.assert_awaited_once()


class TestToolHookDeny:
    @pytest.mark.asyncio
    async def test_deny_block_govern_raises_skip_tool_execution(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(
                Decision.DENY, reason="Forbidden", mode=Mode.GOVERN
            )
        )
        tool_hook = _governed(
            pydantic_agent, mock_harness, agent_card, strategy=Strategy.BLOCK
        )
        with pytest.raises(SkipToolExecution) as exc_info:
            await tool_hook(
                MagicMock(),
                call=_tool_call_part(),
                tool_def=MagicMock(),
                args={"city": "London"},
                handler=AsyncMock(),
            )
        assert "denied" in exc_info.value.result.lower()

    @pytest.mark.asyncio
    async def test_deny_steer_govern_raises_model_retry(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(Decision.DENY, reason="Blocked", mode=Mode.GOVERN)
        )
        tool_hook = _governed(
            pydantic_agent, mock_harness, agent_card, strategy=Strategy.STEER
        )
        with pytest.raises(ModelRetry, match="different approach"):
            await tool_hook(
                MagicMock(),
                call=_tool_call_part(),
                tool_def=MagicMock(),
                args={"city": "London"},
                handler=AsyncMock(),
            )

    @pytest.mark.asyncio
    async def test_deny_monitor_mode_allows_execution(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(Decision.DENY, reason="Would block")
        )
        tool_hook = _governed(pydantic_agent, mock_harness, agent_card)
        handler = AsyncMock(return_value="Sunny in London")
        result = await tool_hook(
            MagicMock(),
            call=_tool_call_part(),
            tool_def=MagicMock(),
            args={"city": "London"},
            handler=handler,
        )
        assert result == "Sunny in London"

    @pytest.mark.asyncio
    async def test_deny_steer_mode_allows_execution(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        """A DENY in Mode.STEER (server-side) is observe-only -- the tool
        runs even though the local Strategy would otherwise block it."""
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(Decision.DENY, reason="Steered", mode=Mode.STEER)
        )
        tool_hook = _governed(
            pydantic_agent, mock_harness, agent_card, strategy=Strategy.BLOCK
        )
        handler = AsyncMock(return_value="Sunny in London")
        result = await tool_hook(
            MagicMock(),
            call=_tool_call_part(),
            tool_def=MagicMock(),
            args={"city": "London"},
            handler=handler,
        )
        assert result == "Sunny in London"


class TestToolHookPostExecuteRedaction:
    @pytest.mark.asyncio
    async def test_post_tool_govern_deny_returns_redacted_string(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.adjudicate = AsyncMock(
            side_effect=[
                Adjudicated(Decision.ALLOW, reason="OK"),
                Adjudicated(Decision.DENY, reason="Output blocked", mode=Mode.GOVERN),
            ]
        )
        tool_hook = _governed(pydantic_agent, mock_harness, agent_card)
        result = await tool_hook(
            MagicMock(),
            call=_tool_call_part(),
            tool_def=MagicMock(),
            args={"city": "London"},
            handler=AsyncMock(return_value="Sunny in London"),
        )
        assert result == _POST_TOOL_REDACTED

    @pytest.mark.asyncio
    async def test_post_tool_monitor_deny_allows_result_through(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.adjudicate = AsyncMock(
            side_effect=[
                Adjudicated(Decision.ALLOW, reason="OK"),
                Adjudicated(Decision.DENY, reason="Would redact"),
            ]
        )
        tool_hook = _governed(pydantic_agent, mock_harness, agent_card)
        result = await tool_hook(
            MagicMock(),
            call=_tool_call_part(),
            tool_def=MagicMock(),
            args={"city": "London"},
            handler=AsyncMock(return_value="Sunny in London"),
        )
        assert result == "Sunny in London"


class TestToolHookEscalate:
    @pytest.mark.asyncio
    async def test_escalate_with_escalation_enabled_raises(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(Decision.ESCALATE, reason="Needs approval")
        )
        tool_hook = _governed(
            pydantic_agent,
            mock_harness,
            agent_card,
            enable_escalation=True,
            include_tool_args_in_escalation=True,
        )
        with pytest.raises(ApprovalRequired) as exc_info:
            await tool_hook(
                MagicMock(),
                call=_tool_call_part(),
                tool_def=MagicMock(),
                args={"city": "London"},
                handler=AsyncMock(),
            )
        meta = exc_info.value.metadata
        assert meta["tool_name"] == "get_weather"
        assert meta["tool_args"] == {"city": "London"}
        assert "Needs approval" in meta["reason"]
        assert meta["sondera_call_id"] == "call-1"

    @pytest.mark.asyncio
    async def test_escalate_redacts_args_by_default(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(Decision.ESCALATE, reason="Needs approval")
        )
        tool_hook = _governed(
            pydantic_agent,
            mock_harness,
            agent_card,
            enable_escalation=True,
            include_tool_args_in_escalation=False,
        )
        with pytest.raises(ApprovalRequired) as exc_info:
            await tool_hook(
                MagicMock(),
                call=_tool_call_part(),
                tool_def=MagicMock(),
                args={"city": "London"},
                handler=AsyncMock(),
            )
        assert "<redacted" in exc_info.value.metadata["tool_args"]

    @pytest.mark.asyncio
    async def test_escalate_without_escalation_raises_runtime_error(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(Decision.ESCALATE, reason="Needs approval")
        )
        tool_hook = _governed(pydantic_agent, mock_harness, agent_card)
        with pytest.raises(RuntimeError, match="escalation is not enabled"):
            await tool_hook(
                MagicMock(),
                call=_tool_call_part(),
                tool_def=MagicMock(),
                args={"city": "London"},
                handler=AsyncMock(),
            )


class TestEscalateApprovalKey:
    """Issue 3 regression: distinct calls with identical args must escalate independently."""

    @pytest.mark.asyncio
    async def test_two_identical_calls_escalate_independently(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(Decision.ESCALATE, reason="Needs approval")
        )
        tool_hook = _governed(
            pydantic_agent,
            mock_harness,
            agent_card,
            enable_escalation=True,
        )

        # First invocation: distinct call_id
        with pytest.raises(ApprovalRequired) as exc1:
            await tool_hook(
                MagicMock(),
                call=_tool_call_part(call_id="call-A"),
                tool_def=MagicMock(),
                args={"city": "London"},
                handler=AsyncMock(),
            )
        assert exc1.value.metadata["sondera_call_id"] == "call-A"

        # Second invocation with identical args but different call_id must
        # also escalate -- not auto-approve.
        with pytest.raises(ApprovalRequired) as exc2:
            await tool_hook(
                MagicMock(),
                call=_tool_call_part(call_id="call-B"),
                tool_def=MagicMock(),
                args={"city": "London"},
                handler=AsyncMock(),
            )
        assert exc2.value.metadata["sondera_call_id"] == "call-B"

    @pytest.mark.asyncio
    async def test_re_invocation_with_same_call_id_after_approval_does_not_re_escalate(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        """Issue 3 second half: when pydantic-ai re-invokes a previously
        escalated call (same tool_call_id, after the deferred-approval loop
        resolves), the hook must NOT re-escalate -- it must run the handler.
        Without this, escalations would loop forever.
        """
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(Decision.ESCALATE, reason="Needs approval")
        )
        tool_hook = _governed(
            pydantic_agent, mock_harness, agent_card, enable_escalation=True
        )

        # First invocation -- the user-approval loop registers call-A.
        with pytest.raises(ApprovalRequired):
            await tool_hook(
                MagicMock(),
                call=_tool_call_part(call_id="call-A"),
                tool_def=MagicMock(),
                args={"city": "London"},
                handler=AsyncMock(),
            )

        # pydantic-ai re-invokes the SAME call_id after approval.
        # Note: the harness still says ESCALATE on the pre-tool event, but
        # the provider's per-call dedup short-circuits and runs the handler.
        handler = AsyncMock(return_value="Sunny in London")
        result = await tool_hook(
            MagicMock(),
            call=_tool_call_part(call_id="call-A"),
            tool_def=MagicMock(),
            args={"city": "London"},
            handler=handler,
        )
        assert result == "Sunny in London"
        handler.assert_awaited_once()


class TestCallIdEventCorrelation:
    """Verify the harness sees the pydantic-ai-issued tool_call_id in events.

    Two distinct invocations should produce two distinct ToolCall events with
    different ``call_id`` values, even when the tool name and args match.
    """

    @pytest.mark.asyncio
    async def test_call_ids_propagate_into_harness_events(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        tool_hook = _governed(pydantic_agent, mock_harness, agent_card)
        for cid in ("call-X", "call-Y"):
            await tool_hook(
                MagicMock(),
                call=_tool_call_part(call_id=cid),
                tool_def=MagicMock(),
                args={"city": "London"},
                handler=AsyncMock(return_value="Sunny"),
            )
        # adjudicate is called for pre-tool + post-tool per invocation.
        # Pull the pre-tool events (every other call) and verify call_id.
        events = [c.args[0] for c in mock_harness.adjudicate.await_args_list]
        pre_tool_events = events[::2]
        seen_call_ids = {e.event.call_id for e in pre_tool_events}
        assert seen_call_ids == {"call-X", "call-Y"}


class TestToolHookHarnessErrorPolicy:
    @pytest.mark.asyncio
    async def test_fail_closed_pre_tool_raises_runtime_error(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.adjudicate = AsyncMock(side_effect=ConnectionError("boom"))
        tool_hook = _governed(
            pydantic_agent,
            mock_harness,
            agent_card,
            harness_error_policy=HarnessErrorPolicy.FAIL_CLOSED,
        )
        with pytest.raises(RuntimeError, match="fail-closed"):
            await tool_hook(
                MagicMock(),
                call=_tool_call_part(),
                tool_def=MagicMock(),
                args={"city": "London"},
                handler=AsyncMock(),
            )

    @pytest.mark.asyncio
    async def test_fail_open_pre_tool_proceeds(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.adjudicate = AsyncMock(side_effect=ConnectionError("boom"))
        tool_hook = _governed(
            pydantic_agent,
            mock_harness,
            agent_card,
            harness_error_policy=HarnessErrorPolicy.FAIL_OPEN,
            acknowledge_fail_open=True,
        )
        result = await tool_hook(
            MagicMock(),
            call=_tool_call_part(),
            tool_def=MagicMock(),
            args={"city": "London"},
            handler=AsyncMock(return_value="Sunny in London"),
        )
        assert result == "Sunny in London"

    @pytest.mark.asyncio
    async def test_fail_open_post_tool_returns_handler_result(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        """Post-tool harness error under FAIL_OPEN must return the handler's
        actual result -- not the redacted string and not a raise."""
        mock_harness.adjudicate = AsyncMock(
            side_effect=[
                Adjudicated(Decision.ALLOW, reason="OK"),  # pre-tool succeeds
                ConnectionError("post-tool harness exploded"),  # post-tool errs
            ]
        )
        tool_hook = _governed(
            pydantic_agent,
            mock_harness,
            agent_card,
            harness_error_policy=HarnessErrorPolicy.FAIL_OPEN,
            acknowledge_fail_open=True,
        )
        result = await tool_hook(
            MagicMock(),
            call=_tool_call_part(),
            tool_def=MagicMock(),
            args={"city": "London"},
            handler=AsyncMock(return_value="Sunny in London"),
        )
        assert result == "Sunny in London"

    @pytest.mark.asyncio
    async def test_authentication_error_always_fail_closed(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        from sondera.exceptions import AuthenticationError

        mock_harness.adjudicate = AsyncMock(side_effect=AuthenticationError("nope"))
        tool_hook = _governed(
            pydantic_agent,
            mock_harness,
            agent_card,
            harness_error_policy=HarnessErrorPolicy.FAIL_OPEN,
            acknowledge_fail_open=True,
        )
        with pytest.raises(RuntimeError, match="authentication"):
            await tool_hook(
                MagicMock(),
                call=_tool_call_part(),
                tool_def=MagicMock(),
                args={"city": "London"},
                handler=AsyncMock(),
            )


class TestNonSerializableOutput:
    @pytest.mark.asyncio
    async def test_non_serializable_falls_back_to_str(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        class _NotJson:
            def __str__(self) -> str:
                return "<NotJson>"

        tool_hook = _governed(pydantic_agent, mock_harness, agent_card)
        result = await tool_hook(
            MagicMock(),
            call=_tool_call_part(),
            tool_def=MagicMock(),
            args={"city": "London"},
            handler=AsyncMock(return_value=_NotJson()),
        )
        # POST event submission should have succeeded with str() fallback
        assert mock_harness.adjudicate.await_count == 2  # pre + post
        assert isinstance(result, _NotJson)


class TestBypassWhenUninitialized:
    @pytest.mark.asyncio
    async def test_bypass_when_agent_none(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.agent = None
        tool_hook = _governed(pydantic_agent, mock_harness, agent_card)
        handler = AsyncMock(return_value="Sunny")
        result = await tool_hook(
            MagicMock(),
            call=_tool_call_part(),
            tool_def=MagicMock(),
            args={"city": "London"},
            handler=handler,
        )
        assert result == "Sunny"
        mock_harness.adjudicate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_bypass_when_trajectory_id_none(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.trajectory_id = None
        tool_hook = _governed(pydantic_agent, mock_harness, agent_card)
        result = await tool_hook(
            MagicMock(),
            call=_tool_call_part(),
            tool_def=MagicMock(),
            args={"city": "London"},
            handler=AsyncMock(return_value="Sunny"),
        )
        assert result == "Sunny"
        mock_harness.adjudicate.assert_not_awaited()


class TestDefaultStrategy:
    def test_default_strategy_is_block(self):
        provider = SonderaProvider()
        assert provider._strategy == Strategy.BLOCK

    def test_default_harness_error_policy_is_fail_closed(self):
        provider = SonderaProvider()
        assert provider._harness_error_policy == HarnessErrorPolicy.FAIL_CLOSED

    def test_default_enable_escalation_is_false(self):
        provider = SonderaProvider()
        assert provider._enable_escalation is False


class TestEndToEndAgentRun:
    """End-to-end smoke test against ``agent.run`` to insure against
    pydantic-ai internals changing under us (``hooks._registry`` is private).

    Other tests in this file reach into the registry directly to invoke
    individual hook callables; this test runs a real agent and asserts
    that adjudication actually fires, so a future pydantic-ai refactor
    can't silently bypass us.
    """

    @pytest.mark.asyncio
    async def test_run_fires_pre_model_adjudication(
        self,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        from pydantic_ai.models.test import TestModel

        # TestModel returns canned text without making any network call.
        agent = PydanticAgent(TestModel(custom_output_text="hi"))
        SonderaProvider().govern(agent, harness=mock_harness, agent_card=agent_card)
        result = await agent.run("hello")
        assert result.output == "hi"
        # Adjudicate is called for both the user prompt (before_model_request)
        # and the assistant response (after_model_request), so >= 2 awaits.
        assert mock_harness.adjudicate.await_count >= 2
        mock_harness.initialize.assert_awaited_once()
        mock_harness.finalize.assert_awaited_once()
