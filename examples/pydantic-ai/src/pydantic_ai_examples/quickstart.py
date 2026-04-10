"""Quickstart: Pydantic AI agent with Sondera governance.

This example shows the ``SonderaProvider`` integration path, which uses
``govern()`` to mutate a Pydantic AI agent in place for automatic policy
enforcement on every tool call.

Usage:
    # 1. Install dependencies
    cd examples/pydantic-ai && uv sync --group google

    # 2. Set environment variables
    export GOOGLE_API_KEY=...

    # 3. Run (with Sondera auth)
    sondera auth login
    uv run python -m pydantic_ai_examples.quickstart
"""

from __future__ import annotations

import asyncio
import os

from pydantic_ai import Agent
from sondera.harness import SonderaRemoteHarness
from sondera.pydantic import SonderaProvider, Strategy


def greet(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"


async def main() -> None:
    # Pick model based on available API keys
    if os.environ.get("OPENAI_API_KEY"):
        model = "openai:gpt-4o-mini"
    elif os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        model = "google-gla:gemini-2.5-flash"
    elif os.environ.get("ANTHROPIC_API_KEY"):
        model = "anthropic:claude-haiku-4-5-20251001"
    else:
        model = "google-gla:gemini-2.5-flash"

    # Create a Pydantic AI agent with one tool
    agent = Agent(
        model,
        system_prompt="Be helpful and concise.",
        tools=[greet],  # type: ignore[arg-type]
    )

    # Build Sondera governance
    provider = SonderaProvider(strategy=Strategy.BLOCK)
    agent_card = provider.build_agent_card(agent, agent_id="pydantic-quickstart-demo")

    harness = SonderaRemoteHarness()
    provider.govern(agent, harness=harness, agent_card=agent_card)

    # Run governed agent
    result = await agent.run("Greet Alice")
    print(f"Result: {result.output}")


if __name__ == "__main__":
    asyncio.run(main())
