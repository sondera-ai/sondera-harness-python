"""Unit tests for SonderaHarnessPlugin (ADK integration).

Note: These tests require the 'adk' optional dependency.
Install with: uv pip install -e ".[adk]"
"""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("google.adk", reason="google-adk package not installed")

from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types as genai_types

from sondera.adk.plugin import SonderaHarnessPlugin, _extract_text
from sondera.harness import Harness
from sondera.types import Adjudication, Decision, PromptContent

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_harness() -> MagicMock:
    """Create a mock harness that defaults to ALLOW."""
    harness = MagicMock(spec=Harness)
    harness.adjudicate = AsyncMock(
        return_value=Adjudication(decision=Decision.ALLOW, reason="Allowed")
    )
    harness.finalize = AsyncMock()
    harness.initialize = AsyncMock()
    harness.resume = AsyncMock()
    harness._trajectory_id = "test-trajectory-123"
    harness.trajectory_id = "test-trajectory-123"
    return harness


@pytest.fixture
def plugin(mock_harness: MagicMock) -> SonderaHarnessPlugin:
    return SonderaHarnessPlugin(harness=mock_harness)


@pytest.fixture
def invocation_context() -> MagicMock:
    ctx = MagicMock(spec=InvocationContext)
    agent = MagicMock(spec=LlmAgent)
    agent.name = "test-agent"
    agent.description = "A test agent"
    agent.instruction = "Be helpful"
    agent.tools = []
    ctx.agent = agent
    ctx.app_name = "test-app"
    # Mock session with an id for session_id propagation
    session = MagicMock()
    session.id = "test-session-123"
    ctx.session = session
    return ctx


@pytest.fixture
def callback_context() -> MagicMock:
    return MagicMock(spec=CallbackContext)


# ---------------------------------------------------------------------------
# _extract_text helper
# ---------------------------------------------------------------------------


class TestExtractText:
    def test_none_content(self):
        assert _extract_text(None) == ""

    def test_none_parts(self):
        content = genai_types.Content(role="user", parts=None)
        assert _extract_text(content) == ""

    def test_single_text_part(self):
        content = genai_types.Content(
            role="user", parts=[genai_types.Part.from_text(text="hello")]
        )
        assert _extract_text(content) == "hello"

    def test_multiple_text_parts(self):
        content = genai_types.Content(
            role="user",
            parts=[
                genai_types.Part.from_text(text="hello"),
                genai_types.Part.from_text(text="world"),
            ],
        )
        assert _extract_text(content) == "hello\nworld"

    def test_empty_parts(self):
        content = genai_types.Content(role="user", parts=[])
        assert _extract_text(content) == ""


# ---------------------------------------------------------------------------
# on_user_message_callback
# ---------------------------------------------------------------------------


class TestOnUserMessageCallback:
    @pytest.mark.asyncio
    async def test_allow(self, plugin, invocation_context, mock_harness):
        message = genai_types.Content(
            role="user", parts=[genai_types.Part.from_text(text="Hello")]
        )
        result = await plugin.on_user_message_callback(
            invocation_context=invocation_context, user_message=message
        )
        assert result is None
        mock_harness.initialize.assert_awaited_once()
        mock_harness.adjudicate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_session_id_propagated(
        self, plugin, invocation_context, mock_harness
    ):
        """Verify session_id from invocation_context.session is passed to initialize."""
        message = genai_types.Content(
            role="user", parts=[genai_types.Part.from_text(text="Hello")]
        )
        await plugin.on_user_message_callback(
            invocation_context=invocation_context, user_message=message
        )
        # Check initialize was called with session_id from the mock session
        _, kwargs = mock_harness.initialize.call_args
        assert kwargs["session_id"] == "test-session-123"

    @pytest.mark.asyncio
    async def test_no_session_passes_none(self, plugin, mock_harness):
        """When invocation_context.session is None, session_id should be None."""
        ctx = MagicMock(spec=InvocationContext)
        agent = MagicMock(spec=LlmAgent)
        agent.name = "test-agent"
        agent.description = "A test agent"
        agent.instruction = "Be helpful"
        agent.tools = []
        ctx.agent = agent
        ctx.app_name = "test-app"
        ctx.session = None

        message = genai_types.Content(
            role="user", parts=[genai_types.Part.from_text(text="Hello")]
        )
        await plugin.on_user_message_callback(
            invocation_context=ctx, user_message=message
        )
        _, kwargs = mock_harness.initialize.call_args
        assert kwargs["session_id"] is None

    @pytest.mark.asyncio
    async def test_deny(self, plugin, invocation_context, mock_harness):
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudication(decision=Decision.DENY, reason="Blocked")
        )
        message = genai_types.Content(
            role="user", parts=[genai_types.Part.from_text(text="bad input")]
        )
        result = await plugin.on_user_message_callback(
            invocation_context=invocation_context, user_message=message
        )
        assert result is not None
        assert result.parts[0].text == "Blocked"

    @pytest.mark.asyncio
    async def test_escalate_logs_warning(
        self, plugin, invocation_context, mock_harness, caplog
    ):
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudication(decision=Decision.ESCALATE, reason="Needs review")
        )
        message = genai_types.Content(
            role="user", parts=[genai_types.Part.from_text(text="borderline")]
        )
        with caplog.at_level(logging.WARNING):
            result = await plugin.on_user_message_callback(
                invocation_context=invocation_context, user_message=message
            )
        assert result is None  # ESCALATE does not block
        assert "ESCALATE" in caplog.text
        assert "Needs review" in caplog.text

    @pytest.mark.asyncio
    async def test_multipart_content(self, plugin, invocation_context, mock_harness):
        message = genai_types.Content(
            role="user",
            parts=[
                genai_types.Part.from_text(text="part one"),
                genai_types.Part.from_text(text="part two"),
            ],
        )
        await plugin.on_user_message_callback(
            invocation_context=invocation_context, user_message=message
        )
        # Verify the adjudicated content includes both parts
        call_args = mock_harness.adjudicate.call_args
        content = call_args[0][2]  # third positional arg
        assert isinstance(content, PromptContent)
        assert "part one" in content.text
        assert "part two" in content.text

    @pytest.mark.asyncio
    async def test_empty_message_skips_adjudication(
        self, plugin, invocation_context, mock_harness
    ):
        message = genai_types.Content(role="user", parts=[])
        result = await plugin.on_user_message_callback(
            invocation_context=invocation_context, user_message=message
        )
        assert result is None
        # initialize is called, but adjudicate should not be
        mock_harness.initialize.assert_awaited_once()
        mock_harness.adjudicate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_same_session_reuses_trajectory(
        self, plugin, invocation_context, mock_harness
    ):
        """Second message in the same session should reuse the active trajectory."""
        msg1 = genai_types.Content(
            role="user", parts=[genai_types.Part.from_text(text="first")]
        )
        msg2 = genai_types.Content(
            role="user", parts=[genai_types.Part.from_text(text="second")]
        )

        # First message initializes
        await plugin.on_user_message_callback(
            invocation_context=invocation_context, user_message=msg1
        )
        mock_harness.initialize.assert_awaited_once()

        # Second message in the same session should NOT call initialize or resume
        await plugin.on_user_message_callback(
            invocation_context=invocation_context, user_message=msg2
        )
        mock_harness.initialize.assert_awaited_once()  # still just once
        mock_harness.resume.assert_not_awaited()
        # But adjudicate should have been called for both messages
        assert mock_harness.adjudicate.await_count == 2


# ---------------------------------------------------------------------------
# before_model_callback
# ---------------------------------------------------------------------------


class TestBeforeModelCallback:
    @pytest.mark.asyncio
    async def test_extracts_user_content(self, plugin, callback_context, mock_harness):
        request = LlmRequest(
            contents=[
                genai_types.Content(
                    role="user",
                    parts=[genai_types.Part.from_text(text="What is my balance?")],
                ),
            ]
        )
        result = await plugin.before_model_callback(
            callback_context=callback_context, llm_request=request
        )
        assert result is None
        call_args = mock_harness.adjudicate.call_args
        content = call_args[0][2]
        assert isinstance(content, PromptContent)
        assert content.text == "What is my balance?"

    @pytest.mark.asyncio
    async def test_extracts_last_user_content(
        self, plugin, callback_context, mock_harness
    ):
        """When multiple user messages exist, extract the most recent one."""
        request = LlmRequest(
            contents=[
                genai_types.Content(
                    role="user",
                    parts=[genai_types.Part.from_text(text="first message")],
                ),
                genai_types.Content(
                    role="model",
                    parts=[genai_types.Part.from_text(text="response")],
                ),
                genai_types.Content(
                    role="user",
                    parts=[genai_types.Part.from_text(text="second message")],
                ),
            ]
        )
        await plugin.before_model_callback(
            callback_context=callback_context, llm_request=request
        )
        call_args = mock_harness.adjudicate.call_args
        content = call_args[0][2]
        assert content.text == "second message"

    @pytest.mark.asyncio
    async def test_empty_contents_sends_empty_string(
        self, plugin, callback_context, mock_harness
    ):
        request = LlmRequest(contents=[])
        await plugin.before_model_callback(
            callback_context=callback_context, llm_request=request
        )
        call_args = mock_harness.adjudicate.call_args
        content = call_args[0][2]
        assert content.text == ""

    @pytest.mark.asyncio
    async def test_deny(self, plugin, callback_context, mock_harness):
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudication(
                decision=Decision.DENY, reason="Model call blocked"
            )
        )
        request = LlmRequest(contents=[])
        result = await plugin.before_model_callback(
            callback_context=callback_context, llm_request=request
        )
        assert result is not None
        assert isinstance(result, LlmResponse)
        assert result.content.parts[0].text == "Model call blocked"


# ---------------------------------------------------------------------------
# after_model_callback
# ---------------------------------------------------------------------------


class TestAfterModelCallback:
    @pytest.mark.asyncio
    async def test_allow(self, plugin, callback_context, mock_harness):
        response = LlmResponse(
            content=genai_types.Content(
                parts=[genai_types.Part.from_text(text="Here is your balance")]
            )
        )
        result = await plugin.after_model_callback(
            callback_context=callback_context, llm_response=response
        )
        assert result is None
        mock_harness.adjudicate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deny(self, plugin, callback_context, mock_harness):
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudication(decision=Decision.DENY, reason="Response blocked")
        )
        response = LlmResponse(
            content=genai_types.Content(
                parts=[genai_types.Part.from_text(text="sensitive data")]
            )
        )
        result = await plugin.after_model_callback(
            callback_context=callback_context, llm_response=response
        )
        assert result is not None
        assert result.content.parts[0].text == "Response blocked"

    @pytest.mark.asyncio
    async def test_no_content_skips(self, plugin, callback_context, mock_harness):
        response = LlmResponse(content=None)
        result = await plugin.after_model_callback(
            callback_context=callback_context, llm_response=response
        )
        assert result is None
        mock_harness.adjudicate.assert_not_awaited()


# ---------------------------------------------------------------------------
# before_tool_callback / after_tool_callback
# ---------------------------------------------------------------------------


class TestToolCallbacks:
    @pytest.fixture
    def mock_tool(self) -> MagicMock:
        tool = MagicMock(spec=BaseTool)
        tool.name = "get_portfolio"
        return tool

    @pytest.fixture
    def tool_context(self) -> MagicMock:
        return MagicMock(spec=ToolContext)

    @pytest.mark.asyncio
    async def test_before_tool_allow(
        self, plugin, mock_tool, tool_context, mock_harness
    ):
        result = await plugin.before_tool_callback(
            tool=mock_tool,
            tool_args={"customer_id": "CUST001"},
            tool_context=tool_context,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_before_tool_deny(
        self, plugin, mock_tool, tool_context, mock_harness
    ):
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudication(
                decision=Decision.DENY, reason="Tool not permitted"
            )
        )
        result = await plugin.before_tool_callback(
            tool=mock_tool,
            tool_args={"customer_id": "CUST001"},
            tool_context=tool_context,
        )
        assert result is not None
        assert "Tool blocked" in result["error"]

    @pytest.mark.asyncio
    async def test_after_tool_allow(
        self, plugin, mock_tool, tool_context, mock_harness
    ):
        result = await plugin.after_tool_callback(
            tool=mock_tool,
            tool_args={"customer_id": "CUST001"},
            tool_context=tool_context,
            result={"total_value": 50000},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_after_tool_deny(self, plugin, mock_tool, tool_context, mock_harness):
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudication(
                decision=Decision.DENY, reason="Result contains PII"
            )
        )
        result = await plugin.after_tool_callback(
            tool=mock_tool,
            tool_args={"customer_id": "CUST001"},
            tool_context=tool_context,
            result={"ssn": "123-45-6789"},
        )
        assert result is not None
        assert "Tool result blocked" in result["error"]

    @pytest.mark.asyncio
    async def test_before_tool_escalate(
        self, plugin, mock_tool, tool_context, mock_harness, caplog
    ):
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudication(
                decision=Decision.ESCALATE, reason="Needs approval"
            )
        )
        with caplog.at_level(logging.WARNING):
            result = await plugin.before_tool_callback(
                tool=mock_tool,
                tool_args={"customer_id": "CUST001"},
                tool_context=tool_context,
            )
        assert result is None  # ESCALATE does not block
        assert "ESCALATE" in caplog.text


# ---------------------------------------------------------------------------
# after_run_callback
# ---------------------------------------------------------------------------


class TestAfterRunCallback:
    @pytest.mark.asyncio
    async def test_does_not_finalize(self, plugin, invocation_context, mock_harness):
        """after_run_callback defers finalization to close()."""
        await plugin.after_run_callback(invocation_context=invocation_context)
        mock_harness.finalize.assert_not_awaited()


class TestClose:
    @pytest.mark.asyncio
    async def test_finalizes_active_trajectory(self, plugin, mock_harness):
        mock_harness.trajectory_id = "traj-123"
        await plugin.close()
        mock_harness.finalize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_finalize_without_trajectory(self, plugin, mock_harness):
        mock_harness.trajectory_id = None
        await plugin.close()
        mock_harness.finalize.assert_not_awaited()
