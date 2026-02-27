"""Tests for SonderaGraph wrapper."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from sondera.harness import Harness
from sondera.langgraph.exceptions import GuardrailViolationError
from sondera.langgraph.graph import SonderaGraph
from sondera.types import Adjudication, Agent, Decision


@pytest.fixture
def mock_harness() -> MagicMock:
    """Create a mock harness for testing."""
    harness = MagicMock(spec=Harness)
    harness.adjudicate = AsyncMock(
        return_value=Adjudication(decision=Decision.ALLOW, reason="Allowed")
    )
    harness.finalize = AsyncMock()
    harness.initialize = AsyncMock()
    harness.agent = Agent(
        id="test-agent",
        provider_id="langgraph",
        name="Test Agent",
        description="Agent for graph testing",
        instruction="Be helpful",
        tools=[],
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
            return_value=Adjudication(
                decision=Decision.DENY, reason="Blocked by policy"
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
            return_value=Adjudication(
                decision=Decision.DENY, reason="Blocked by policy"
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
        """Verify PRE_MODEL step recorded for HumanMessage input."""

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            yield ("values", {"messages": []})

        mock_compiled_graph.astream = mock_astream

        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        await sg.ainvoke({"messages": [HumanMessage(content="Hello")]})

        # First adjudicate call should be for the user input (PRE_MODEL)
        from sondera.types import Role, Stage

        first_call = mock_harness.adjudicate.call_args_list[0]
        assert first_call.kwargs["stage"] == Stage.PRE_MODEL
        assert first_call.kwargs["role"] == Role.USER

    @pytest.mark.asyncio
    async def test_final_message_recording(
        self, mock_compiled_graph: MagicMock, mock_harness: MagicMock
    ):
        """Verify POST_MODEL step recorded for AIMessage output."""
        final_state = {"messages": [AIMessage(content="Final answer")]}

        async def mock_astream(input, config=None, stream_mode=None, **kwargs):
            yield ("values", final_state)

        mock_compiled_graph.astream = mock_astream

        sg = SonderaGraph(mock_compiled_graph, harness=mock_harness)
        await sg.ainvoke({"data": "input"})

        from sondera.types import Role, Stage

        last_call = mock_harness.adjudicate.call_args_list[-1]
        assert last_call.kwargs["stage"] == Stage.POST_MODEL
        assert last_call.kwargs["role"] == Role.MODEL

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
