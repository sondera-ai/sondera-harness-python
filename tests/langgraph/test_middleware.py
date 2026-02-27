"""Tests for SonderaHarnessMiddleware."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime
from langgraph.types import Command

from sondera.harness import Harness
from sondera.langgraph.middleware import (
    SonderaHarnessMiddleware,
    State,
    Strategy,
    _extract_last_user_message,
    _message_to_text,
)
from sondera.types import Adjudication, Agent, Decision


@pytest.fixture
def mock_harness() -> MagicMock:
    """Create a mock harness for testing."""
    harness = MagicMock(spec=Harness)
    harness.adjudicate = AsyncMock(
        return_value=Adjudication(decision=Decision.ALLOW, reason="Allowed")
    )
    harness.finalize = AsyncMock()

    # Make initialize set the trajectory_id when called
    async def mock_initialize(*args, **kwargs):
        harness.trajectory_id = "test-trajectory-123"
        harness._trajectory_id = "test-trajectory-123"

    harness.initialize = AsyncMock(side_effect=mock_initialize)
    harness.resume = AsyncMock()
    harness._trajectory_id = "test-trajectory-123"
    harness.trajectory_id = "test-trajectory-123"
    return harness


@pytest.fixture
def test_agent() -> Agent:
    """Create a test agent."""
    return Agent(
        id="test-middleware-agent",
        provider_id="langchain",
        name="Test Middleware Agent",
        description="Agent used for middleware testing",
        instruction="Respond concisely",
        tools=[],
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
        mock_middleware._harness.adjudicate.return_value = Adjudication(
            decision=Decision.ALLOW, reason="Allowed"
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
        mock_middleware._harness.adjudicate.return_value = Adjudication(
            decision=Decision.DENY, reason="Blocked by policy"
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
        mock_harness.adjudicate.return_value = Adjudication(
            decision=Decision.DENY, reason="Please rephrase your request"
        )

        state = {"messages": [HumanMessage(content="Bad content")]}
        result = await middleware.abefore_agent(state, Runtime())

        assert result is not None
        assert "messages" in result
        # STEER should NOT jump to end - it allows continuation with modified content
        assert "jump_to" not in result
        # STEER now replaces with AIMessage containing policy violation info
        assert isinstance(result["messages"][0], AIMessage)
        assert (
            "Policy violation in user message: Please rephrase your request"
            in result["messages"][0].content
        )

    @pytest.mark.asyncio
    async def test_awrap_model_call_allows_on_allow_decision(
        self, mock_middleware: SonderaHarnessMiddleware
    ):
        """Test that awrap_model_call allows execution when adjudication allows."""
        mock_middleware._harness.adjudicate.return_value = Adjudication(
            decision=Decision.ALLOW, reason="Allowed"
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
        mock_middleware._harness.adjudicate.return_value = Adjudication(
            decision=Decision.DENY, reason="Pre-model blocked"
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
        mock_middleware._harness.adjudicate.return_value = Adjudication(
            decision=Decision.ALLOW, reason="Allowed"
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
        mock_middleware._harness.adjudicate.return_value = Adjudication(
            decision=Decision.DENY, reason="Tool not allowed"
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
            Adjudication(decision=Decision.DENY, reason="Tool concern"),
            Adjudication(decision=Decision.ALLOW, reason="Allowed"),
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
        assert (
            result.content
            == "Tool execution modified due to policy concern: Tool concern"
        )
        # Verify only pre-tool adjudication was called (tool execution was blocked)
        assert mock_harness.adjudicate.call_count == 1

    @pytest.mark.asyncio
    async def test_awrap_tool_call_post_tool_block_returns_command(
        self, mock_middleware: SonderaHarnessMiddleware
    ):
        """Test that awrap_tool_call returns Command on post-tool deny with BLOCK strategy."""
        # First call (pre-tool) allows, second call (post-tool) denies
        mock_middleware._harness.adjudicate.side_effect = [
            Adjudication(decision=Decision.ALLOW, reason="Pre-tool allowed"),
            Adjudication(decision=Decision.DENY, reason="Post-tool blocked"),
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
        mock_middleware._harness.adjudicate.return_value = Adjudication(
            decision=Decision.ALLOW, reason="Allowed"
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
        mock_middleware._harness.adjudicate.return_value = Adjudication(
            decision=Decision.ALLOW, reason="Allowed"
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
        mock_middleware._harness.adjudicate.return_value = Adjudication(
            decision=Decision.ALLOW, reason="Allowed"
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
