"""Email and Calendar Assistant using ADK with Sondera SDK.

Quickstart:
  1. Install: uv sync
  2. Set keys: export GOOGLE_API_KEY=...
  3. Login: sondera auth login
  4. Run: uv run python -m adk_examples.email_calendar_assistant

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
from typing import List, Optional

from archetypes.communications import create_calendar_event as _create_calendar_event
from archetypes.communications import get_calendar_events as _get_calendar_events
from archetypes.communications import get_unread_emails as _get_unread_emails
from archetypes.communications import send_email as _send_email
from google.adk import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel

from sondera.adk import SonderaHarnessPlugin
from sondera.harness import SonderaRemoteHarness


# ADK-compatible Pydantic models with typing module hints
class Email(BaseModel):
    """Email message."""

    id: str
    sender: str
    subject: str
    body: str
    received_at: str


class SendEmailResult(BaseModel):
    """Email sending result."""

    status: str
    message_id: str
    to: str
    subject: str


class CalendarEvent(BaseModel):
    """Calendar event."""

    id: str
    title: str
    start_time: str
    end_time: str
    attendees: List[str]
    location: Optional[str] = None


class CreateEventResult(BaseModel):
    """Result of creating a calendar event."""

    status: str
    event_id: str
    title: str
    start_time: str


# ADK-compatible wrapper functions with typing module hints
def get_unread_emails(user_id: str) -> List[Email]:
    """Get unread emails for a user.

    Args:
        user_id: User identifier

    Returns:
        List of unread emails
    """
    results = _get_unread_emails(user_id)
    return [Email.model_validate(r.model_dump()) for r in results]


def send_email(to: str, subject: str, body: str) -> SendEmailResult:
    """Send an email.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body content

    Returns:
        Status of email sending operation
    """
    result = _send_email(to, subject, body)
    return SendEmailResult.model_validate(result.model_dump())


def get_calendar_events(
    user_id: str, date: Optional[str] = None
) -> List[CalendarEvent]:
    """Get calendar events for a user.

    Args:
        user_id: User identifier
        date: Optional date filter (YYYY-MM-DD)

    Returns:
        List of calendar events
    """
    results = _get_calendar_events(user_id, date)
    return [CalendarEvent.model_validate(r.model_dump()) for r in results]


def create_calendar_event(
    title: str,
    start_time: str,
    end_time: str,
    attendees: List[str],
    location: Optional[str] = None,
) -> CreateEventResult:
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
    result = _create_calendar_event(title, start_time, end_time, attendees, location)
    return CreateEventResult.model_validate(result.model_dump())


INSTRUCTION = """
You are an email and calendar assistant. You can use these tools:
get_unread_emails, send_email, get_calendar_events, create_calendar_event.

Help users manage their emails and calendar events efficiently.
When scheduling meetings, check for conflicts with existing events.
Keep responses concise and actionable.
"""


def create_agent() -> Agent:
    """Create an ADK agent with communications tools from archetypes."""
    return Agent(
        model="gemini-2.5-flash",
        name="email_calendar_assistant",
        description="Email and Calendar Assistant that manages communications and scheduling.",
        instruction=INSTRUCTION,
        tools=[
            get_unread_emails,
            send_email,
            get_calendar_events,
            create_calendar_event,
        ],
    )


async def interactive_loop(runner: InMemoryRunner, app_name: str) -> None:
    """REPL to interact with the agent."""
    print("\nADK Email/Calendar Assistant Demo\n" + "-" * 40)
    print("Type your message (Ctrl-C to exit).\n")

    session = await runner.session_service.create_session(
        user_id="user", app_name=app_name
    )

    while True:
        try:
            user_input = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        message = types.Content(
            role="user", parts=[types.Part.from_text(text=user_input)]
        )

        response_text = ""
        async for event in runner.run_async(
            user_id="user",
            session_id=session.id,
            new_message=message,
        ):
            if event.is_final_response() and event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        response_text = part.text
                        break

        if response_text:
            print(f"Agent: {response_text}\n")


async def build_runner(*, enforce: bool) -> tuple[InMemoryRunner, str]:
    """Create the ADK runner with Sondera plugin."""
    agent = create_agent()
    app_name = "email_calendar_app"

    harness = SonderaRemoteHarness()
    plugin = SonderaHarnessPlugin(harness=harness)

    runner = InMemoryRunner(
        agent=agent,
        app_name=app_name,
        plugins=[plugin],
    )

    return runner, app_name


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

    runner, app_name = await build_runner(enforce=args.enforce)
    await interactive_loop(runner, app_name)


if __name__ == "__main__":
    asyncio.run(main())
