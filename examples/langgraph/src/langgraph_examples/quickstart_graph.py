"""Quickstart: Custom StateGraph with SonderaGraph wrapper.

This example shows the **SonderaGraph** integration path for custom
``StateGraph`` workflows where you control the graph topology. Each
node execution is tracked as a trajectory step for policy evaluation.

No LLM dependency — pure function nodes for easy local testing.

Usage:
    # 1. Install dependencies
    cd examples/langgraph && uv sync

    # 2. Set environment variables
    export SONDERA_HARNESS_ENDPOINT=localhost:50051

    # 3. Run
    uv run python -m langgraph_examples.quickstart_graph
"""

from __future__ import annotations

import asyncio
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from sondera import Agent, AgentCard, ReActAgentCard
from sondera.harness import SonderaRemoteHarness
from sondera.langgraph import SonderaGraph


class WorkflowState(TypedDict, total=False):
    query: str
    processed: str
    result: str


def preprocess(state: WorkflowState) -> dict[str, Any]:
    """Normalize the input query."""
    return {"processed": state.get("query", "").strip().lower()}


def compute(state: WorkflowState) -> dict[str, Any]:
    """Compute a result from the processed query."""
    text = state.get("processed", "")
    return {"result": f"Computed result for: {text}"}


def build_graph() -> StateGraph:
    graph = StateGraph(WorkflowState)
    graph.add_node("preprocess", preprocess)
    graph.add_node("compute", compute)
    graph.set_entry_point("preprocess")
    graph.add_edge("preprocess", "compute")
    graph.add_edge("compute", END)
    return graph


async def main() -> None:
    harness = SonderaRemoteHarness(
        agent=Agent(
            id="quickstart-graph-agent",
            provider="langgraph",
            card=AgentCard.react(
                ReActAgentCard(
                    system_instruction="Process queries deterministically",
                )
            ),
        ),
    )

    compiled = build_graph().compile()
    wrapped = SonderaGraph(compiled, harness=harness)

    result = await wrapped.ainvoke({"query": "  Hello World  "})
    print(f"Result: {result['result']}")


if __name__ == "__main__":
    asyncio.run(main())
