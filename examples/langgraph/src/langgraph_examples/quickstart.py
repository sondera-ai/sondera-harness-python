"""Quickstart: LangGraph agent with Sondera middleware (recommended for agent-style workflows).

This example shows the **middleware** integration path, which hooks into
LangGraph's ``create_agent`` lifecycle for automatic policy enforcement
on every model call, tool call, and agent boundary.

Usage:
    # 1. Install dependencies
    cd examples/langgraph && uv sync

    # 2. Set environment variables
    export SONDERA_HARNESS_ENDPOINT=localhost:50051
    export OPENAI_API_KEY=sk-...

    # 3. Run
    uv run python -m langgraph_examples.quickstart
"""

from __future__ import annotations

import asyncio

from langchain.agents import create_agent
from langchain_core.tools import tool

from sondera import Agent, AgentCard, ReActAgentCard
from sondera.harness import SonderaRemoteHarness
from sondera.langgraph import SonderaHarnessMiddleware, Strategy


@tool
def greet(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"


async def main() -> None:
    harness = SonderaRemoteHarness(
        agent=Agent(
            id="quickstart-agent",
            provider="langgraph",
            card=AgentCard.react(
                ReActAgentCard(
                    system_instruction="Be helpful and concise",
                )
            ),
        ),
    )

    middleware = SonderaHarnessMiddleware(
        harness=harness,
        strategy=Strategy.BLOCK,
    )

    agent = create_agent(
        model="openai:gpt-4o-mini",
        tools=[greet],
        middleware=[middleware],
    )

    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "Greet Alice"}]}
    )
    for msg in result["messages"]:
        print(f"{msg.__class__.__name__}: {msg.content}")


if __name__ == "__main__":
    asyncio.run(main())
