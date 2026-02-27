"""LangGraph state graph wrapper with Sondera trajectory tracking."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterator
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from sondera.harness import Harness
from sondera.types import (
    Adjudication,
    Content,
    Decision,
    PromptContent,
    Role,
    Stage,
    ToolResponseContent,
)

from .exceptions import GuardrailViolationError

try:
    from langgraph.graph.state import CompiledStateGraph
except ImportError:  # pragma: no cover
    CompiledStateGraph = None  # type: ignore[assignment,misc]

LOGGER = logging.getLogger(__name__)


class SonderaGraph:
    """Wrapper for LangGraph compiled graphs that tracks node executions.

    Uses LangGraph's streaming API to intercept each node execution
    and record it as a trajectory step. This enables policy enforcement and
    observability for state-based workflows.

    Example:
        ```python
        from langgraph.graph import StateGraph, END
        from sondera.langgraph import SonderaGraph
        from sondera.harness import SonderaRemoteHarness

        # Build your graph
        graph = StateGraph(MyState)
        graph.add_node("node1", my_function)
        graph.add_edge("node1", END)
        compiled = graph.compile()

        # Create harness
        harness = SonderaRemoteHarness(agent=agent)

        # Wrap with Sondera
        wrapped = SonderaGraph(compiled, harness=harness)

        # Execute - node executions will be tracked
        result = await wrapped.ainvoke(initial_state)
        ```
    """

    def __init__(
        self,
        compiled_graph: Any,
        *,
        harness: Harness,
        track_nodes: bool = True,
        enforce: bool = True,
    ) -> None:
        """Initialize the graph wrapper.

        Args:
            compiled_graph: The LangGraph compiled graph to wrap
            harness: Sondera harness for policy enforcement
            track_nodes: Whether to track node executions (default: True)
            enforce: Whether to enforce policy decisions (default: True)
        """
        self._graph = compiled_graph
        self._harness = harness
        self._track_nodes = track_nodes
        self._enforce = enforce
        self._logger = LOGGER

    # -- Properties that pass through to the underlying graph -----------------

    @property
    def name(self) -> str:
        """Name of the underlying graph."""
        return self._graph.name

    @property
    def input_schema(self) -> Any:
        """Input schema of the underlying graph."""
        return self._graph.input_schema

    @property
    def output_schema(self) -> Any:
        """Output schema of the underlying graph."""
        return self._graph.output_schema

    # -- Core invoke / stream methods -----------------------------------------

    async def ainvoke(
        self,
        input: dict[str, Any] | Any,
        config: dict[str, Any] | None = None,
        *,
        context: dict[str, Any] | None = None,
        output_keys: str | list[str] | None = None,
        interrupt_before: list[str] | None = None,
        interrupt_after: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute the graph with trajectory tracking via streaming.

        Args:
            input: Initial state for the graph
            config: Optional configuration dict
            context: Optional context dict (passed to underlying graph)
            output_keys: Keys to include in output
            interrupt_before: Nodes to interrupt before
            interrupt_after: Nodes to interrupt after
            **kwargs: Additional keyword arguments forwarded to the graph

        Returns:
            Final state after graph execution
        """
        # Initialize trajectory
        await self._harness.initialize(agent=self._harness.agent)

        # Record initial user message if present
        if isinstance(input, dict) and "messages" in input and input["messages"]:
            initial_msg = input["messages"][0]
            if isinstance(initial_msg, HumanMessage | BaseMessage):
                await self._record_step(
                    content=PromptContent(text=_message_to_text(initial_msg)),
                    role=Role.USER,
                    stage=Stage.PRE_MODEL,
                    node="user_input",
                )

        # Build shared kwargs for the underlying graph call
        graph_kwargs: dict[str, Any] = {**kwargs}
        if context is not None:
            graph_kwargs["context"] = context
        if output_keys is not None:
            graph_kwargs["output_keys"] = output_keys
        if interrupt_before is not None:
            graph_kwargs["interrupt_before"] = interrupt_before
        if interrupt_after is not None:
            graph_kwargs["interrupt_after"] = interrupt_after

        # Execute the graph
        if self._track_nodes:
            # Multi-mode streaming: "updates" for per-node tracking,
            # "values" for the final reducer-resolved state.
            final_state: dict[str, Any] | Any = None
            async for mode, chunk in self._graph.astream(
                input,
                config=config,
                stream_mode=["updates", "values"],
                **graph_kwargs,
            ):
                if mode == "updates":
                    if isinstance(chunk, dict):
                        for node_name, node_state in chunk.items():
                            await self._record_node_execution(
                                node_name=node_name,
                                node_state=node_state,
                            )
                elif mode == "values":
                    final_state = chunk
        else:
            final_state = await self._graph.ainvoke(
                input, config=config, **graph_kwargs
            )

        # Record final output if present
        if (
            final_state
            and isinstance(final_state, dict)
            and "messages" in final_state
            and final_state["messages"]
        ):
            final_msg = final_state["messages"][-1]
            if isinstance(final_msg, AIMessage | BaseMessage):
                await self._record_step(
                    content=PromptContent(text=_message_to_text(final_msg)),
                    role=Role.MODEL,
                    stage=Stage.POST_MODEL,
                    node="final_output",
                )

        # Finalize trajectory
        await self._harness.finalize()

        return final_state

    def invoke(
        self,
        input: dict[str, Any] | Any,
        config: dict[str, Any] | None = None,
        *,
        context: dict[str, Any] | None = None,
        output_keys: str | list[str] | None = None,
        interrupt_before: list[str] | None = None,
        interrupt_after: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Synchronous version of ainvoke."""
        return asyncio.run(
            self.ainvoke(
                input,
                config,
                context=context,
                output_keys=output_keys,
                interrupt_before=interrupt_before,
                interrupt_after=interrupt_after,
                **kwargs,
            )
        )

    async def astream(
        self,
        input: dict[str, Any] | Any,
        config: dict[str, Any] | None = None,
        *,
        stream_mode: str | list[str] | None = None,
        context: dict[str, Any] | None = None,
        output_keys: str | list[str] | None = None,
        interrupt_before: list[str] | None = None,
        interrupt_after: list[str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        """Stream graph execution with optional trajectory tracking.

        When the user's ``stream_mode`` includes ``"updates"``, node
        executions are recorded as a side-effect.  Otherwise only
        lifecycle management (initialize / finalize) is performed.

        Yields chunks from the underlying graph's ``astream``.
        """
        await self._harness.initialize(agent=self._harness.agent)

        graph_kwargs: dict[str, Any] = {**kwargs}
        if context is not None:
            graph_kwargs["context"] = context
        if output_keys is not None:
            graph_kwargs["output_keys"] = output_keys
        if interrupt_before is not None:
            graph_kwargs["interrupt_before"] = interrupt_before
        if interrupt_after is not None:
            graph_kwargs["interrupt_after"] = interrupt_after

        # Determine whether we can intercept updates for tracking
        modes = (
            stream_mode if isinstance(stream_mode, list) else [stream_mode or "values"]
        )
        track = self._track_nodes and "updates" in modes
        is_multi = isinstance(stream_mode, list)

        try:
            async for chunk in self._graph.astream(
                input, config=config, stream_mode=stream_mode, **graph_kwargs
            ):
                # When multi-mode, chunk is (mode, data)
                if track and is_multi:
                    mode, data = chunk
                    if mode == "updates" and isinstance(data, dict):
                        for node_name, node_state in data.items():
                            await self._record_node_execution(node_name, node_state)
                elif track and not is_multi and stream_mode == "updates":
                    if isinstance(chunk, dict):
                        for node_name, node_state in chunk.items():
                            await self._record_node_execution(node_name, node_state)
                yield chunk
        finally:
            await self._harness.finalize()

    def stream(
        self,
        input: dict[str, Any] | Any,
        config: dict[str, Any] | None = None,
        *,
        stream_mode: str | list[str] | None = None,
        context: dict[str, Any] | None = None,
        output_keys: str | list[str] | None = None,
        interrupt_before: list[str] | None = None,
        interrupt_after: list[str] | None = None,
        **kwargs: Any,
    ) -> Iterator[Any]:
        """Synchronous version of astream."""
        loop = asyncio.new_event_loop()
        try:
            aiter = self.astream(
                input,
                config,
                stream_mode=stream_mode,
                context=context,
                output_keys=output_keys,
                interrupt_before=interrupt_before,
                interrupt_after=interrupt_after,
                **kwargs,
            )
            while True:
                try:
                    yield loop.run_until_complete(aiter.__anext__())
                except StopAsyncIteration:
                    break
        finally:
            loop.close()

    # -- Delegation methods ---------------------------------------------------

    def get_state(self, config: dict[str, Any], **kwargs: Any) -> Any:
        """Get the current state of the graph. Delegates to underlying graph."""
        return self._graph.get_state(config, **kwargs)

    async def aget_state(self, config: dict[str, Any], **kwargs: Any) -> Any:
        """Async get the current state. Delegates to underlying graph."""
        return await self._graph.aget_state(config, **kwargs)

    def update_state(
        self, config: dict[str, Any], values: dict[str, Any], **kwargs: Any
    ) -> Any:
        """Update the graph state. Delegates to underlying graph."""
        return self._graph.update_state(config, values, **kwargs)

    async def aupdate_state(
        self, config: dict[str, Any], values: dict[str, Any], **kwargs: Any
    ) -> Any:
        """Async update the graph state. Delegates to underlying graph."""
        return await self._graph.aupdate_state(config, values, **kwargs)

    def get_graph(self, **kwargs: Any) -> Any:
        """Get the graph structure. Delegates to underlying graph."""
        return self._graph.get_graph(**kwargs)

    async def aget_graph(self, **kwargs: Any) -> Any:
        """Async get the graph structure. Delegates to underlying graph."""
        return await self._graph.aget_graph(**kwargs)

    def get_state_history(self, config: dict[str, Any], **kwargs: Any) -> Any:
        """Get state history. Delegates to underlying graph."""
        return self._graph.get_state_history(config, **kwargs)

    async def aget_state_history(self, config: dict[str, Any], **kwargs: Any) -> Any:
        """Async get state history. Delegates to underlying graph."""
        return await self._graph.aget_state_history(config, **kwargs)

    # -- Internal helpers -----------------------------------------------------

    async def _record_node_execution(
        self,
        node_name: str,
        node_state: dict[str, Any],
    ) -> None:
        """Record a node execution as a trajectory step."""
        # Extract meaningful content from the node's state update
        if (
            isinstance(node_state, dict)
            and "messages" in node_state
            and node_state["messages"]
        ):
            last_msg = node_state["messages"][-1]
            if isinstance(last_msg, BaseMessage):
                content = _message_to_text(last_msg)
            else:
                content = str(last_msg)
        else:
            # For non-message nodes, summarize the state change
            content = f"Node '{node_name}' updated state"

        await self._record_step(
            content=ToolResponseContent(tool_id=node_name, response=content),
            role=Role.TOOL,  # Nodes are like tool executions
            stage=Stage.POST_TOOL,
            node=node_name,
        )

    async def _record_step(
        self,
        *,
        content: Content,
        role: Role,
        stage: Stage,
        node: str,
    ) -> Adjudication:
        """Record and adjudicate a trajectory step."""
        # Adjudicate with policy engine via harness
        adjudication = await self._harness.adjudicate(
            stage=stage,
            role=role,
            content=content,
        )

        # Enforce DENY decisions if enabled
        if adjudication.decision is Decision.DENY and self._enforce:
            raise GuardrailViolationError(
                stage=stage,
                node=node,
                reason=adjudication.reason,
            )

        return adjudication


def _message_to_text(message: BaseMessage | Any) -> str:
    """Extract text content from a message."""
    if isinstance(message, BaseMessage):
        if isinstance(message.content, str):
            return message.content
        return str(message.content)
    if isinstance(message, dict) and "content" in message:
        return str(message["content"])
    return str(message)
