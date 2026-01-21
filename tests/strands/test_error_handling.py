"""Unit tests for SonderaHarnessHook error handling.

Tests verify the error handling behavior in async hook callbacks.

Note: These tests require the 'strands' optional dependency.
Install with: uv pip install -e ".[strands]"
"""

import inspect
import logging
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

# Skip this module if strands is not installed
pytest.importorskip("strands", reason="strands package not installed")

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


class TestAsyncCallbackErrorHandling:
    """Test error handling in async hook callbacks."""

    @pytest.mark.asyncio
    async def test_async_callback_handles_exceptions(
        self, mock_harness: MagicMock, caplog
    ):
        """Test that async callbacks handle exceptions gracefully."""
        # Configure harness to raise an exception
        mock_harness.initialize.side_effect = RuntimeError("Async method failed")

        hook = SonderaHarnessHook(harness=mock_harness)

        # Create mock event
        mock_agent = Mock()
        mock_agent.name = "test-agent"
        mock_agent.system_prompt = "You are helpful"
        mock_agent.tools = []
        event = BeforeInvocationEvent(agent=mock_agent)

        # Should not raise exception, should log error
        with caplog.at_level(logging.ERROR):
            await hook._on_before_invocation(event)

        # Verify error was logged
        assert "Error in before_invocation" in caplog.text

    @pytest.mark.asyncio
    async def test_all_async_callbacks_have_error_handling(
        self, mock_harness: MagicMock, caplog
    ):
        """Test that all async callback methods handle exceptions."""
        # Configure harness methods to raise exceptions
        mock_harness.initialize.side_effect = RuntimeError("Test error")
        mock_harness.finalize.side_effect = RuntimeError("Test error")
        mock_harness.adjudicate.side_effect = RuntimeError("Test error")

        hook = SonderaHarnessHook(harness=mock_harness)

        # Create properly configured mock agents
        mock_agent = Mock()
        mock_agent.name = "test-agent"
        mock_agent.system_prompt = "You are helpful"
        mock_agent.description = "A test agent"
        mock_agent.tools = []

        # Create mock stop_response for after_model_call to have content
        mock_stop_response = Mock()
        mock_stop_response.message = {"content": "Hello, how can I help?"}

        test_cases = [
            (
                "_on_before_invocation",
                BeforeInvocationEvent(agent=mock_agent),
                "before_invocation",
            ),
            (
                "_on_after_invocation",
                AfterInvocationEvent(agent=mock_agent),
                "after_invocation",
            ),
            (
                "_on_before_model_call",
                BeforeModelCallEvent(agent=mock_agent),
                "before_model_call",
            ),
            (
                "_on_after_model_call",
                AfterModelCallEvent(
                    agent=mock_agent, stop_response=mock_stop_response, exception=None
                ),
                "after_model_call",
            ),
        ]

        for method_name, event, expected_log in test_cases:
            with caplog.at_level(logging.ERROR):
                method = getattr(hook, method_name)
                await method(event)

            # Verify error was logged for this specific method
            assert f"Error in {expected_log}" in caplog.text
            caplog.clear()

    @pytest.mark.asyncio
    async def test_tool_call_async_callbacks_handle_errors(
        self, mock_harness: MagicMock, caplog
    ):
        """Test that tool call async callbacks handle exceptions."""
        # Configure harness to raise exception
        mock_harness.adjudicate.side_effect = RuntimeError("Tool error")

        hook = SonderaHarnessHook(harness=mock_harness)

        # Test before tool call
        before_event = BeforeToolCallEvent(
            agent=Mock(),
            selected_tool=Mock(),
            tool_use={"name": "test_tool", "input": {}},
            invocation_state={},
        )

        with caplog.at_level(logging.ERROR):
            await hook._on_before_tool_call(before_event)

        assert "Error in before_tool_call" in caplog.text

        # Test after tool call
        after_event = AfterToolCallEvent(
            agent=Mock(),
            selected_tool=Mock(),
            tool_use={"name": "test_tool"},
            invocation_state={},
            result="test result",
            exception=None,
            cancel_message=None,
        )

        caplog.clear()
        with caplog.at_level(logging.ERROR):
            await hook._on_after_tool_call(after_event)

        assert "Error in after_tool_call" in caplog.text

    def test_async_method_signatures(self, mock_harness: MagicMock):
        """Test that callback methods are async and have correct signatures."""
        hook = SonderaHarnessHook(harness=mock_harness)

        # All callback methods should be async and accept event parameter
        async_methods = [
            "_on_before_invocation",
            "_on_after_invocation",
            "_on_before_model_call",
            "_on_after_model_call",
            "_on_before_tool_call",
            "_on_after_tool_call",
        ]

        for method_name in async_methods:
            method = getattr(hook, method_name)
            sig = inspect.signature(method)

            # Should have 'event' parameter
            assert "event" in sig.parameters
            # Should be coroutine (async)
            assert inspect.iscoroutinefunction(method)

    @pytest.mark.asyncio
    async def test_successful_async_execution_no_errors(
        self, mock_harness: MagicMock, caplog
    ):
        """Test that successful async execution doesn't produce errors."""
        hook = SonderaHarnessHook(harness=mock_harness)

        # Create mock event with all required attributes
        mock_agent = Mock()
        mock_agent.name = "test-agent"
        mock_agent.system_prompt = "You are helpful"
        mock_agent.description = "A test agent"
        mock_agent.tools = []
        event = BeforeInvocationEvent(agent=mock_agent)

        # Should complete without errors
        with caplog.at_level(logging.ERROR):
            await hook._on_before_invocation(event)

        # Verify no error logs
        assert "Error" not in caplog.text

        # Verify harness was called
        mock_harness.initialize.assert_called_once()


class TestHarnessConnectionErrorHandling:
    """Test error handling for harness connection issues."""

    def test_initialization_with_harness(self, mock_harness: MagicMock):
        """Test that hook initializes correctly with harness."""
        hook = SonderaHarnessHook(harness=mock_harness)

        assert hook._harness is mock_harness

    def test_initialization_with_custom_logger(self, mock_harness: MagicMock):
        """Test initialization with custom logger."""
        custom_logger = logging.getLogger("test_logger")

        hook = SonderaHarnessHook(
            harness=mock_harness,
            logger_instance=custom_logger,
        )

        assert hook._log is custom_logger


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
