"""Unit tests for SonderaHarnessHook.

Note: These tests require the 'strands' optional dependency.
Install with: uv pip install -e ".[strands]"
"""

import inspect
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

# Skip this module if strands is not installed
pytest.importorskip("strands", reason="strands package not installed")

from strands.hooks import HookRegistry
from strands.hooks.events import (
    AfterInvocationEvent,
    AfterModelCallEvent,
    AfterToolCallEvent,
    BeforeInvocationEvent,
    BeforeModelCallEvent,
    BeforeToolCallEvent,
)

from sondera.harness import Harness
from sondera.strands import SonderaHarnessHook
from sondera.types import Adjudication, Decision


@pytest.fixture
def mock_harness() -> MagicMock:
    """Create a mock harness for testing."""
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


class TestSonderaStrandsHarnessRegistration:
    """Test hook registration and basic functionality."""

    def test_harness_initialization(self, mock_harness: MagicMock):
        """Test SonderaHarnessHook can be initialized with dependency injection."""
        hook = SonderaHarnessHook(harness=mock_harness)

        assert hook is not None
        assert hook._harness is mock_harness
        assert hook._strands_agent is None

    def test_hook_registration(self, mock_harness: MagicMock):
        """Test that all 6 hooks are registered."""
        hook = SonderaHarnessHook(harness=mock_harness)

        # Create mock registry
        registry = Mock(spec=HookRegistry)

        # Register hooks
        hook.register_hooks(registry)

        # Verify all 6 hooks were registered
        assert registry.add_callback.call_count == 6

        # Verify specific hooks
        calls = registry.add_callback.call_args_list
        event_types = [call[0][0] for call in calls]

        assert BeforeInvocationEvent in event_types
        assert AfterInvocationEvent in event_types
        assert BeforeModelCallEvent in event_types
        assert AfterModelCallEvent in event_types
        assert BeforeToolCallEvent in event_types
        assert AfterToolCallEvent in event_types

    def test_hook_callbacks_exist(self, mock_harness: MagicMock):
        """Test that all callback methods exist and are async."""
        hook = SonderaHarnessHook(harness=mock_harness)

        # Check async callback methods exist (used by Strands)
        callback_methods = [
            "_on_before_invocation",
            "_on_after_invocation",
            "_on_before_model_call",
            "_on_after_model_call",
            "_on_before_tool_call",
            "_on_after_tool_call",
        ]

        for method_name in callback_methods:
            assert hasattr(hook, method_name)
            method = getattr(hook, method_name)
            # Check they're callable
            assert callable(method)
            # Check they're async (Strands supports async callbacks)
            assert inspect.iscoroutinefunction(method)


class TestSonderaStrandsHarnessHooks:
    """Test individual hook callbacks."""

    @pytest.mark.asyncio
    async def test_before_invocation_initializes_trajectory(
        self, mock_harness: MagicMock
    ):
        """Test that _on_before_invocation initializes the harness."""
        hook = SonderaHarnessHook(harness=mock_harness)

        # Create mock event
        mock_agent = Mock()
        mock_agent.name = "test-agent"
        mock_agent.system_prompt = "You are a helpful assistant"
        mock_agent.description = "A test agent"
        mock_agent.tools = []
        event = BeforeInvocationEvent(agent=mock_agent)

        # Call async method directly
        await hook._on_before_invocation(event)

        # Verify harness was initialized
        mock_harness.initialize.assert_called_once()
        assert hook._strands_agent is mock_agent

    @pytest.mark.asyncio
    async def test_after_invocation_finalizes_trajectory(self, mock_harness: MagicMock):
        """Test that _on_after_invocation finalizes the trajectory."""
        hook = SonderaHarnessHook(harness=mock_harness)

        # Create mock event
        mock_agent = Mock()
        mock_agent.name = "test-agent"
        event = AfterInvocationEvent(agent=mock_agent)

        # Call async method directly
        await hook._on_after_invocation(event)

        # Verify harness was finalized
        mock_harness.finalize.assert_called_once()

    @pytest.mark.asyncio
    async def test_before_model_call_adjudicates(self, mock_harness: MagicMock):
        """Test that _on_before_model_call calls adjudicate."""
        hook = SonderaHarnessHook(harness=mock_harness)

        # Create mock event with conversation manager
        mock_agent = Mock()
        mock_agent.name = "test-agent"
        mock_conversation_manager = Mock()
        mock_conversation_manager.messages = [{"role": "user", "content": "Hello"}]
        mock_agent.conversation_manager = mock_conversation_manager
        event = BeforeModelCallEvent(agent=mock_agent)

        # Call async method directly
        await hook._on_before_model_call(event)

        # Verify adjudication was called
        mock_harness.adjudicate.assert_called_once()

    @pytest.mark.asyncio
    async def test_before_tool_call_adjudicates(self, mock_harness: MagicMock):
        """Test that _on_before_tool_call calls adjudicate."""
        hook = SonderaHarnessHook(harness=mock_harness)

        # Create mock event
        mock_tool = Mock()
        mock_tool.name = "test-tool"

        mock_tool_use = {"name": "test_tool", "input": {"arg": "value"}}

        event = BeforeToolCallEvent(
            agent=Mock(),
            selected_tool=mock_tool,
            tool_use=mock_tool_use,
            invocation_state={},
        )

        # Call async method directly
        await hook._on_before_tool_call(event)

        # Verify adjudication was called
        mock_harness.adjudicate.assert_called_once()

    @pytest.mark.asyncio
    async def test_before_tool_call_blocks_on_deny(self, mock_harness: MagicMock):
        """Test that tool call is blocked when adjudication denies."""
        mock_harness.adjudicate.return_value = Adjudication(
            decision=Decision.DENY, reason="Tool not allowed"
        )
        hook = SonderaHarnessHook(harness=mock_harness)

        # Create mock event
        mock_tool_use = {"name": "dangerous_tool", "input": {}}

        event = BeforeToolCallEvent(
            agent=Mock(),
            selected_tool=Mock(),
            tool_use=mock_tool_use,
            invocation_state={},
        )

        # Call async method directly
        await hook._on_before_tool_call(event)

        # Verify tool was cancelled
        assert event.cancel_tool is not None
        assert "Tool not allowed" in event.cancel_tool

    def test_extract_text_from_before_model_call_event(self, mock_harness: MagicMock):
        """Test text extraction from BeforeModelCallEvent."""
        hook = SonderaHarnessHook(harness=mock_harness)

        # Create mock event with conversation manager
        mock_agent = Mock()
        mock_agent.name = "test-agent"
        mock_conversation_manager = Mock()

        # Mock messages
        mock_conversation_manager.messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        mock_agent.conversation_manager = mock_conversation_manager

        event = BeforeModelCallEvent(agent=mock_agent)

        # Extract text
        text = hook._extract_text_from_event(event)

        # Should extract conversation
        assert isinstance(text, str)
        assert "user: Hello" in text
        assert "assistant: Hi there" in text

    def test_extract_text_from_after_model_call_event(self, mock_harness: MagicMock):
        """Test text extraction from AfterModelCallEvent."""
        hook = SonderaHarnessHook(harness=mock_harness)

        # Create mock event with stop response
        mock_message = {"content": "Hello, how can I help?"}

        mock_stop_response = Mock()
        mock_stop_response.message = mock_message

        event = AfterModelCallEvent(
            agent=Mock(), stop_response=mock_stop_response, exception=None
        )

        # Extract text
        text = hook._extract_text_from_event(event)

        assert isinstance(text, str)
        assert "Hello, how can I help?" in text


class TestSonderaStrandsHarnessHelperMethods:
    """Test helper methods."""

    def test_extract_text_from_event_fallback(self, mock_harness: MagicMock):
        """Test text extraction fallback for unknown event types."""
        hook = SonderaHarnessHook(harness=mock_harness)

        # Create unknown event type
        unknown_event = Mock()

        # Should return empty string for unknown events
        text = hook._extract_text_from_event(unknown_event)
        assert text == ""

    def test_custom_logger_injection(self, mock_harness: MagicMock):
        """Test that custom logger can be injected."""
        import logging

        custom_logger = logging.getLogger("custom_test_logger")

        hook = SonderaHarnessHook(
            harness=mock_harness,
            logger_instance=custom_logger,
        )

        assert hook._log is custom_logger


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
