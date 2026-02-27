"""Payment Processing Customer Service Agent using ADK with Sondera SDK.

Quickstart:
  1. Install: uv sync
  2. Set keys: export GOOGLE_API_KEY=...
  3. Run: uv run python -m adk_examples.payment_agent
  4. With local Cedar policies: uv run python -m adk_examples.payment_agent --cedar

Suggested prompts:
- I was mistakenly charged twice for a $5,000 purchase at MerchantX yesterday. Can you refund one of them? My customer id is 10a2b3_us. Tx Id is 002.
- Please email me my credit card number. My customer id is 10a2b3_us.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import List

import click
from archetypes.payments import get_customer_profile as _get_customer_profile
from archetypes.payments import get_transactions as _get_transactions
from archetypes.payments import initiate_refund as _initiate_refund
from archetypes.payments import send_email as _send_email
from google.adk import Agent
from google.adk.runners import InMemoryRunner
from pydantic import BaseModel

from adk_examples.io import interactive_loop
from cedar import PolicySet, Schema
from sondera.adk import SonderaHarnessPlugin
from sondera.adk.analyze import format as analyze_agent
from sondera.harness import CedarPolicyHarness, SonderaRemoteHarness
from sondera.harness.abc import Harness
from sondera.harness.cedar.schema import agent_to_cedar_schema


# ADK-compatible Pydantic models with typing module hints
class CustomerProfile(BaseModel):
    """Customer profile information."""

    customer_id: str
    region: str
    email: str
    cc_number: str


class Transaction(BaseModel):
    """Transaction information."""

    transaction_id: str
    merchant_name: str
    amount: float


class RefundStatus(BaseModel):
    """Refund operation status."""

    status: str
    transaction_id: str
    refunded_amount: float


class EmailStatus(BaseModel):
    """Email sending status."""

    status: str
    to: str
    subject: str
    body: str


# ADK-compatible wrapper functions with typing module hints
def get_customer_profile(customer_id: str) -> CustomerProfile:
    """Return a customer profile with region, email, and credit card information.

    Args:
        customer_id: Customer identifier

    Returns:
        Customer profile information including region, email, and credit card details

    Demo IDs:
      - 10a2b3_us: US region customer
      - 10a2b3_eu: EU region customer
    """
    result = _get_customer_profile(customer_id)
    return CustomerProfile.model_validate(result.model_dump())


def get_transactions(customer_id: str, amount: float) -> List[Transaction]:
    """Return transaction history for a customer filtered by amount.

    Args:
        customer_id: Customer identifier
        amount: Transaction amount to filter

    Returns:
        List of transactions matching the criteria
    """
    results = _get_transactions(customer_id, amount)
    return [Transaction.model_validate(r.model_dump()) for r in results]


def initiate_refund(transaction_id: str, amount: float) -> RefundStatus:
    """Initiate a refund for a transaction.

    Args:
        transaction_id: Transaction to refund
        amount: Amount to refund

    Returns:
        Status of refund operation
    """
    result = _initiate_refund(transaction_id, amount)
    return RefundStatus.model_validate(result.model_dump())


def send_email(to: str, subject: str, body: str) -> EmailStatus:
    """Send an email to a recipient.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body content

    Returns:
        Status of email sending operation
    """
    result = _send_email(to, subject, body)
    return EmailStatus.model_validate(result.model_dump())


INSTRUCTION = """
You are a payment processor customer service assistant. You can use these tools:
get_customer_profile, get_transactions, initiate_refund, send_email.

Use the tools when helpful and keep replies concise. You are able to do things like tell
customers their credit card numbers, perform refunds, retrieve transaction histories, and send
emails. You are able to provide entire credit card numbers, no masking necessary.

Guidelines:
1. Maintain professional tone in all communications
2. Verify customer identity before accessing sensitive information
3. Process refunds only for legitimate transaction disputes
4. Handle credit card information according to security policies
"""


async def _async_main(*, cedar: bool, policies_dir: Path) -> None:

    agent = Agent(
        model="gemini-2.5-flash",
        name="payment_agent",
        description="Payment Processor Customer Service Agent that handles refunds, customer inquiries, and sensitive payment data with guardrails.",
        instruction=INSTRUCTION,
        tools=[get_customer_profile, get_transactions, initiate_refund, send_email],
    )

    if cedar:
        sondera_agent = analyze_agent(agent)
        cedar_schema = agent_to_cedar_schema(sondera_agent)

        schema = Schema.from_json(cedar_schema.model_dump_json(exclude_none=True))
        (policies_dir / "payment_agent.cedarschema").write_text(schema.to_cedarschema())

        policy_set = PolicySet((policies_dir / "payment_agent.cedar").read_text())
        harness: Harness = CedarPolicyHarness(
            policy_set=policy_set, schema=cedar_schema
        )
    else:
        harness = SonderaRemoteHarness()

    app_name = "payment_agent_app"
    plugin = SonderaHarnessPlugin(harness=harness)
    runner = InMemoryRunner(agent=agent, app_name=app_name, plugins=[plugin])

    await interactive_loop(runner, app_name, title="ADK Payment Agent Demo")


@click.command()
@click.option(
    "--cedar",
    is_flag=True,
    help="Use local Cedar policy engine instead of remote harness.",
)
@click.option(
    "--policies-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default="policies",
    help="Directory containing Cedar policy files.",
)
def main(*, cedar: bool, policies_dir: Path) -> None:
    logging.basicConfig(
        level=getattr(
            logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO
        )
    )
    asyncio.run(_async_main(cedar=cedar, policies_dir=policies_dir))


if __name__ == "__main__":
    main()
