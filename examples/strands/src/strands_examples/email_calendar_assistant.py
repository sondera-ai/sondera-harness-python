"""Email and Calendar Assistant using Strands Agent SDK with Sondera SDK.

Quickstart:
  1. Install: uv sync
  2. Set keys: export AWS_REGION=us-east-1 AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...
  3. Login: sondera auth login
  4. Run: uv run python -m strands_examples.email_calendar_assistant

Suggested prompts:
- What unread emails do I have?
- What meetings do I have coming up?
- Schedule a meeting with John for tomorrow at 2pm about project review.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os

from archetypes.communications import (
    create_calendar_event,
    get_calendar_events,
    get_unread_emails,
    send_email,
)

from sondera.harness import SonderaRemoteHarness
from sondera.strands import SonderaHarnessHook
from strands import Agent, tool


@tool
def strands_get_unread_emails(user_id: str) -> str:
    """Get unread emails for a user.

    Args:
        user_id: User identifier

    Returns:
        List of unread emails
    """
    results = get_unread_emails(user_id)
    return "[" + ", ".join(r.model_dump_json() for r in results) + "]"


@tool
def strands_send_email(to: str, subject: str, body: str) -> str:
    """Send an email.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body content

    Returns:
        Status of email sending operation
    """
    return send_email(to, subject, body).model_dump_json()


@tool
def strands_get_calendar_events(user_id: str, date: str | None = None) -> str:
    """Get calendar events for a user.

    Args:
        user_id: User identifier
        date: Optional date filter (YYYY-MM-DD)

    Returns:
        List of calendar events
    """
    results = get_calendar_events(user_id, date)
    return "[" + ", ".join(r.model_dump_json() for r in results) + "]"


@tool
def strands_create_calendar_event(
    title: str,
    start_time: str,
    end_time: str,
    attendees: list[str],
    location: str | None = None,
) -> str:
    """Create a calendar event.

    Args:
        title: Event title
        start_time: Start time (ISO format)
        end_time: End time (ISO format)
        attendees: List of attendee emails
        location: Optional location

    Returns:
        Result of event creation
    """
    return create_calendar_event(
        title, start_time, end_time, attendees, location
    ).model_dump_json()


STRANDS_TOOLS = [
    strands_get_unread_emails,
    strands_send_email,
    strands_get_calendar_events,
    strands_create_calendar_event,
]

SYSTEM_PROMPT = """
You are an email and calendar assistant. You can use these tools:
get_unread_emails, send_email, get_calendar_events, create_calendar_event.

Help users manage their emails and calendar events efficiently.
When scheduling meetings, check for conflicts with existing events.
Keep responses concise and actionable.
"""


def create_agent(harness: SonderaRemoteHarness, *, enforce: bool) -> Agent:
    """Create a Strands agent with communications tools from archetypes."""
    hook = SonderaHarnessHook(harness=harness)

    _ = enforce  # Reserved for future enforcement mode support

    return Agent(
        model="anthropic.claude-3-5-sonnet-20241022-v2:0",
        system_prompt=SYSTEM_PROMPT,
        tools=STRANDS_TOOLS,
        hooks=[hook],
    )


async def interactive_loop(agent: Agent) -> None:
    """REPL to interact with the agent."""
    print("\nStrands Email/Calendar Assistant Demo\n" + "-" * 40)
    print("Type your message (Ctrl-C to exit).\n")

    while True:
        try:
            user_input = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        response = await agent.invoke_async(user_input)
        print(f"Agent: {response}\n")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Sondera-instrumented email/calendar assistant demo."
    )
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(
            logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO
        )
    )

    harness = SonderaRemoteHarness()
    agent = create_agent(harness, enforce=args.enforce)
    await interactive_loop(agent)


if __name__ == "__main__":
    asyncio.run(main())
