"""Tests for stream_ask_with_tools tool-availability behavior.

Verifies that cloud models retain tools across multiple rounds while
local models (ollama, vllm) have tools dropped after the first round
to prevent tool-call loops.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest

from sondera.tui.ai.client import (
    DoneEvent,
    StatusEvent,
    TextChunk,
    stream_ask_with_tools,
)

# ---------------------------------------------------------------------------
# Lightweight mock objects that mimic the litellm streaming response shape
# ---------------------------------------------------------------------------


@dataclass
class _MockFunction:
    name: str | None = None
    arguments: str | None = None


@dataclass
class _MockToolCall:
    index: int = 0
    id: str | None = None
    function: _MockFunction | None = None


@dataclass
class _MockDelta:
    content: str | None = None
    tool_calls: list[_MockToolCall] | None = None


@dataclass
class _MockChoice:
    delta: _MockDelta


@dataclass
class _MockChunk:
    choices: list[_MockChoice]


def _text_chunk(text: str) -> _MockChunk:
    return _MockChunk(choices=[_MockChoice(delta=_MockDelta(content=text))])


def _tool_call_chunks(
    tool_id: str, name: str, arguments: dict[str, Any]
) -> list[_MockChunk]:
    return [
        _MockChunk(
            choices=[
                _MockChoice(
                    delta=_MockDelta(
                        tool_calls=[
                            _MockToolCall(
                                index=0,
                                id=tool_id,
                                function=_MockFunction(name=name, arguments=""),
                            )
                        ]
                    )
                )
            ]
        ),
        _MockChunk(
            choices=[
                _MockChoice(
                    delta=_MockDelta(
                        tool_calls=[
                            _MockToolCall(
                                index=0,
                                function=_MockFunction(arguments=json.dumps(arguments)),
                            )
                        ]
                    )
                )
            ]
        ),
    ]


@dataclass
class _CallRecord:
    model: str
    has_tools: bool
    round_index: int


class _MockAcompletion:
    """Mock for litellm.acompletion that records calls and returns scripted responses."""

    def __init__(self, responses: list[list[_MockChunk]]) -> None:
        self.responses = responses
        self.calls: list[_CallRecord] = []
        self._call_index = 0

    async def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(
            _CallRecord(
                model=kwargs["model"],
                has_tools="tools" in kwargs,
                round_index=self._call_index,
            )
        )
        chunks = (
            self.responses[self._call_index]
            if self._call_index < len(self.responses)
            else [_text_chunk("fallback")]
        )
        self._call_index += 1

        async def _stream():
            for c in chunks:
                yield c

        return _stream()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_agents",
            "description": "List agents",
            "parameters": {"type": "object", "properties": {}},
        },
    }
]


async def _collect(aiter):
    return [e async for e in aiter]


async def _dummy_executor(name: str, args: dict) -> dict:
    return {"result": f"executed {name}"}


async def _run(
    mock, *, model="gemini/gemini-2.5-pro", execute_tool=_dummy_executor, **kw
):
    """Run stream_ask_with_tools with a mocked litellm.acompletion."""
    with patch("sondera.tui.ai.client.litellm") as mock_litellm:
        mock_litellm.acompletion = mock
        return await _collect(
            stream_ask_with_tools(
                question="test",
                context="ctx",
                model=model,
                execute_tool=execute_tool,
                **kw,
            )
        )


@pytest.fixture(autouse=True)
def _patch_tool_declarations():
    with patch("sondera.tui.ai.tools.get_tool_declarations", return_value=FAKE_TOOLS):
        yield


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCloudModelMultiRoundTools:
    """Cloud models should keep tools available across all rounds."""

    @pytest.mark.asyncio
    async def test_multi_round_tool_use(self):
        mock = _MockAcompletion(
            [
                _tool_call_chunks("tc-1", "list_agents", {}),
                _tool_call_chunks("tc-2", "list_agents", {}),
                [_text_chunk("Here are the results.")],
            ]
        )

        events = await _run(mock)

        assert len(mock.calls) == 3
        assert all(c.has_tools for c in mock.calls)
        text = "".join(e.text for e in events if isinstance(e, TextChunk))
        assert "results" in text
        assert isinstance(events[-1], DoneEvent)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "model",
        [
            "gemini/gemini-2.5-pro",
            "openai/gpt-4o",
            "anthropic/claude-sonnet-4-20250514",
        ],
    )
    async def test_tools_kept_after_round_one(self, model):
        mock = _MockAcompletion(
            [
                _tool_call_chunks("tc-1", "list_agents", {}),
                [_text_chunk("Done.")],
            ]
        )

        await _run(mock, model=model)

        assert mock.calls[0].has_tools is True
        assert mock.calls[1].has_tools is True


class TestLocalModelToolDrop:
    """Local models (ollama, vllm) should have tools dropped after round 1."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "model",
        [
            "ollama/llama3",
            "ollama/mistral",
            "vllm/meta-llama/Llama-3-8B",
        ],
    )
    async def test_tools_dropped_after_round_one(self, model):
        mock = _MockAcompletion(
            [
                _tool_call_chunks("tc-1", "list_agents", {}),
                [_text_chunk("Done.")],
            ]
        )

        await _run(mock, model=model)

        assert len(mock.calls) == 2
        assert mock.calls[0].has_tools is True
        assert mock.calls[1].has_tools is False


class TestMaxRounds:
    @pytest.mark.asyncio
    async def test_exhausts_max_rounds(self):
        mock = _MockAcompletion(
            [_tool_call_chunks(f"tc-{i}", "list_agents", {}) for i in range(10)]
        )

        events = await _run(mock, max_rounds=3)

        assert len(mock.calls) == 3
        assert isinstance(events[-1], DoneEvent)

    @pytest.mark.asyncio
    async def test_default_is_five(self):
        mock = _MockAcompletion(
            [_tool_call_chunks(f"tc-{i}", "list_agents", {}) for i in range(10)]
        )

        await _run(mock)

        assert len(mock.calls) == 5


@pytest.mark.asyncio
async def test_no_executor_no_tools():
    mock = _MockAcompletion([[_text_chunk("Hello.")]])

    await _run(mock, execute_tool=None)

    assert len(mock.calls) == 1
    assert mock.calls[0].has_tools is False


@pytest.mark.asyncio
async def test_text_only_single_round():
    mock = _MockAcompletion(
        [[_text_chunk("The dashboard shows "), _text_chunk("3 agents.")]]
    )

    events = await _run(mock)

    assert len(mock.calls) == 1
    text = "".join(e.text for e in events if isinstance(e, TextChunk))
    assert "3 agents" in text
    assert isinstance(events[-1], DoneEvent)


class TestToolExecution:
    @pytest.mark.asyncio
    async def test_executor_called(self):
        call_log: list[tuple[str, dict]] = []

        async def tracking_executor(name: str, args: dict) -> dict:
            call_log.append((name, args))
            return {"agents": ["Agent-1", "Agent-2"]}

        mock = _MockAcompletion(
            [
                _tool_call_chunks("tc-1", "list_agents", {}),
                [_text_chunk("Found 2 agents.")],
            ]
        )

        await _run(mock, execute_tool=tracking_executor)

        assert call_log == [("list_agents", {})]
        assert len(mock.calls) == 2

    @pytest.mark.asyncio
    async def test_executor_error_handled(self):
        async def failing_executor(name: str, args: dict) -> dict:
            raise RuntimeError("connection failed")

        mock = _MockAcompletion(
            [
                _tool_call_chunks("tc-1", "list_agents", {}),
                [_text_chunk("Sorry.")],
            ]
        )

        events = await _run(mock, execute_tool=failing_executor)

        assert len(mock.calls) == 2
        assert isinstance(events[-1], DoneEvent)

    @pytest.mark.asyncio
    async def test_status_events_emitted(self):
        mock = _MockAcompletion(
            [
                _tool_call_chunks("tc-1", "list_agents", {}),
                [_text_chunk("Done.")],
            ]
        )

        events = await _run(mock)

        assert any(isinstance(e, StatusEvent) for e in events)


@pytest.mark.asyncio
async def test_history_included():
    captured_kwargs: list[dict] = []

    async def capturing_acompletion(**kwargs):
        captured_kwargs.append(kwargs)

        async def _stream():
            yield _text_chunk("response")

        return _stream()

    with patch("sondera.tui.ai.client.litellm") as mock_litellm:
        mock_litellm.acompletion = capturing_acompletion
        await _collect(
            stream_ask_with_tools(
                question="follow up",
                context="ctx",
                model="gemini/gemini-2.5-pro",
                history=[("first question", "first answer")],
            )
        )

    messages = captured_kwargs[0]["messages"]
    assert (
        len(messages) == 4
    )  # system + history user + history assistant + current user
    assert messages[1] == {"role": "user", "content": "first question"}
    assert messages[2] == {"role": "assistant", "content": "first answer"}
