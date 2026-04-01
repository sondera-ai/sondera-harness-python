"""AI Assist session lifecycle: trajectory creation for conversations.

Wraps Harness lifecycle (initialize/adjudicate/finalize) to
persist AI conversations as trajectories on the Sondera Platform and
enforce policy decisions at each stage.

Follows the custom integration pattern from docs.sondera.ai/integrations/custom/.
All methods are exception-safe: errors are logged, never raised.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import sondera.settings as _settings
from sondera.harness import Harness, SonderaRemoteHarness
from sondera.types import (
    Adjudicated,
    Agent,
    Event,
    Prompt,
    PromptRole,
    ToolCall,
    ToolOutput,
)

_log = logging.getLogger(__name__)

# Agent definition following the custom integration pattern.
_AI_AGENT = Agent(
    id="sondera-ai-assistant",
    provider="sondera-tui",
)


class AskSession:
    """Manages the lifecycle of an AI Assist conversation trajectory.

    Each question-answer exchange creates one trajectory. Methods return
    ``Adjudicated`` verdicts so callers can enforce Deny/Escalate at each
    point. Exceptions are swallowed so session failures never break the
    AI flow.

    Uses the Trajectory Event Model types (``Event``, ``Prompt``, ``ToolCall``,
    ``ToolOutput``). Each adjudicate method constructs an ``Event`` wrapping a
    typed payload and returns the ``Adjudicated`` verdict.

    Usage::

        session = AskSession()
        await session.start()

        adj = await session.adjudicate_user_prompt("What agents have violations?")
        if adj and adj.decision == Decision.Deny:
            # policy blocked the prompt
            ...

        adj = await session.adjudicate_tool_request("list_agents", {})
        if adj and adj.decision == Decision.Deny:
            # don't execute the tool
            ...

        adj = await session.adjudicate_tool_response("list_agents", {"count": 5})
        adj = await session.adjudicate_model_response("Agent X has 3 denials...")
        await session.finish()
    """

    def __init__(self) -> None:
        self._harness: Harness | None = None
        self._active: bool = False

    @property
    def is_active(self) -> bool:
        return self._active

    async def start(self) -> None:
        """Initialize a new trajectory. No-op if disabled or unconfigured."""
        if not _settings.SETTINGS.ai_harness_enabled:
            return
        if not _settings.SETTINGS.sondera_api_token:
            return
        try:
            self._harness = SonderaRemoteHarness(
                sondera_harness_endpoint=_settings.SETTINGS.sondera_harness_endpoint,
                sondera_api_key=_settings.SETTINGS.sondera_api_token,
            )
            await self._harness.initialize(agent=_AI_AGENT)
            self._active = True
            _log.debug("AI trajectory started: %s", self._harness.trajectory_id)
        except Exception:
            _log.debug("Failed to start AI trajectory", exc_info=True)
            self._harness = None
            self._active = False

    async def _adjudicate(
        self, payload: Prompt | ToolCall | ToolOutput, label: str
    ) -> Adjudicated | None:
        """Build an Event from *payload* and adjudicate it.

        Returns ``None`` if the session is inactive or on any error.
        """
        if not self._active or not self._harness:
            return None
        agent = self._harness.agent
        tid = self._harness.trajectory_id
        if agent is None or tid is None:
            return None
        try:
            event = Event(agent=agent, trajectory_id=tid, event=payload)
            return await self._harness.adjudicate(event)
        except Exception:
            _log.debug("Failed to adjudicate %s", label, exc_info=True)
            return None

    async def adjudicate_user_prompt(self, text: str) -> Adjudicated | None:
        """Record and adjudicate user question."""
        return await self._adjudicate(
            Prompt(content=text, role=PromptRole.User), "user prompt"
        )

    async def adjudicate_model_response(self, text: str) -> Adjudicated | None:
        """Record and adjudicate model response."""
        return await self._adjudicate(
            Prompt(content=text, role=PromptRole.Assistant), "model response"
        )

    async def adjudicate_tool_request(
        self, tool_name: str, args: dict[str, Any]
    ) -> Adjudicated | None:
        """Record and adjudicate tool call."""
        return await self._adjudicate(
            ToolCall(tool=tool_name, arguments=args), f"tool request: {tool_name}"
        )

    async def adjudicate_tool_response(
        self, tool_name: str, result: Any
    ) -> Adjudicated | None:
        """Record and adjudicate tool result."""
        output = result if isinstance(result, str) else json.dumps(result)
        return await self._adjudicate(
            ToolOutput(call_id=tool_name, output=output, success=True),
            f"tool response: {tool_name}",
        )

    async def finish(self) -> None:
        """Finalize the trajectory. Safe to call even if start() failed."""
        if not self._active or not self._harness:
            self._active = False
            return
        try:
            await self._harness.finalize()
            _log.debug("AI trajectory finalized: %s", self._harness.trajectory_id)
        except Exception:
            _log.debug("Failed to finalize AI trajectory", exc_info=True)
        finally:
            self._active = False
            self._harness = None
