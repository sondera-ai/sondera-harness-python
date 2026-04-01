"""Tests for SonderaHarnessMiddleware."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime
from langgraph.types import Command

from sondera import (
    Adjudicated,
    Agent,
    Decision,
    GuardrailResults,
    Mode,
    SignatureGuardrailMatch,
    SignatureGuardrailResult,
    Steering,
)
from sondera.harness import Harness
from sondera.langgraph.middleware import (
    SonderaHarnessMiddleware,
    State,
    Strategy,
    _deny_reason,
    _extract_last_user_message,
    _log_guardrails,
    _message_to_text,
)


@pytest.fixture
def mock_harness() -> MagicMock:
    """Create a mock harness for testing."""
    harness = MagicMock(spec=Harness)
    harness.adjudicate = AsyncMock(
        return_value=Adjudicated(Decision.Allow, reason="Allowed")
    )
    harness.finalize = AsyncMock()
    harness.fail = AsyncMock()

    # Make initialize set the trajectory_id when called
    async def mock_initialize(*args, **kwargs):
        harness.trajectory_id = "test-trajectory-123"
        harness._trajectory_id = "test-trajectory-123"

    harness.initialize = AsyncMock(side_effect=mock_initialize)
    harness.resume = AsyncMock()
    harness._trajectory_id = "test-trajectory-123"
    harness.trajectory_id = "test-trajectory-123"
    harness.agent = Agent(
        id="test-middleware-agent",
        provider="langchain",
    )
    return harness


@pytest.fixture
def test_agent() -> Agent:
    """Create a test agent."""
    return Agent(
        id="test-middleware-agent",
        provider="langchain",
    )


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_extract_last_user_message_from_human_message(self):
        """Test extracting HumanMessage from state."""
        state = {"messages": [HumanMessage(content="Hello")]}
        result = _extract_last_user_message(state)
        assert isinstance(result, HumanMessage)
        assert result.content == "Hello"

    def test_extract_last_user_message_from_dict(self):
        """Test extracting user message from dict format."""
        state = {"messages": [{"role": "user", "content": "Hello from dict"}]}
        result = _extract_last_user_message(state)
        assert isinstance(result, HumanMessage)
        assert result.content == "Hello from dict"

    def test_extract_last_user_message_empty_state(self):
        """Test extracting from empty state."""
        state = {"messages": []}
        result = _extract_last_user_message(state)
        assert result is None

    def test_extract_last_user_message_no_messages_key(self):
        """Test extracting when messages key is missing."""
        state = {}
        result = _extract_last_user_message(state)
        assert result is None

    def test_message_to_text_string_content(self):
        """Test converting message with string content."""
        message = HumanMessage(content="Hello world")
        result = _message_to_text(message)
        assert result == "Hello world"

    def test_message_to_text_list_content(self):
        """Test converting message with list content."""
        message = HumanMessage(content=["Hello", "world"])
        result = _message_to_text(message)
        assert result == "Hello world"


class TestSonderaHarnessMiddlewareInit:
    """Tests for middleware initialization."""

    def test_init_with_block_strategy(self, mock_harness: MagicMock, test_agent: Agent):
        """Test initialization with BLOCK strategy."""
        middleware = SonderaHarnessMiddleware(
            harness=mock_harness,
            strategy=Strategy.BLOCK,
        )
        assert middleware._strategy == Strategy.BLOCK
        assert middleware._harness is mock_harness

    def test_init_with_steer_strategy(self, mock_harness: MagicMock, test_agent: Agent):
        """Test initialization with STEER strategy."""
        middleware = SonderaHarnessMiddleware(
            harness=mock_harness,
            strategy=Strategy.STEER,
        )
        assert middleware._strategy == Strategy.STEER
        assert middleware._harness is mock_harness

    def test_init_default_strategy(self, mock_harness: MagicMock, test_agent: Agent):
        """Test that default strategy is BLOCK."""
        middleware = SonderaHarnessMiddleware(
            harness=mock_harness,
        )
        assert middleware._strategy == Strategy.BLOCK

    def test_init_without_agent(self, mock_harness: MagicMock):
        """Test initialization works with just harness."""
        middleware = SonderaHarnessMiddleware(
            harness=mock_harness,
        )
        assert middleware._harness is mock_harness
        assert middleware._strategy == Strategy.BLOCK


class TestSonderaHarnessMiddlewareHooks:
    """Tests for middleware hooks using mocked Harness."""

    @pytest.fixture
    def mock_middleware(
        self, mock_harness: MagicMock, test_agent: Agent
    ) -> SonderaHarnessMiddleware:
        """Create a middleware with mocked Harness methods."""
        middleware = SonderaHarnessMiddleware(
            harness=mock_harness,
            strategy=Strategy.BLOCK,
        )
        return middleware

    @pytest.mark.asyncio
    async def test_abefore_agent_allows_on_allow_decision(
        self, mock_middleware: SonderaHarnessMiddleware
    ):
        """Test that abefore_agent allows execution when adjudication allows."""
        # Reset trajectory_id to None to simulate uninitialized state
        mock_middleware._harness.trajectory_id = None
        mock_middleware._harness.adjudicate.return_value = Adjudicated(
            Decision.Allow, reason="Allowed"
        )

        state = {"messages": [HumanMessage(content="Hello")]}
        result = await mock_middleware.abefore_agent(state, Runtime())

        # Should return trajectory_id and session_id from initialization
        assert result is not None
        assert result["trajectory_id"] == "test-trajectory-123"
        assert result["session_id"].startswith("session-")
        mock_middleware._harness.initialize.assert_called_once()
        mock_middleware._harness.adjudicate.assert_called_once()

    @pytest.mark.asyncio
    async def test_abefore_agent_jumps_to_end_on_deny_with_block_strategy(
        self, mock_middleware: SonderaHarnessMiddleware
    ):
        """Test that abefore_agent jumps to end when adjudication denies with BLOCK strategy."""
        mock_middleware._harness.adjudicate.return_value = Adjudicated(
            Decision.Deny, mode=Mode.Govern, reason="Blocked by policy"
        )

        state = {"messages": [HumanMessage(content="Bad content")]}
        result = await mock_middleware.abefore_agent(state, Runtime())

        assert result is not None
        assert "messages" in result
        assert "jump_to" in result
        assert result["jump_to"] == "end"
        assert isinstance(result["messages"][0], AIMessage)
        assert "Blocked by policy" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_abefore_agent_steers_on_deny_with_steer_strategy(
        self, mock_harness: MagicMock, test_agent: Agent
    ):
        """Test that abefore_agent returns steering response when adjudication denies with STEER strategy."""
        middleware = SonderaHarnessMiddleware(
            harness=mock_harness,
            strategy=Strategy.STEER,
        )
        mock_harness.adjudicate.return_value = Adjudicated(
            Decision.Deny, mode=Mode.Govern, reason="Please rephrase your request"
        )

        state = {"messages": [HumanMessage(content="Bad content")]}
        result = await middleware.abefore_agent(state, Runtime())

        assert result is not None
        assert "messages" in result
        # STEER should NOT jump to end - it allows continuation with modified content
        assert "jump_to" not in result
        # STEER now replaces with AIMessage containing policy violation info
        assert isinstance(result["messages"][0], AIMessage)
        assert "Please rephrase your request" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_awrap_model_call_allows_on_allow_decision(
        self, mock_middleware: SonderaHarnessMiddleware
    ):
        """Test that awrap_model_call allows execution when adjudication allows."""
        mock_middleware._harness.adjudicate.return_value = Adjudicated(
            Decision.Allow, reason="Allowed"
        )

        request = ModelRequest(
            model=FakeListChatModel(responses=["ok"]),
            system_prompt=None,
            messages=[HumanMessage(content="Hi")],
            tool_choice=None,
            tools=[],
            response_format=None,
            state={"messages": [HumanMessage(content="Hi")]},
            runtime=Runtime(),
            model_settings={},
        )

        async def handler(req: ModelRequest) -> ModelResponse:
            return ModelResponse(result=[AIMessage(content="Model response")])

        result = await mock_middleware.awrap_model_call(request, handler)

        assert isinstance(result, ModelResponse)
        assert len(result.result) == 1
        assert result.result[0].content == "Model response"

    @pytest.mark.asyncio
    async def test_awrap_model_call_returns_policy_message_on_pre_model_deny(
        self, mock_middleware: SonderaHarnessMiddleware
    ):
        """Test that awrap_model_call returns policy message on pre-model deny."""
        mock_middleware._harness.adjudicate.return_value = Adjudicated(
            Decision.Deny, mode=Mode.Govern, reason="Pre-model blocked"
        )

        request = ModelRequest(
            model=FakeListChatModel(responses=["ok"]),
            system_prompt=None,
            messages=[HumanMessage(content="Hi")],
            tool_choice=None,
            tools=[],
            response_format=None,
            state={"messages": [HumanMessage(content="Hi")]},
            runtime=Runtime(),
            model_settings={},
        )

        async def handler(req: ModelRequest) -> ModelResponse:
            return ModelResponse(result=[AIMessage(content="Should not reach")])

        result = await mock_middleware.awrap_model_call(request, handler)

        assert isinstance(result, ModelResponse)
        assert len(result.result) == 1
        assert isinstance(result.result[0], AIMessage)
        assert "Pre-model blocked" in result.result[0].content

    @pytest.mark.asyncio
    async def test_awrap_tool_call_allows_on_allow_decision(
        self, mock_middleware: SonderaHarnessMiddleware
    ):
        """Test that awrap_tool_call allows execution when adjudication allows."""
        mock_middleware._harness.adjudicate.return_value = Adjudicated(
            Decision.Allow, reason="Allowed"
        )

        tool_request = ToolCallRequest(
            tool_call={"name": "test_tool", "args": {"param": "value"}, "id": "tool-1"},
            tool=None,
            state={"messages": []},
            runtime=Runtime(),
        )

        async def handler(req: ToolCallRequest) -> ToolMessage:
            return ToolMessage(
                content="Tool result",
                tool_call_id=req.tool_call["id"],
                name=req.tool_call["name"],
            )

        result = await mock_middleware.awrap_tool_call(tool_request, handler)

        assert isinstance(result, ToolMessage)
        assert result.content == "Tool result"

    @pytest.mark.asyncio
    async def test_awrap_tool_call_returns_blocked_message_on_pre_tool_deny(
        self, mock_middleware: SonderaHarnessMiddleware
    ):
        """Test that awrap_tool_call returns blocked message on pre-tool deny."""
        mock_middleware._harness.adjudicate.return_value = Adjudicated(
            Decision.Deny, mode=Mode.Govern, reason="Tool not allowed"
        )

        tool_request = ToolCallRequest(
            tool_call={"name": "dangerous_tool", "args": {}, "id": "tool-1"},
            tool=None,
            state={"messages": []},
            runtime=Runtime(),
        )

        async def handler(req: ToolCallRequest) -> ToolMessage:
            return ToolMessage(
                content="Should not reach", tool_call_id="tool-1", name="dangerous_tool"
            )

        result = await mock_middleware.awrap_tool_call(tool_request, handler)

        # BLOCK strategy now returns Command object to jump to end
        assert isinstance(result, Command)
        assert result.goto == "__end__"
        assert "messages" in result.update
        tool_message = result.update["messages"][0]
        assert isinstance(tool_message, ToolMessage)
        assert "Tool execution was blocked" in tool_message.content
        assert "Tool not allowed" in tool_message.content
        assert tool_message.name == "dangerous_tool"

    @pytest.mark.asyncio
    async def test_awrap_tool_call_steers_on_deny_with_steer_strategy(
        self, mock_harness: MagicMock, test_agent: Agent
    ):
        """Test that awrap_tool_call allows execution with STEER strategy despite pre-tool deny."""
        middleware = SonderaHarnessMiddleware(
            harness=mock_harness,
            strategy=Strategy.STEER,
        )
        # First call (pre-tool) denies, second call (post-tool) allows
        mock_harness.adjudicate.side_effect = [
            Adjudicated(Decision.Deny, mode=Mode.Govern, reason="Tool concern"),
            Adjudicated(Decision.Allow, reason="Allowed"),
        ]

        tool_request = ToolCallRequest(
            tool_call={"name": "risky_tool", "args": {}, "id": "tool-1"},
            tool=None,
            state={"messages": []},
            runtime=Runtime(),
        )

        async def handler(req: ToolCallRequest) -> ToolMessage:
            return ToolMessage(
                content="Tool executed successfully",
                tool_call_id="tool-1",
                name="risky_tool",
            )

        result = await middleware.awrap_tool_call(tool_request, handler)

        # STEER now returns modified tool message instead of executing the tool
        assert isinstance(result, ToolMessage)
        assert "Tool concern" in result.content
        # Verify only pre-tool adjudication was called (tool execution was blocked)
        assert mock_harness.adjudicate.call_count == 1

    @pytest.mark.asyncio
    async def test_awrap_tool_call_post_tool_block_returns_command(
        self, mock_middleware: SonderaHarnessMiddleware
    ):
        """Test that awrap_tool_call returns Command on post-tool deny with BLOCK strategy."""
        # First call (pre-tool) allows, second call (post-tool) denies
        mock_middleware._harness.adjudicate.side_effect = [
            Adjudicated(Decision.Allow, reason="Pre-tool allowed"),
            Adjudicated(Decision.Deny, mode=Mode.Govern, reason="Post-tool blocked"),
        ]

        tool_request = ToolCallRequest(
            tool_call={"name": "test_tool", "args": {}, "id": "tool-1"},
            tool=None,
            state={"messages": []},
            runtime=Runtime(),
        )

        async def handler(req: ToolCallRequest) -> ToolMessage:
            return ToolMessage(
                content="Tool executed", tool_call_id="tool-1", name="test_tool"
            )

        result = await mock_middleware.awrap_tool_call(tool_request, handler)

        # BLOCK strategy on post-tool should return Command
        assert isinstance(result, Command)
        assert result.goto == "__end__"
        tool_message = result.update["messages"][0]
        assert "Tool result was blocked" in tool_message.content
        assert mock_middleware._harness.adjudicate.call_count == 2

    @pytest.mark.asyncio
    async def test_aafter_agent_finalizes_trajectory(
        self, mock_middleware: SonderaHarnessMiddleware
    ):
        """Test that aafter_agent finalizes the trajectory and preserves session_id."""
        mock_middleware._harness.adjudicate.return_value = Adjudicated(
            Decision.Allow, reason="Allowed"
        )

        state = {
            "messages": [AIMessage(content="Final response")],
            "session_id": "session-abc",
        }
        result = await mock_middleware.aafter_agent(state, Runtime())

        # Should return both trajectory_id and session_id
        assert result == {
            "trajectory_id": "test-trajectory-123",
            "session_id": "session-abc",
        }
        mock_middleware._harness.finalize.assert_called_once()

    @pytest.mark.asyncio
    async def test_aafter_agent_handles_no_final_message(
        self, mock_middleware: SonderaHarnessMiddleware
    ):
        """Test that aafter_agent handles case with no final message gracefully."""
        mock_middleware._harness.adjudicate.return_value = Adjudicated(
            Decision.Allow, reason="Allowed"
        )

        state = {"messages": []}  # No messages
        result = await mock_middleware.aafter_agent(state, Runtime())

        # Should return trajectory_id to preserve for next conversation
        assert result == {"trajectory_id": "test-trajectory-123"}
        # Should still finalize even if no final message
        mock_middleware._harness.finalize.assert_called_once()
        # Should not adjudicate if no final message
        mock_middleware._harness.adjudicate.assert_not_called()

    @pytest.mark.asyncio
    async def test_abefore_agent_reuses_session_id_across_turns(
        self, mock_middleware: SonderaHarnessMiddleware
    ):
        """Test that abefore_agent reuses session_id from state on subsequent turns."""
        mock_middleware._harness.adjudicate.return_value = Adjudicated(
            Decision.Allow, reason="Allowed"
        )

        state = {
            "messages": [HumanMessage(content="Hello")],
            "session_id": "session-existing-789",
        }
        result = await mock_middleware.abefore_agent(state, Runtime())

        # Should initialize a new per-turn trajectory (not resume)
        mock_middleware._harness.initialize.assert_called_once()
        _, kwargs = mock_middleware._harness.initialize.call_args
        assert kwargs["session_id"] == "session-existing-789"
        mock_middleware._harness.resume.assert_not_called()
        mock_middleware._harness.adjudicate.assert_called_once()
        # Should return same session_id and new trajectory_id
        assert result is not None
        assert result["session_id"] == "session-existing-789"
        assert result["trajectory_id"] == "test-trajectory-123"


class TestStateClass:
    """Tests for State class with trajectory_id and session_id support."""

    def test_state_has_trajectory_id_field(self):
        """Test that State class supports trajectory_id field."""
        state = State(messages=[], trajectory_id="test-123")
        assert state["trajectory_id"] == "test-123"
        assert "messages" in state

    def test_state_has_session_id_field(self):
        """Test that State class supports session_id field."""
        state = State(messages=[], session_id="session-abc")
        assert state["session_id"] == "session-abc"

    def test_state_fields_are_optional(self):
        """Test that trajectory_id and session_id are optional in State."""
        state = State(messages=[])
        assert "messages" in state
        assert state.get("trajectory_id") is None
        assert state.get("session_id") is None


class TestStrategyEnum:
    """Tests for Strategy enum."""

    def test_strategy_values(self):
        """Test Strategy enum values."""
        assert Strategy.BLOCK.value == "block"
        assert Strategy.STEER.value == "steer"

    def test_strategy_is_string_enum(self):
        """Test that Strategy is a string enum."""
        assert isinstance(Strategy.BLOCK, str)
        assert Strategy.BLOCK == "block"


class TestNonGoverningModePassthrough:
    """Tests that non-Govern mode denies are treated as observe-only."""

    @pytest.fixture
    def mock_middleware(self, mock_harness: MagicMock) -> SonderaHarnessMiddleware:
        return SonderaHarnessMiddleware(harness=mock_harness, strategy=Strategy.BLOCK)

    @pytest.mark.asyncio
    async def test_abefore_agent_monitor_deny_allows_through(
        self, mock_middleware: SonderaHarnessMiddleware
    ):
        """abefore_agent with Monitor-mode deny should not block."""
        mock_middleware._harness.adjudicate.return_value = Adjudicated(
            Decision.Deny, mode=Mode.Monitor, reason="Observed violation"
        )
        state = {"messages": [HumanMessage(content="Bad content")]}
        result = await mock_middleware.abefore_agent(state, Runtime())

        # No jump_to — execution continues
        assert result is not None
        assert "jump_to" not in result
        assert "messages" not in result

    @pytest.mark.asyncio
    async def test_abefore_agent_steer_mode_deny_allows_through(
        self, mock_middleware: SonderaHarnessMiddleware
    ):
        """abefore_agent with Steer-mode deny should not block."""
        mock_middleware._harness.adjudicate.return_value = Adjudicated(
            Decision.Deny, mode=Mode.Steer, reason="Steering suggestion"
        )
        state = {"messages": [HumanMessage(content="Questionable content")]}
        result = await mock_middleware.abefore_agent(state, Runtime())

        assert result is not None
        assert "jump_to" not in result

    @pytest.mark.asyncio
    async def test_awrap_model_call_monitor_deny_allows_through(
        self, mock_middleware: SonderaHarnessMiddleware
    ):
        """awrap_model_call with Monitor-mode pre-model deny should call the model normally."""
        mock_middleware._harness.adjudicate.return_value = Adjudicated(
            Decision.Deny, mode=Mode.Monitor, reason="Observed"
        )
        handler_called = False

        request = ModelRequest(
            model=None,
            system_prompt=None,
            messages=[HumanMessage(content="Hi")],
            tool_choice=None,
            tools=[],
            response_format=None,
            state={},
            runtime=Runtime(),
            model_settings={},
        )

        async def handler(req: ModelRequest) -> ModelResponse:
            nonlocal handler_called
            handler_called = True
            return ModelResponse(result=[AIMessage(content="Real response")])

        result = await mock_middleware.awrap_model_call(request, handler)

        # Model should still be called
        assert handler_called
        assert result.result[0].content == "Real response"

    @pytest.mark.asyncio
    async def test_awrap_tool_call_monitor_deny_executes_tool(
        self, mock_middleware: SonderaHarnessMiddleware
    ):
        """awrap_tool_call with Monitor-mode pre-tool deny should execute the tool."""
        mock_middleware._harness.adjudicate.return_value = Adjudicated(
            Decision.Deny, mode=Mode.Monitor, reason="Observed"
        )
        tool_request = ToolCallRequest(
            tool_call={"name": "my_tool", "args": {}, "id": "tc-1"},
            tool=None,
            state={},
            runtime=Runtime(),
        )
        handler_called = False

        async def handler(req: ToolCallRequest) -> ToolMessage:
            nonlocal handler_called
            handler_called = True
            return ToolMessage(
                content="Tool output", tool_call_id="tc-1", name="my_tool"
            )

        result = await mock_middleware.awrap_tool_call(tool_request, handler)

        # Tool should still execute
        assert handler_called
        assert isinstance(result, ToolMessage)
        assert result.content == "Tool output"

    @pytest.mark.asyncio
    async def test_awrap_tool_call_monitor_post_tool_deny_returns_original(
        self, mock_harness: MagicMock
    ):
        """Post-tool Monitor-mode deny should return the original (unmodified) tool result."""
        middleware = SonderaHarnessMiddleware(
            harness=mock_harness, strategy=Strategy.BLOCK
        )
        mock_harness.adjudicate.side_effect = [
            Adjudicated(Decision.Allow, reason="Pre-tool OK"),
            Adjudicated(Decision.Deny, mode=Mode.Monitor, reason="Post-tool observed"),
        ]
        tool_request = ToolCallRequest(
            tool_call={"name": "my_tool", "args": {}, "id": "tc-1"},
            tool=None,
            state={},
            runtime=Runtime(),
        )

        async def handler(req: ToolCallRequest) -> ToolMessage:
            return ToolMessage(
                content="Sensitive output", tool_call_id="tc-1", name="my_tool"
            )

        result = await middleware.awrap_tool_call(tool_request, handler)

        # Monitor mode: original result passes through unchanged
        assert isinstance(result, ToolMessage)
        assert result.content == "Sensitive output"


class TestDenyReasonHelper:
    """Tests for _deny_reason helper."""

    def test_returns_steering_explanation_when_present(self):
        """Steering explanation takes priority over reason."""
        adjudicated = Adjudicated(
            Decision.Deny,
            reason="Policy violation",
            steering=Steering(explanation="Please rephrase"),
        )

        result = _deny_reason(adjudicated, "default")
        assert result == "Please rephrase"

    def test_falls_back_to_deny_message_when_no_steering(self):
        """Falls back to deny_message when steering is absent."""
        adjudicated = Adjudicated(Decision.Deny, reason="Policy violation")

        result = _deny_reason(adjudicated, "default fallback")
        assert "Policy violation" in result or result == "default fallback"

    def test_falls_back_when_steering_has_no_explanation(self):
        """Falls back when steering exists but explanation is empty."""
        adjudicated = Adjudicated(
            Decision.Deny,
            reason="Policy violation",
            steering=Steering(explanation=""),
        )

        result = _deny_reason(adjudicated, "default fallback")
        # Empty string is falsy — should fall back to deny_message
        assert result != ""


class TestLogGuardrailsHelper:
    """Tests for _log_guardrails helper."""

    def test_no_log_when_guardrails_absent(self):
        """No warning logged when adjudicated has no guardrails."""
        import logging

        log = MagicMock(spec=logging.Logger)
        adjudicated = Adjudicated(Decision.Allow, reason="OK")

        _log_guardrails(log, adjudicated, "traj-1")
        log.warning.assert_not_called()

    def test_no_log_when_signature_not_triggered(self):
        """No warning logged when signature guardrail did not fire."""
        import logging

        log = MagicMock(spec=logging.Logger)
        adjudicated = Adjudicated(
            Decision.Allow,
            reason="OK",
            guardrails=GuardrailResults(
                signature=SignatureGuardrailResult(triggered=False),
            ),
        )

        _log_guardrails(log, adjudicated, "traj-1")
        log.warning.assert_not_called()

    def test_warning_logged_when_signature_triggered(self):
        """WARNING is emitted when at least one YARA rule fires."""
        import logging

        log = MagicMock(spec=logging.Logger)
        adjudicated = Adjudicated(
            Decision.Deny,
            reason="YARA hit",
            guardrails=GuardrailResults(
                signature=SignatureGuardrailResult(
                    triggered=True,
                    severity="HIGH",
                    categories=["pii"],
                    matches=[SignatureGuardrailMatch("detect_pii")],
                ),
            ),
        )

        _log_guardrails(log, adjudicated, "traj-42")

        log.warning.assert_called_once()
        call_args = log.warning.call_args
        assert "traj-42" in str(call_args)
        assert "HIGH" in str(call_args) or "severity" in str(call_args[0])


class TestMiddlewareSessionId:
    """Tests for session_id propagation in SonderaHarnessMiddleware."""

    @pytest.mark.asyncio
    async def test_constructor_session_id_used_as_fallback(
        self, mock_harness: MagicMock
    ):
        """Verify constructor session_id is used when state has no session_id."""
        mw = SonderaHarnessMiddleware(harness=mock_harness, session_id="sess-ctor")
        state = State(messages=[HumanMessage(content="hello")])
        runtime = MagicMock()

        await mw.abefore_agent(state, runtime)
        mock_harness.initialize.assert_awaited_once_with(session_id="sess-ctor")

    @pytest.mark.asyncio
    async def test_state_session_id_takes_precedence(self, mock_harness: MagicMock):
        """Verify state session_id overrides constructor session_id."""
        mw = SonderaHarnessMiddleware(harness=mock_harness, session_id="sess-ctor")
        state = State(messages=[HumanMessage(content="hello")], session_id="sess-state")
        runtime = MagicMock()

        await mw.abefore_agent(state, runtime)
        mock_harness.initialize.assert_awaited_once_with(session_id="sess-state")

    @pytest.mark.asyncio
    async def test_auto_generated_session_id_not_persisted(
        self, mock_harness: MagicMock
    ):
        """Verify auto-generated session_id is NOT reused across turns.

        When no constructor session_id is provided, each turn gets a fresh
        auto-generated ID to avoid cross-conversation bleed when a single
        middleware instance serves multiple chats.
        """
        mw = SonderaHarnessMiddleware(harness=mock_harness)
        runtime = MagicMock()

        # First turn: no session_id anywhere — auto-generates
        state1 = State(messages=[HumanMessage(content="turn 1")])
        result1 = await mw.abefore_agent(state1, runtime)
        first_session_id = result1["session_id"]
        assert first_session_id.startswith("session-")

        mock_harness.initialize.reset_mock()

        # Second turn: no session_id — gets a different auto-generated ID
        state2 = State(messages=[HumanMessage(content="turn 2")])
        result2 = await mw.abefore_agent(state2, runtime)
        assert result2["session_id"].startswith("session-")
        assert result2["session_id"] != first_session_id

    @pytest.mark.asyncio
    async def test_constructor_session_id_persisted_across_turns(
        self, mock_harness: MagicMock
    ):
        """Verify constructor session_id IS reused across turns."""
        mw = SonderaHarnessMiddleware(harness=mock_harness, session_id="sess-shared")
        runtime = MagicMock()

        state1 = State(messages=[HumanMessage(content="turn 1")])
        result1 = await mw.abefore_agent(state1, runtime)
        assert result1["session_id"] == "sess-shared"

        mock_harness.initialize.reset_mock()

        state2 = State(messages=[HumanMessage(content="turn 2")])
        result2 = await mw.abefore_agent(state2, runtime)
        assert result2["session_id"] == "sess-shared"
