"""Payment Processing Agent using LangGraph with Sondera SDK.

Quickstart:
  1. Install: uv pip install -e ../archetypes && uv pip install -e ".[google]"
  2. Set keys: export GOOGLE_API_KEY=... SONDERA_API_KEY=$(uv run python scripts/generate_test_jwt.py)
  3. Run: uv run python -m langgraph_examples.payment_agent
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os

from archetypes.payments import (
    get_customer_profile,
    get_transactions,
    initiate_refund,
    send_email,
)
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import tool

from langgraph_examples.providers import DEFAULT_MODELS, Provider, make_model
from sondera.harness import SonderaRemoteHarness
from sondera.langgraph import (
    SonderaHarnessMiddleware,
    Strategy,
    create_agent_from_langchain_tools,
)


# Wrap archetype functions as LangChain tools
@tool
def lc_get_customer_profile(customer_id: str) -> str:
    """Return a customer profile with region, email, and credit card information."""
    return get_customer_profile(customer_id).model_dump_json()


@tool
def lc_get_transactions(customer_id: str, amount: float) -> str:
    """Return transaction history for a customer filtered by amount."""
    txns = get_transactions(customer_id, amount)
    return "[" + ",".join(t.model_dump_json() for t in txns) + "]"


@tool
def lc_initiate_refund(transaction_id: str, amount: float) -> str:
    """Initiate a refund for a transaction."""
    return initiate_refund(transaction_id, amount).model_dump_json()


@tool
def lc_send_email(to: str, subject: str, body: str) -> str:
    """Send an email to a recipient."""
    return send_email(to, subject, body).model_dump_json()


LC_TOOLS = [
    lc_get_customer_profile,
    lc_get_transactions,
    lc_initiate_refund,
    lc_send_email,
]


def make_system_prompt() -> str:
    """System prompt for payment agent."""
    return (
        "You are a payment processor customer service assistant. You can use the tools "
        "get_customer_profile, get_transactions, initiate_refund, and send_email. Use the tools "
        "when helpful and keep replies concise. You may handle sensitive data where policy permits."
    )


def _most_recent_ai(messages: list[BaseMessage]) -> AIMessage | None:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message
    return None


async def interactive_loop(agent_graph) -> None:
    """REPL to interact with the agent."""
    print("\nLangGraph Payment Agent Demo\n" + "-" * 40)
    print("Type your message (Ctrl-C to exit).\n")

    history: list[BaseMessage] = []

    while True:
        try:
            user_input = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        history.append(HumanMessage(content=user_input))
        result = await agent_graph.ainvoke({"messages": history})
        history = result["messages"]
        response = _most_recent_ai(history)
        if response:
            print(f"Agent: {response.content}\n")


async def build_agent(
    *,
    provider: Provider,
    model_name: str | None,
    enforce: bool,
):
    """Create the agent graph with Sondera middleware."""
    sondera_agent = create_agent_from_langchain_tools(
        tools=LC_TOOLS,
        agent_id="payment-agent-demo",
        agent_name="payment-agent-demo",
        agent_description="Handles refunds, customer inquiries, and sensitive payment data with guardrails.",
        provider_id="langchain",
        system_prompt_func=make_system_prompt,
    )

    harness = SonderaRemoteHarness(agent=sondera_agent)

    middleware = [
        SonderaHarnessMiddleware(
            harness=harness, strategy=Strategy.BLOCK if enforce else Strategy.STEER
        )
    ]
    model = make_model(provider=provider, model=model_name)
    await harness.initialize()

    return create_agent(
        model=model,
        tools=LC_TOOLS,
        system_prompt=make_system_prompt(),
        middleware=middleware,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Sondera-instrumented payment agent demo."
    )
    parser.add_argument(
        "--provider", choices=list(DEFAULT_MODELS.keys()), default="google"
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(
            logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO
        )
    )

    agent_graph = await build_agent(
        provider=args.provider,
        model_name=args.model,
        enforce=args.enforce,
    )
    await interactive_loop(agent_graph)


if __name__ == "__main__":
    asyncio.run(main())
