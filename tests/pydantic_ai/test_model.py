"""Tests for the before/after_model_request hooks registered by govern().

Covers pre-prompt adjudication (raises ``SkipModelRequest`` on Deny+Govern),
post-response adjudication (substitutes a denial response on Deny+Govern), and
the model layer's compliance with ``HarnessErrorPolicy`` -- which the previous
``WrapperModel``-based implementation silently ignored (issue 2).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic_ai.capabilities import Hooks
from pydantic_ai.exceptions import SkipModelRequest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from pydantic_ai import Agent as PydanticAgent
from sondera import Adjudicated, Agent, Decision, HarnessErrorPolicy, Mode
from sondera.harness import Harness
from sondera.pydantic.provider import SonderaProvider

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_harness() -> MagicMock:
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
    return PydanticAgent("test")


@pytest.fixture
def agent_card() -> Agent:
    return Agent(id="test", provider="pydantic-ai")


def _extract_hooks(agent: PydanticAgent) -> Hooks:
    root = agent._root_capability  # noqa: SLF001
    for sub in getattr(root, "capabilities", []):
        if isinstance(sub, Hooks):
            return sub
    raise AssertionError("No Sondera Hooks capability found")


def _hook(hooks: Hooks, key: str) -> Any:
    entries = hooks._registry.get(key)  # noqa: SLF001
    assert entries, f"No handler registered for {key}"
    return entries[0].func


def _request_context(text: str = "Hello") -> Any:
    ctx = MagicMock()
    ctx.messages = [ModelRequest(parts=[UserPromptPart(content=text)])]
    return ctx


def _response(text: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(content=text)])


def _govern(
    agent: PydanticAgent,
    harness: MagicMock,
    card: Agent,
    *,
    harness_error_policy: HarnessErrorPolicy = HarnessErrorPolicy.FAIL_CLOSED,
    acknowledge_fail_open: bool = False,
) -> Hooks:
    SonderaProvider(harness_error_policy=harness_error_policy).govern(
        agent,
        harness=harness,
        agent_card=card,
        acknowledge_fail_open=acknowledge_fail_open,
    )
    return _extract_hooks(agent)


# ---------------------------------------------------------------------------
# before_model_request -- pre-prompt adjudication
# ---------------------------------------------------------------------------


class TestPreModelAllow:
    @pytest.mark.asyncio
    async def test_allow_returns_request_context_unchanged(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        hooks = _govern(pydantic_agent, mock_harness, agent_card)
        pre = _hook(hooks, "before_model_request")
        ctx = _request_context("Hi")
        result = await pre(MagicMock(), ctx)
        assert result is ctx
        mock_harness.adjudicate.assert_awaited_once()


class TestPreModelDeny:
    @pytest.mark.asyncio
    async def test_deny_govern_raises_skip_model_request(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(
                Decision.DENY, reason="Blocked by policy", mode=Mode.GOVERN
            )
        )
        hooks = _govern(pydantic_agent, mock_harness, agent_card)
        pre = _hook(hooks, "before_model_request")
        with pytest.raises(SkipModelRequest) as exc_info:
            await pre(MagicMock(), _request_context("Hi"))
        denial = exc_info.value.response
        assert isinstance(denial, ModelResponse)
        text = " ".join(p.content for p in denial.parts if isinstance(p, TextPart))
        assert "Blocked by policy" in text

    @pytest.mark.asyncio
    async def test_deny_monitor_mode_allows_request_through(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(Decision.DENY, reason="Would block")
        )
        hooks = _govern(pydantic_agent, mock_harness, agent_card)
        pre = _hook(hooks, "before_model_request")
        ctx = _request_context("Hi")
        result = await pre(MagicMock(), ctx)
        assert result is ctx


class TestPreModelHarnessErrorPolicy:
    """Issue 2 regression: pre-model layer must respect HarnessErrorPolicy."""

    @pytest.mark.asyncio
    async def test_fail_closed_pre_model_raises(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.adjudicate = AsyncMock(side_effect=ConnectionError("boom"))
        hooks = _govern(
            pydantic_agent,
            mock_harness,
            agent_card,
            harness_error_policy=HarnessErrorPolicy.FAIL_CLOSED,
        )
        pre = _hook(hooks, "before_model_request")
        with pytest.raises(RuntimeError, match="fail-closed"):
            await pre(MagicMock(), _request_context("Hi"))

    @pytest.mark.asyncio
    async def test_fail_open_pre_model_proceeds(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.adjudicate = AsyncMock(side_effect=ConnectionError("boom"))
        hooks = _govern(
            pydantic_agent,
            mock_harness,
            agent_card,
            harness_error_policy=HarnessErrorPolicy.FAIL_OPEN,
            acknowledge_fail_open=True,
        )
        pre = _hook(hooks, "before_model_request")
        ctx = _request_context("Hi")
        result = await pre(MagicMock(), ctx)
        assert result is ctx


# ---------------------------------------------------------------------------
# after_model_request -- post-response adjudication
# ---------------------------------------------------------------------------


class TestPostModelAllow:
    @pytest.mark.asyncio
    async def test_allow_returns_response_unchanged(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        hooks = _govern(pydantic_agent, mock_harness, agent_card)
        post = _hook(hooks, "after_model_request")
        resp = _response("Sunny in London")
        result = await post(MagicMock(), _request_context(), resp)
        assert result is resp


class TestPostModelDeny:
    @pytest.mark.asyncio
    async def test_deny_govern_returns_substituted_denial(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(
                Decision.DENY, reason="Response forbidden", mode=Mode.GOVERN
            )
        )
        hooks = _govern(pydantic_agent, mock_harness, agent_card)
        post = _hook(hooks, "after_model_request")
        original = _response("Sunny")
        result = await post(MagicMock(), _request_context(), original)
        assert result is not original
        assert isinstance(result, ModelResponse)
        text = " ".join(p.content for p in result.parts if isinstance(p, TextPart))
        assert "Response forbidden" in text

    @pytest.mark.asyncio
    async def test_deny_monitor_mode_returns_original_response(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(Decision.DENY, reason="Would redact")
        )
        hooks = _govern(pydantic_agent, mock_harness, agent_card)
        post = _hook(hooks, "after_model_request")
        original = _response("Sunny")
        result = await post(MagicMock(), _request_context(), original)
        assert result is original


class TestPostModelHarnessErrorPolicy:
    @pytest.mark.asyncio
    async def test_fail_closed_post_model_raises(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.adjudicate = AsyncMock(side_effect=ConnectionError("boom"))
        hooks = _govern(
            pydantic_agent,
            mock_harness,
            agent_card,
            harness_error_policy=HarnessErrorPolicy.FAIL_CLOSED,
        )
        post = _hook(hooks, "after_model_request")
        with pytest.raises(RuntimeError, match="fail-closed"):
            await post(MagicMock(), _request_context(), _response("Sunny"))

    @pytest.mark.asyncio
    async def test_fail_open_post_model_returns_original(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.adjudicate = AsyncMock(side_effect=ConnectionError("boom"))
        hooks = _govern(
            pydantic_agent,
            mock_harness,
            agent_card,
            harness_error_policy=HarnessErrorPolicy.FAIL_OPEN,
            acknowledge_fail_open=True,
        )
        post = _hook(hooks, "after_model_request")
        original = _response("Sunny")
        assert await post(MagicMock(), _request_context(), original) is original


# ---------------------------------------------------------------------------
# Bypass when harness is uninitialized
# ---------------------------------------------------------------------------


class TestModelBypassWhenUninitialized:
    @pytest.mark.asyncio
    async def test_pre_model_bypass_when_agent_none(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.agent = None
        hooks = _govern(pydantic_agent, mock_harness, agent_card)
        pre = _hook(hooks, "before_model_request")
        ctx = _request_context()
        result = await pre(MagicMock(), ctx)
        assert result is ctx
        mock_harness.adjudicate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_post_model_bypass_when_trajectory_id_none(
        self,
        pydantic_agent: PydanticAgent,
        mock_harness: MagicMock,
        agent_card: Agent,
    ):
        mock_harness.trajectory_id = None
        hooks = _govern(pydantic_agent, mock_harness, agent_card)
        post = _hook(hooks, "after_model_request")
        resp = _response("Sunny")
        result = await post(MagicMock(), _request_context(), resp)
        assert result is resp
        mock_harness.adjudicate.assert_not_awaited()
