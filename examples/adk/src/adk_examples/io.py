"""Shared interactive REPL for ADK examples."""

from __future__ import annotations

from google.adk.runners import InMemoryRunner
from google.genai import types


async def interactive_loop(
    runner: InMemoryRunner, app_name: str, *, title: str = "ADK Agent Demo"
) -> None:
    """REPL to interact with the agent."""
    print(f"\n{title}\n" + "-" * len(title))
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
