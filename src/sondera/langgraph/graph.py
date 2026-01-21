"""LangGraph state graph wrapper with Sondera trajectory tracking."""

from __future__ import annotations

import logging
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

LOGGER = logging.getLogger(__name__)


class SonderaGraph:
    """Wrapper for LangGraph compiled graphs that tracks node executions.

    Uses LangGraph's streaming API (astream) to intercept each node execution
    and record it as a trajectory step. This enables policy enforcement and
    observability for state-based workflows.

    Example:
        ```python
        from langgraph.graph import StateGraph, END
        from sondera.langgraph import SonderaGraphWrapper
        from sondera.harness import Harness

        # Build your graph
        graph = StateGraph(MyState)
        graph.add_node("node1", my_function)
        graph.add_edge("node1", END)
        compiled = graph.compile()

        # Create harness
        harness = Harness(
            sondera_harness_endpoint="localhost:50051",
            agent=agent,
        )

        # Wrap with Sondera
        wrapped = SonderaGraphWrapper(compiled, harness=harness)

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

    async def ainvoke(
        self,
        input: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute the graph with trajectory tracking via streaming.

        Args:
            input: Initial state for the graph
            config: Optional configuration dict

        Returns:
            Final state after graph execution
        """
        # Initialize trajectory
        await self._harness.initialize(agent=self._harness._agent)

        # Record initial user message if present
        if "messages" in input and input["messages"]:
            initial_msg = input["messages"][0]
            if isinstance(initial_msg, HumanMessage | BaseMessage):
                await self._record_step(
                    content=PromptContent(text=_message_to_text(initial_msg)),
                    role=Role.USER,
                    stage=Stage.PRE_MODEL,
                    node="user_input",
                )

        # Use streaming to track each node execution
        final_state = dict(input) if isinstance(input, dict) else {}
        if self._track_nodes:
            async for chunk in self._graph.astream(input, config=config):
                # chunk is {node_name: node_state_output}
                for node_name, node_state in chunk.items():
                    await self._record_node_execution(
                        node_name=node_name,
                        node_state=node_state,
                    )
                    # Merge node updates into accumulated state
                    if isinstance(node_state, dict):
                        final_state.update(node_state)
                    else:
                        final_state = node_state
        else:
            final_state = await self._graph.ainvoke(input, config=config)

        # Record final output if present
        if final_state and "messages" in final_state and final_state["messages"]:
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

    async def _record_node_execution(
        self,
        node_name: str,
        node_state: dict[str, Any],
    ) -> None:
        """Record a node execution as a trajectory step."""
        # Extract meaningful content from the node's state update
        if "messages" in node_state and node_state["messages"]:
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

    def invoke(
        self, input: dict[str, Any], config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Synchronous version of ainvoke (not recommended for production)."""
        import asyncio

        return asyncio.run(self.ainvoke(input, config))


def _message_to_text(message: BaseMessage | Any) -> str:
    """Extract text content from a message."""
    if isinstance(message, BaseMessage):
        if isinstance(message.content, str):
            return message.content
        return str(message.content)
    if isinstance(message, dict) and "content" in message:
        return str(message["content"])
    return str(message)
