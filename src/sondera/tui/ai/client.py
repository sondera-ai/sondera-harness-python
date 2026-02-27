"""Async LiteLLM client wrapper for the /ask feature.

Uses LiteLLM to support any provider: gemini/, openai/, anthropic/,
ollama/, vllm/, and more. Model strings follow LiteLLM format.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass
from typing import Any

import litellm

# Suppress LiteLLM's noisy debug logging in the TUI
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

_SYSTEM_PROMPT = """\
You are a governance analyst assistant embedded in the Sondera agent monitoring dashboard. \
You answer questions about agent behavior, policy violations, trajectory data, and \
governance decisions.

IMPORTANT: Always answer from the SCREEN CONTEXT first. The context contains the data \
currently visible to the user, including violation reasons, agent statuses, and trajectory \
details. Only use tools when the context genuinely lacks the information needed to answer.

SETTINGS: You can modify AI-related settings using preview_setting_update. When the user \
asks to change a setting:
1. Call preview_setting_update to show the current and proposed values
2. Tell the user what will change and ask them to confirm (yes/no)
3. Do NOT try to apply the change yourself. The system applies it when the user types 'yes'.
Read-only settings (not modifiable): SONDERA_API_TOKEN, SONDERA_ENDPOINT.

NAVIGATION: You can navigate the user between screens:
- navigate_to_agent: open an agent's detail screen
- navigate_to_trajectory: open a trajectory, optionally at a specific step
- navigate_to_violation: find and open the first violated trajectory for an agent
- navigate_to_dashboard: return to the main dashboard
When the user says 'take me to', 'show me', 'open', or 'go to', use navigation tools to \
actually navigate there, don't just describe the data.
For denials/violations, prefer navigate_to_violation over list_violations since it \
navigates directly to the violated step.

ACTIONS: You can also perform these actions directly:
- change_theme: switch themes (call with no args to list available)
- take_screenshot: save an SVG screenshot of the current screen
- show_keys: toggle the keyboard shortcuts help panel

Guidelines:
- Be concise and specific
- Reference agent names, policy IDs, and step numbers when relevant
- Use plain text, not markdown (no **, ##, ```, etc.)
- Use bullet points with - for lists
- Keep answers under 300 words unless the user asks for detail
- If a tool call fails (not found, error), fall back to what's in context
- Start your response directly, don't repeat the question
"""


# ---------------------------------------------------------------------------
# Event types for the agentic streaming loop
# ---------------------------------------------------------------------------


@dataclass
class TextChunk:
    """Streamed text fragment from the model."""

    text: str


@dataclass
class StatusEvent:
    """Status message shown during tool execution (e.g. 'Fetching trajectory...')."""

    message: str


@dataclass
class DoneEvent:
    """Signals the agentic loop has finished."""


AskEvent = TextChunk | StatusEvent | DoneEvent

ToolExecutor = Callable[[str, dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]


_SUGGESTION_PROMPT = """\
You're embedded in a governance monitoring dashboard for AI agents. Users can ask \
analytical questions about what they see (agent behavior, policy violations, trajectory \
data, governance decisions) and can also modify AI settings like model and API key.

PRIORITY: If there are violations or denied decisions, ALWAYS suggest a question about \
those. Violations are the most important thing on screen.

Based on the screen context, suggest ONE short analytical question (under 50 characters) \
referencing specific agent names or data visible on screen. Write only the question text \
in lowercase, no quotes, no punctuation at the end. Examples of good suggestions:
- what caused the input validation errors
- summarize the recent violations
- which agents have the most denials
- what went wrong in step 5
"""


async def generate_suggestion(
    context: str,
    api_key: str | None = None,
    model: str = "gemini/gemini-3.0-flash",
    api_base: str | None = None,
) -> str:
    """Generate a short suggested question based on screen context.

    Returns empty string on any failure (API error, etc.).
    """
    kwargs: dict[str, Any] = {}
    if api_key:
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["api_base"] = api_base

    response = await litellm.acompletion(
        model=model,
        messages=[
            {
                "role": "user",
                "content": (
                    f"{_SUGGESTION_PROMPT}\n"
                    f"--- CONTEXT ---\n{context}\n--- END CONTEXT ---"
                ),
            },
        ],
        **kwargs,
    )
    text = (response.choices[0].message.content or "").strip().rstrip("?.!").strip()  # type: ignore[union-attr]
    # Sanity check: reject overly long or multi-line suggestions
    if len(text) > 80 or "\n" in text:
        return ""
    # Reject suggestions about actions users can't take in the dashboard
    _bad_starts = ("how to ", "how do i ", "add ", "create ", "set up ")
    if text.lower().startswith(_bad_starts):
        return ""
    return text


async def stream_ask(
    question: str,
    context: str,
    api_key: str | None = None,
    model: str = "gemini/gemini-2.5-pro",
    api_base: str | None = None,
) -> AsyncIterator[str]:
    """Stream a response given a question and governance context.

    Yields text chunks as they arrive.
    """
    kwargs: dict[str, Any] = {}
    if api_key:
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["api_base"] = api_base

    response = await litellm.acompletion(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"--- CONTEXT ---\n{context}\n--- END CONTEXT ---\n\n"
                    f"User question: {question}"
                ),
            },
        ],
        stream=True,
        **kwargs,
    )
    async for chunk in response:  # type: ignore[union-attr]
        content = chunk.choices[0].delta.content
        if content:
            yield content


def _try_parse_text_tool_calls(text: str) -> list[dict[str, Any]] | None:
    """Try to parse text content as JSON tool call(s).

    Some models (especially small local ones via Ollama) output tool calls as
    text content rather than using the proper delta.tool_calls streaming format.
    Returns a list of {id, name, arguments} dicts, or None if not a tool call.
    """
    text = text.strip()
    if not text:
        return None

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    calls: list[dict[str, Any]] = []
    items = [data] if isinstance(data, dict) else data if isinstance(data, list) else []

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        # Wrapped format: {"type": "function", "function": {"name": ..., "arguments": ...}}
        func = item.get("function")
        if isinstance(func, dict) and "name" in func:
            calls.append(
                {
                    "id": item.get("id", f"text_call_{i}"),
                    "name": func["name"],
                    "arguments": json.dumps(func.get("arguments", {})),
                }
            )
        # Flat format: {"name": ..., "arguments": ...}
        elif "name" in item and "arguments" in item:
            args = item["arguments"]
            calls.append(
                {
                    "id": item.get("id", f"text_call_{i}"),
                    "name": item["name"],
                    "arguments": json.dumps(args)
                    if not isinstance(args, str)
                    else args,
                }
            )

    return calls if calls else None


def _extract_text_from_json(text: str) -> str | None:
    """Try to extract readable text from JSON that a model echoed back.

    Some local models wrap their response in JSON like {"response": "..."} or
    {"content": "..."} instead of returning plain text. Extract the string
    value so the user sees a readable answer.
    """
    text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    # Pick the longest string value: that's almost always the actual response
    str_vals = [
        (v.strip(), k) for k, v in data.items() if isinstance(v, str) and v.strip()
    ]
    if str_vals:
        return max(str_vals, key=lambda x: len(x[0]))[0]

    return None


async def stream_ask_with_tools(
    question: str,
    context: str,
    api_key: str | None = None,
    model: str = "gemini/gemini-2.5-pro",
    api_base: str | None = None,
    execute_tool: ToolExecutor | None = None,
    max_rounds: int = 5,
    history: list[tuple[str, str]] | None = None,
) -> AsyncIterator[AskEvent]:
    """Stream a response with function calling support.

    Yields AskEvent objects: TextChunk for streamed text, StatusEvent during
    tool fetches, DoneEvent when finished. The caller drives cancellation by
    stopping iteration.

    ``history`` is a list of (question, response) tuples from prior exchanges
    in this session so the model can follow conversational references like
    "yes", "do that", etc.
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
    ]

    # Include recent conversation history so the model can resolve references
    # like "yes", "do that", "change it". Cap at 10 most recent exchanges to
    # keep token usage reasonable.
    if history:
        for q, r in history[-10:]:
            messages.append({"role": "user", "content": q})
            if r:
                messages.append({"role": "assistant", "content": r})

    messages.append(
        {
            "role": "user",
            "content": (
                f"--- SCREEN CONTEXT ---\n{context}\n"
                f"--- END CONTEXT ---\n\n"
                f"User question: {question}"
            ),
        },
    )

    # Build tools in OpenAI-compatible format
    tools = None
    if execute_tool is not None:
        from .tools import get_tool_declarations

        tools = get_tool_declarations()

    extra: dict[str, Any] = {}
    if api_key:
        extra["api_key"] = api_key
    if api_base:
        extra["api_base"] = api_base

    for _round in range(max_rounds):
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            **extra,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await litellm.acompletion(**kwargs)

        # Accumulate streamed text and tool call fragments.
        # Some local models output tool call JSON as text content instead of
        # using delta.tool_calls. We detect this by buffering text that starts
        # with '{' or '[' and checking if it parses as a tool call.
        text_parts: list[str] = []
        text_buffer: list[str] = []
        buffering_json: bool = False
        first_text: bool = True
        tool_calls_acc: dict[int, dict[str, Any]] = {}

        async for chunk in response:  # type: ignore[union-attr]
            delta = chunk.choices[0].delta

            # Text content
            if delta.content:
                if first_text and tools:
                    first_text = False
                    stripped = delta.content.lstrip()
                    if stripped.startswith(("{", "[")):
                        # Might be a JSON tool call dumped as text, buffer it
                        buffering_json = True
                        text_buffer.append(delta.content)
                    else:
                        text_parts.append(delta.content)
                        yield TextChunk(text=delta.content)
                elif buffering_json:
                    text_buffer.append(delta.content)
                else:
                    text_parts.append(delta.content)
                    yield TextChunk(text=delta.content)

            # Tool call chunks (accumulated by index)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {
                            "id": "",
                            "name": "",
                            "arguments": "",
                        }
                    if tc.id:
                        tool_calls_acc[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls_acc[idx]["name"] = tc.function.name
                        if tc.function.arguments:
                            tool_calls_acc[idx]["arguments"] += tc.function.arguments

        # Check if buffered text is actually a JSON tool call
        if buffering_json and text_buffer:
            full_text = "".join(text_buffer)
            parsed = _try_parse_text_tool_calls(full_text)
            if parsed and execute_tool is not None:
                # Treat as proper tool calls
                for i, tc_data in enumerate(parsed):
                    tool_calls_acc[len(tool_calls_acc) + i] = tc_data
            else:
                # Not a tool call: try to extract readable text from JSON
                extracted = _extract_text_from_json(full_text)
                display = extracted if extracted else full_text
                yield TextChunk(text=display)
                text_parts.append(display)
        elif not tool_calls_acc and text_parts and execute_tool is not None:
            # Fallback: text was streamed but might still be a JSON tool call
            # (e.g. first chunk didn't start with '{' due to whitespace)
            full_text = "".join(text_parts)
            parsed = _try_parse_text_tool_calls(full_text)
            if parsed:
                for i, tc_data in enumerate(parsed):
                    tool_calls_acc[i] = tc_data
                # Clear text_parts so we don't include JSON in conversation
                text_parts.clear()

        # If no tool calls, we're done
        if not tool_calls_acc or execute_tool is None:
            yield DoneEvent()
            return

        # Build assistant message with tool calls for conversation history
        assistant_msg: dict[str, Any] = {"role": "assistant"}
        if text_parts:
            assistant_msg["content"] = "".join(text_parts)
        assistant_msg["tool_calls"] = [
            {
                "id": tc_data["id"],
                "type": "function",
                "function": {
                    "name": tc_data["name"],
                    "arguments": tc_data["arguments"],
                },
            }
            for _, tc_data in sorted(tool_calls_acc.items())
        ]
        messages.append(assistant_msg)

        # Execute each tool call and add results to conversation
        for _, tc_data in sorted(tool_calls_acc.items()):
            tool_name = tc_data["name"]
            try:
                tool_args = (
                    json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                )
            except json.JSONDecodeError:
                tool_args = {}

            short_desc = _tool_status_message(tool_name, tool_args)
            yield StatusEvent(message=short_desc)

            try:
                result = await execute_tool(tool_name, tool_args)
            except Exception as e:
                result = {"error": str(e)[:300]}

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc_data["id"],
                    "content": json.dumps(result),
                }
            )
        # Local models (ollama, vllm) get stuck in tool-call loops;
        # drop tools after the first round so they must respond with text.
        # Cloud models handle multi-round tool use correctly.
        if model.split("/", 1)[0] in ("ollama", "vllm"):
            tools = None

    # Exhausted max rounds
    yield DoneEvent()


_STATUS_TEMPLATES: dict[str, str | Callable[[dict[str, Any]], str]] = {
    "list_agents": "Listing agents...",
    "get_trajectory": lambda args: (
        f"Fetching trajectory {str(args.get('trajectory_id', ''))[:16]}..."
    ),
    "list_agent_trajectories": lambda args: (
        f"Listing trajectories for {args.get('agent_name_or_id', '')}..."
    ),
    "list_violations": lambda args: (
        f"Fetching violations for {args['agent_name_or_id']}..."
        if args.get("agent_name_or_id")
        else "Fetching recent violations..."
    ),
    "get_agent_details": lambda args: (
        f"Fetching details for {args.get('agent_name_or_id', '')}..."
    ),
    "preview_setting_update": lambda args: (
        f"Previewing {args.get('key', '')} change..."
    ),
    "change_theme": lambda args: f"Switching to {args.get('theme', '')}...",
    "take_screenshot": "Taking screenshot...",
    "show_keys": "Toggling keys panel...",
    "navigate_to_agent": lambda args: f"Opening {args.get('agent_name_or_id', '')}...",
    "navigate_to_trajectory": lambda args: (
        f"Opening trajectory {str(args.get('trajectory_id', ''))[:16]}..."
    ),
    "navigate_to_dashboard": "Going to dashboard...",
    "navigate_to_violation": lambda args: (
        f"Finding violations for {args.get('agent_name_or_id', '')}..."
    ),
}


def _tool_status_message(name: str, args: dict[str, Any]) -> str:
    """Human-readable status message for a tool call."""
    template = _STATUS_TEMPLATES.get(name)
    if template is None:
        return f"Calling {name}..."
    return template(args) if callable(template) else template
