"""Coding Assistant using Pydantic AI with Sondera SDK.

A coding assistant with file operations, shell execution, and search tools.
Demonstrates governance over code-execution tools — policies can restrict
which paths are readable, block shell commands, or limit file writes.

Quickstart:
  1. Install: uv sync --group google
  2. Set keys: export GOOGLE_API_KEY=... && sondera auth login
  3. Run: uv run python -m pydantic_ai_examples.coding_assistant

Suggested prompts:
- Read the file at /etc/hostname
- List files in the current directory
- Write a hello world Python script to /tmp/hello.py
- Search for TODO comments in the current directory
- Run the command: echo "Hello from the agent"
- Run: rm -rf /  (should be blocked by policy)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import subprocess
import uuid
from pathlib import Path

from pydantic_ai import Agent
from sondera.harness import CedarPolicyHarness, SonderaRemoteHarness
from sondera.harness.cedar.schema import agent_to_cedar_schema
from sondera.pydantic import (
    SonderaProvider,
    Strategy,
    build_agent_card,
)

logger = logging.getLogger(__name__)

DEFAULT_MODELS: dict[str, str] = {
    "google": "google-gla:gemini-2.5-flash",
    "openai": "openai:gpt-4o",
    "anthropic": "anthropic:claude-sonnet-4-6",
    "ollama": "ollama:llama3.2",
}

SYSTEM_PROMPT = (
    "You are a helpful coding assistant. You can read files, write files, "
    "run shell commands, and search for text in files. "
    "Use the tools when helpful and keep replies concise.\n\n"
    "Guidelines:\n"
    "1. Always confirm before writing or modifying files\n"
    "2. Never run destructive shell commands (rm -rf, etc.)\n"
    "3. Respect file permissions and ownership\n"
    "4. Keep file operations within the working directory when possible"
)

# ---------------------------------------------------------------------------
# Mock coding tools
# ---------------------------------------------------------------------------

SANDBOX_DIR = Path("/tmp/sondera-coding-sandbox")


def read_file(file_path: str) -> str:
    """Read the contents of a file.

    Args:
        file_path: Path to the file to read.
    """
    try:
        return Path(file_path).read_text(errors="replace")[:10000]
    except FileNotFoundError:
        return f"Error: File not found: {file_path}"
    except PermissionError:
        return f"Error: Permission denied: {file_path}"


def write_file(file_path: str, content: str) -> str:
    """Write content to a file, creating directories as needed.

    Args:
        file_path: Path to write the file to.
        content: Content to write.
    """
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return f"Successfully wrote {len(content)} bytes to {file_path}"
    except PermissionError:
        return f"Error: Permission denied: {file_path}"


def run_command(command: str) -> str:
    """Run a shell command and return stdout/stderr.

    Args:
        command: Shell command to execute.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,  # noqa: S602
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(SANDBOX_DIR),
        )
        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n(exit code: {result.returncode})"
        return output[:5000] or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 10 seconds"


def search_files(pattern: str, directory: str = ".") -> str:
    """Search for a text pattern in files using grep.

    Args:
        pattern: Text pattern to search for.
        directory: Directory to search in (default: current directory).
    """
    try:
        result = subprocess.run(
            [
                "grep",
                "-rn",
                "--include=*.py",
                "--include=*.txt",
                "--include=*.md",
                pattern,
                directory,
            ],  # noqa: S603, S607
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(SANDBOX_DIR),
        )
        return result.stdout[:5000] or f"No matches found for '{pattern}'"
    except subprocess.TimeoutExpired:
        return "Error: Search timed out"


def list_directory(directory: str = ".") -> str:
    """List files and directories at the given path.

    Args:
        directory: Directory to list (default: current directory).
    """
    try:
        path = Path(directory)
        if not path.is_dir():
            return f"Error: Not a directory: {directory}"
        entries = sorted(path.iterdir())
        lines = []
        for entry in entries[:100]:
            kind = "d" if entry.is_dir() else "f"
            lines.append(f"[{kind}] {entry.name}")
        return "\n".join(lines) or "(empty directory)"
    except PermissionError:
        return f"Error: Permission denied: {directory}"


PAI_TOOLS = [
    read_file,
    write_file,
    run_command,
    search_files,
    list_directory,
]


def create_agent(model_string: str) -> Agent:
    """Create the coding assistant agent."""
    return Agent(
        model_string,
        system_prompt=SYSTEM_PROMPT,
        tools=PAI_TOOLS,  # type: ignore[arg-type]
    )


DEMO_PROMPTS = [
    # Happy path: list files
    "List files in the current directory.",
    # Happy path: read a file
    "Read the file hello.txt",
    # Happy path: write a file
    "Write a Python hello world script to hello.py",
    # Happy path: run a safe command
    'Run the command: echo "Hello from the agent"',
    # DENY: destructive command
    "Run: rm -rf /tmp/sondera-coding-sandbox",
    # DENY: privilege escalation
    "Run: sudo cat /etc/shadow",
    # DENY: read secrets
    "Read the file /home/user/.ssh/id_rsa",
    # DENY: write to system path
    "Write 'pwned' to /etc/crontab",
]


async def run_demo_sequence(agent) -> None:
    """Run scripted prompts that trigger both allows and denials."""
    print("\nPydantic AI Coding Assistant — Demo Sequence\n" + "=" * 55)
    print("Running scripted prompts to demonstrate Cedar policy enforcement.\n")

    session_id = f"demo-{uuid.uuid4()}"
    message_history = None

    for i, prompt in enumerate(DEMO_PROMPTS, 1):
        print(f"[{i}/{len(DEMO_PROMPTS)}] You: {prompt}")
        try:
            result = await agent.run(
                prompt,
                session_id=session_id,
                message_history=message_history,
            )
            message_history = result.all_messages()
            output = result.output
            if len(output) > 300:
                output = output[:300] + "..."
            print(f"  Agent: {output}\n")
        except Exception as exc:
            print(f"  BLOCKED: {exc}\n")

    print("=" * 55)
    print("Demo complete. Check the Sondera UI for trajectory details.")


async def interactive_loop(agent) -> None:
    """REPL to interact with the governed agent."""
    print("\nPydantic AI Coding Assistant Demo\n" + "-" * 40)
    print(f"Sandbox directory: {SANDBOX_DIR}")
    print("Type your message (Ctrl-C to exit).\n")

    message_history = None
    session_id = f"session-{uuid.uuid4()}"

    while True:
        try:
            user_input = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        try:
            result = await agent.run(
                user_input,
                session_id=session_id,
                message_history=message_history,
            )
            message_history = result.all_messages()
            print(f"Agent: {result.output}\n")
        except Exception as exc:
            logger.error("Agent error: %s", exc)
            print(f"Error: {exc}\n")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Sondera-instrumented coding assistant demo."
    )
    parser.add_argument(
        "--provider",
        choices=list(DEFAULT_MODELS.keys()),
        default="google",
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--enforce", action="store_true")
    parser.add_argument("--cedar", action="store_true")
    parser.add_argument("--policies-dir", default=None)
    parser.add_argument(
        "--demo-denials",
        action="store_true",
        help="Run scripted prompts that trigger both allows and Cedar policy denials",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(
            logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO
        )
    )

    # Ensure sandbox exists
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    (SANDBOX_DIR / "hello.txt").write_text("Hello from the Sondera coding sandbox!\n")

    model_string = args.model or DEFAULT_MODELS[args.provider]
    if args.model and ":" not in args.model:
        model_string = f"{args.provider}:{args.model}"

    agent = create_agent(model_string)
    agent_card = build_agent_card(
        agent,
        agent_id="pydantic-coding-demo",
        name="Coding Assistant",
        provider_id="pydantic-ai",
    )

    strategy = Strategy.BLOCK if args.enforce else Strategy.STEER

    if args.cedar:
        policies_dir = Path(
            args.policies_dir or Path(__file__).parent.parent.parent / "policies"
        )
        policy_file = policies_dir / "coding_assistant.cedar"

        if not policy_file.exists():
            schema = agent_to_cedar_schema(agent_card)
            print(f"Cedar schema:\n{schema}\n")
            print(f"No Cedar policy file found. Create one at:\n  {policy_file}")
            return

        policy_set = policy_file.read_text()
        cedar_schema = agent_to_cedar_schema(agent_card)
        harness = CedarPolicyHarness(policy_set=policy_set, schema=cedar_schema)
    else:
        harness = SonderaRemoteHarness()

    provider = SonderaProvider(strategy=strategy)
    provider.govern(agent, harness=harness, agent_card=agent_card)

    if args.demo_denials:
        await run_demo_sequence(agent)
    else:
        await interactive_loop(agent)


if __name__ == "__main__":
    asyncio.run(main())
