"""Tests for SonderaGraph wrapper."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from sondera import (
    Adjudicated,
    Agent,
    Decision,
    Event,
    Mode,
    Prompt,
    Thought,
)
from sondera.harness import Harness
from sondera.langgraph.exceptions import GuardrailViolationError
from sondera.langgraph.graph import SonderaGraph


@pytest.fixture
def mock_harness() -> MagicMock:
    """Create a mock harness for testing."""
    harness = MagicMock(spec=Harness)
    harness.adjudicate = AsyncMock(
        return_value=Adjudicated(Decision.Allow, reason="Allowed")
    )
    harness.finalize = AsyncMock()
    harness.fail = AsyncMock()
    harness.initialize = AsyncMock()
    harness.agent = Agent(
        id="test-agent",
        provider="langgraph",
    )
    harness.trajectory_id = "test-trajectory-123"
    return harness


@pytest.fixture
def mock_compiled_graph() -> MagicMock:
    """Create a mock compiled graph."""
    graph = MagicMock()
    graph.name = "test-graph"
    graph.input_schema = {"type": "object"}
    graph.output_schema = {"type": "object"}
    return graph


class TestSonderaGraphInit:
    """Tests for SonderaGraph initialization and properties."""

    def test_init(self, mock_compiled_graph: MagicMock, mock_harness: MagicMock):
        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        assert sg._graph is mock_compiled_graph
        assert sg._harness is mock_harness
        assert sg._track_nodes is True
        assert sg._enforce is True

    def test_init_custom_options(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        sg = SonderaGraph(
            mock_compiled_graph,
            harness=mock_harness,
            track_nodes=False,
            enforce=False,
        )
        assert sg._track_nodes is False
        assert sg._enforce is False

    def test_name_property(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        assert sg.name == "test-graph"

    def test_input_schema_property(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        assert sg.input_schema == {"type": "object"}

    def test_output_schema_property(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        assert sg.output_schema == {"type": "object"}


class TestAinvoke:
    """Tests for SonderaGraph.ainvoke."""

    @pytest.mark.asyncio
    async def test_ainvoke_basic_flow(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """Verify harness lifecycle (initialize/adjudicate/finalize) and correct final state."""
        final_state = {"messages": [AIMessage(content="Done")], "count": 3}

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            # Yield updates mode chunks
            yield ("updates", {"node_a": {"count": 1}})
            yield ("updates", {"node_b": {"count": 2}})
            # Yield values mode chunks — last one is the final state
            yield ("values", {"messages": [], "count": 0})
            yield ("values", final_state)

        mock_compiled_graph.astream = mock_astream

        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        result = await sg.ainvoke({"messages": [], "count": 0})

        assert result == final_state
        mock_harness.initialize.assert_awaited_once()
        mock_harness.finalize.assert_awaited_once()
        # Two node executions + final message recording = 3 adjudicate calls
        assert mock_harness.adjudicate.await_count == 3

    @pytest.mark.asyncio
    async def test_ainvoke_track_nodes_disabled(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """Verify delegation to ainvoke when track_nodes=False."""
        expected = {"result": "value"}
        mock_compiled_graph.ainvoke = AsyncMock(return_value=expected)

        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness, track_nodes=False)
        result = await sg.ainvoke({"input": "data"})

        assert result == expected
        mock_compiled_graph.ainvoke.assert_awaited_once()
        mock_harness.initialize.assert_awaited_once()
        mock_harness.finalize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ainvoke_state_accumulation(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """Confirm final state comes from values stream, not naive dict merge."""
        # Simulate reducer-based state where messages accumulate via reducer
        correct_final = {
            "messages": [
                HumanMessage(content="Hi"),
                AIMessage(content="Hello"),
                AIMessage(content="Goodbye"),
            ]
        }

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            # Updates would give partial node outputs
            yield ("updates", {"greet": {"messages": [AIMessage(content="Hello")]}})
            yield (
                "updates",
                {"farewell": {"messages": [AIMessage(content="Goodbye")]}},
            )
            # Values gives the correctly reduced state
            yield ("values", correct_final)

        mock_compiled_graph.astream = mock_astream

        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        result = await sg.ainvoke({"messages": [HumanMessage(content="Hi")]})

        # The result must be the values-stream state, NOT a naive merge
        assert result == correct_final
        assert len(result["messages"]) == 3

    @pytest.mark.asyncio
    async def test_ainvoke_deny_enforcement(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """Mock DENY adjudication, verify GuardrailViolationError."""
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(
                Decision.Deny, mode=Mode.Govern, reason="Blocked by policy"
            )
        )

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            yield ("updates", {"bad_node": {"data": "sensitive"}})
            yield ("values", {"data": "sensitive"})

        mock_compiled_graph.astream = mock_astream

        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        with pytest.raises(GuardrailViolationError) as exc_info:
            await sg.ainvoke({"data": "input"})

        assert "Blocked by policy" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_ainvoke_deny_no_enforcement(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """DENY with enforce=False should not raise."""
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(
                Decision.Deny, mode=Mode.Govern, reason="Blocked by policy"
            )
        )

        final = {"data": "result"}

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            yield ("updates", {"node": {"data": "result"}})
            yield ("values", final)

        mock_compiled_graph.astream = mock_astream

        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness, enforce=False)
        result = await sg.ainvoke({"data": "input"})
        assert result == final

    @pytest.mark.asyncio
    async def test_initial_message_recording(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """Verify user Prompt event recorded for HumanMessage input."""

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            yield ("values", {"messages": []})

        mock_compiled_graph.astream = mock_astream

        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        await sg.ainvoke({"messages": [HumanMessage(content="Hello")]})

        # First adjudicate call should be a Prompt.user event
        first_call = mock_harness.adjudicate.call_args_list[0]
        event = first_call.args[0]
        assert isinstance(event, Event)
        assert isinstance(event.event, Prompt)
        assert event.event.content == "Hello"

    @pytest.mark.asyncio
    async def test_final_message_recording(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """Verify Thought event recorded for AIMessage output."""
        final_state = {"messages": [AIMessage(content="Final answer")]}

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            yield ("values", final_state)

        mock_compiled_graph.astream = mock_astream

        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        await sg.ainvoke({"data": "input"})

        last_call = mock_harness.adjudicate.call_args_list[-1]
        event = last_call.args[0]
        assert isinstance(event, Event)
        assert isinstance(event.event, Thought)
        assert event.event.thought == "Final answer"

    @pytest.mark.asyncio
    async def test_ainvoke_forwards_kwargs(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """Verify context, output_keys, interrupt_before, interrupt_after are forwarded."""
        calls = []

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            calls.append(kwargs)
            yield ("values", {})

        mock_compiled_graph.astream = mock_astream

        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        await sg.ainvoke(
            {},
            context={"user_id": "123"},
            output_keys=["result"],
            interrupt_before=["review"],
            interrupt_after=["done"],
        )

        assert calls[0]["context"] == {"user_id": "123"}
        assert calls[0]["output_keys"] == ["result"]
        assert calls[0]["interrupt_before"] == ["review"]
        assert calls[0]["interrupt_after"] == ["done"]


class TestAstream:
    """Tests for SonderaGraph.astream."""

    @pytest.mark.asyncio
    async def test_astream_delegation(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """Verify chunks yielded from underlying graph."""
        chunks = [{"node_a": {"x": 1}}, {"node_b": {"x": 2}}]

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            for c in chunks:
                yield c

        mock_compiled_graph.astream = mock_astream

        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        collected = []
        async for chunk in sg.astream({"input": "data"}, stream_mode="values"):
            collected.append(chunk)

        assert collected == chunks
        mock_harness.initialize.assert_awaited_once()
        mock_harness.finalize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_astream_tracks_updates(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """Verify node tracking when stream_mode includes updates."""

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            yield {"node_a": {"x": 1}}
            yield {"node_b": {"x": 2}}

        mock_compiled_graph.astream = mock_astream

        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        collected = []
        async for chunk in sg.astream({"input": "data"}, stream_mode="updates"):
            collected.append(chunk)

        assert len(collected) == 2
        # Two node executions recorded
        assert mock_harness.adjudicate.await_count == 2

    @pytest.mark.asyncio
    async def test_astream_multi_mode_tracks_updates(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """Verify node tracking in multi-mode streaming."""

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            yield ("updates", {"node_a": {"x": 1}})
            yield ("values", {"x": 1})

        mock_compiled_graph.astream = mock_astream

        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        collected = []
        async for chunk in sg.astream(
            {"input": "data"}, stream_mode=["updates", "values"]
        ):
            collected.append(chunk)

        assert len(collected) == 2
        # One node execution recorded from updates
        assert mock_harness.adjudicate.await_count == 1


class TestDelegationMethods:
    """Verify delegation methods call through to underlying graph."""

    def test_get_state(self, mock_compiled_graph: MagicMock, mock_harness: MagicMock):
        mock_compiled_graph.get_state.return_value = {"state": "data"}
        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        result = sg.get_state({"configurable": {"thread_id": "1"}})
        assert result == {"state": "data"}
        mock_compiled_graph.get_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_aget_state(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        mock_compiled_graph.aget_state = AsyncMock(return_value={"state": "data"})
        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        result = await sg.aget_state({"configurable": {"thread_id": "1"}})
        assert result == {"state": "data"}

    def test_update_state(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        sg.update_state({"configurable": {"thread_id": "1"}}, {"key": "val"})
        mock_compiled_graph.update_state.assert_called_once_with(
            {"configurable": {"thread_id": "1"}}, {"key": "val"}
        )

    @pytest.mark.asyncio
    async def test_aupdate_state(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        mock_compiled_graph.aupdate_state = AsyncMock()
        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        await sg.aupdate_state({"configurable": {"thread_id": "1"}}, {"key": "val"})
        mock_compiled_graph.aupdate_state.assert_awaited_once()

    def test_get_graph(self, mock_compiled_graph: MagicMock, mock_harness: MagicMock):
        mock_compiled_graph.get_graph.return_value = "graph-repr"
        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        result = sg.get_graph()
        assert result == "graph-repr"

    @pytest.mark.asyncio
    async def test_aget_graph(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        mock_compiled_graph.aget_graph = AsyncMock(return_value="graph-repr")
        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        result = await sg.aget_graph()
        assert result == "graph-repr"

    def test_get_state_history(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        mock_compiled_graph.get_state_history.return_value = ["s1", "s2"]
        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        result = sg.get_state_history({"configurable": {"thread_id": "1"}})
        assert result == ["s1", "s2"]

    @pytest.mark.asyncio
    async def test_aget_state_history(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        mock_compiled_graph.aget_state_history = AsyncMock(return_value=["s1", "s2"])
        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        result = await sg.aget_state_history({"configurable": {"thread_id": "1"}})
        assert result == ["s1", "s2"]


class TestFailPath:
    """Tests that unhandled exceptions mark the trajectory as failed."""

    @pytest.mark.asyncio
    async def test_ainvoke_unexpected_exception_calls_fail(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """An unexpected exception during ainvoke should call harness.fail(), not finalize."""

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            yield ("updates", {"node": {"data": "x"}})
            raise RuntimeError("unexpected boom")

        mock_compiled_graph.astream = mock_astream
        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)

        with pytest.raises(RuntimeError, match="unexpected boom"):
            await sg.ainvoke({"data": "input"})

        mock_harness.fail.assert_awaited_once()
        call_kwargs = mock_harness.fail.call_args.kwargs
        assert "unexpected boom" in call_kwargs["reason"]
        mock_harness.finalize.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ainvoke_guardrail_violation_calls_finalize_not_fail(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """A GuardrailViolationError should call finalize (not fail) and re-raise."""
        mock_harness.adjudicate = AsyncMock(
            return_value=Adjudicated(Decision.Deny, mode=Mode.Govern, reason="Blocked")
        )

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            yield ("updates", {"node": {"data": "sensitive"}})
            yield ("values", {"data": "sensitive"})

        mock_compiled_graph.astream = mock_astream
        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)

        from sondera.langgraph.exceptions import GuardrailViolationError

        with pytest.raises(GuardrailViolationError):
            await sg.ainvoke({"data": "input"})

        mock_harness.finalize.assert_awaited_once()
        mock_harness.fail.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_astream_unexpected_exception_calls_fail(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """An unexpected exception during astream should call harness.fail()."""

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            yield {"node": {"x": 1}}
            raise ValueError("stream error")

        mock_compiled_graph.astream = mock_astream
        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)

        with pytest.raises(ValueError, match="stream error"):
            async for _ in sg.astream({"data": "input"}, stream_mode="updates"):
                pass

        mock_harness.fail.assert_awaited_once()
        call_kwargs = mock_harness.fail.call_args.kwargs
        assert "stream error" in call_kwargs["reason"]
        mock_harness.finalize.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_astream_no_trajectory_id_skips_fail(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """If trajectory_id is None when exception occurs, fail() should not be called."""
        mock_harness.trajectory_id = None

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            # yield is required to make this an async generator (not a coroutine)
            raise RuntimeError("crash before any trajectory")
            yield  # noqa: F401 — unreachable, but makes this an async generator

        mock_compiled_graph.astream = mock_astream
        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)

        with pytest.raises(RuntimeError):
            async for _ in sg.astream({}):
                pass

        mock_harness.fail.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_astream_generator_exit_calls_finalize(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """Abandoning the astream iterator early should finalize the trajectory."""

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            yield {"a": 1}
            yield {"b": 2}
            yield {"c": 3}

        mock_compiled_graph.astream = mock_astream
        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)

        # Explicitly close the iterator via aclose() to trigger GeneratorExit.
        # Using ``async for … break`` doesn't reliably await the cleanup
        # coroutine in all asyncio/pytest-asyncio environments.
        ait = sg.astream({})
        chunk = await ait.__anext__()
        assert chunk == {"a": 1}
        await ait.aclose()

        mock_harness.finalize.assert_awaited_once()
        mock_harness.fail.assert_not_awaited()


class TestInvoke:
    """Tests for synchronous invoke wrapper."""

    def test_invoke_wraps_ainvoke(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """Verify sync invoke calls ainvoke via asyncio.run."""

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            yield ("values", {"result": "ok"})

        mock_compiled_graph.astream = mock_astream

        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        result = sg.invoke({"input": "data"})
        assert result == {"result": "ok"}
        mock_harness.initialize.assert_awaited_once()
        mock_harness.finalize.assert_awaited_once()


class TestSessionId:
    """Tests for session_id propagation in SonderaGraph."""

    @pytest.mark.asyncio
    async def test_ainvoke_passes_session_id(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """Verify session_id is forwarded to harness.initialize."""

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            yield ("values", {"result": "ok"})

        mock_compiled_graph.astream = mock_astream

        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        await sg.ainvoke({"input": "data"}, session_id="sess-abc")
        mock_harness.initialize.assert_awaited_once_with(
            agent=mock_harness.agent, session_id="sess-abc"
        )

    @pytest.mark.asyncio
    async def test_constructor_session_id_used_as_default(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """Verify constructor session_id is used when per-call session_id is not provided."""

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            yield ("values", {"result": "ok"})

        mock_compiled_graph.astream = mock_astream

        sg = SonderaGraph(
            mock_compiled_graph, harness=mock_harness, session_id="sess-default"
        )
        await sg.ainvoke({"input": "data"})
        mock_harness.initialize.assert_awaited_once_with(
            agent=mock_harness.agent, session_id="sess-default"
        )

    @pytest.mark.asyncio
    async def test_per_call_session_id_overrides_constructor(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """Verify per-call session_id takes precedence over constructor."""

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            yield ("values", {"result": "ok"})

        mock_compiled_graph.astream = mock_astream

        sg = SonderaGraph(
            mock_compiled_graph, harness=mock_harness, session_id="sess-default"
        )
        await sg.ainvoke({"input": "data"}, session_id="sess-override")
        mock_harness.initialize.assert_awaited_once_with(
            agent=mock_harness.agent, session_id="sess-override"
        )

    @pytest.mark.asyncio
    async def test_astream_passes_session_id(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """Verify session_id is forwarded through astream."""

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            yield {"result": "ok"}

        mock_compiled_graph.astream = mock_astream

        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        chunks = []
        async for chunk in sg.astream({"input": "data"}, session_id="sess-stream"):
            chunks.append(chunk)
        mock_harness.initialize.assert_awaited_once_with(
            agent=mock_harness.agent, session_id="sess-stream"
        )

    @pytest.mark.asyncio
    async def test_no_session_id_passes_none(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """Verify None is passed when no session_id is provided anywhere."""

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            yield ("values", {"result": "ok"})

        mock_compiled_graph.astream = mock_astream

        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        await sg.ainvoke({"input": "data"})
        mock_harness.initialize.assert_awaited_once_with(
            agent=mock_harness.agent, session_id=None
        )
