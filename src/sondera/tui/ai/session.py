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
from sondera import (
    Adjudication,
    Agent,
    PromptContent,
    Role,
    Stage,
    ToolRequestContent,
    ToolResponseContent,
)
from sondera.harness import Harness, SonderaRemoteHarness
from sondera.tui.ai.tools import get_sdk_tools

_log = logging.getLogger(__name__)

# Agent definition following the custom integration pattern:
# Agent(id="...", provider_id="...", name="...")
_AI_AGENT = Agent(
    id="sondera-ai-assistant",
    provider_id="sondera-tui",
    name="Sondera AI Assistant",
    description="AI governance analyst embedded in the Sondera TUI",
    instruction=(
        "Answer questions about agent behavior, policy violations, and governance data"
    ),
    tools=get_sdk_tools(),
)


class AskSession:
    """Manages the lifecycle of an AI Assist conversation trajectory.

    Each question-answer exchange creates one trajectory. Methods return
    adjudication decisions so callers can enforce DENY/ESCALATE at each
    stage. Exceptions are swallowed so session failures never break the
    AI flow.

    Stage/Role mapping (from docs.sondera.ai/concepts/stages/):
        PRE_MODEL  / USER  – user prompt input validation
        POST_MODEL / MODEL – model output filtering
        PRE_TOOL   / TOOL  – tool argument validation (block before exec)
        POST_TOOL  / TOOL  – tool result sanitization

    Usage::

        session = AskSession()
        await session.start()

        adj = await session.adjudicate_user_prompt("What agents have violations?")
        if adj and adj.is_denied:
            # policy blocked the prompt
            ...

        adj = await session.adjudicate_tool_request("list_agents", {})
        if adj and adj.is_denied:
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
                sondera_harness_client_secure=_settings.SETTINGS.sondera_harness_client_secure,
            )
            await self._harness.initialize(agent=_AI_AGENT)
            self._active = True
            _log.debug("AI trajectory started: %s", self._harness.trajectory_id)
        except Exception:
            _log.debug("Failed to start AI trajectory", exc_info=True)
            self._harness = None
            self._active = False

    async def adjudicate_user_prompt(self, text: str) -> Adjudication | None:
        """Record and adjudicate user question (PRE_MODEL/USER).

        Returns the adjudication so the caller can block the LLM call on DENY.
        Returns None if recording is disabled or fails.
        """
        if not self._active or not self._harness:
            return None
        try:
            return await self._harness.adjudicate(
                Stage.PRE_MODEL, Role.USER, PromptContent(text=text)
            )
        except Exception:
            _log.debug("Failed to adjudicate user prompt", exc_info=True)
            return None

    async def adjudicate_model_response(self, text: str) -> Adjudication | None:
        """Record and adjudicate model response (POST_MODEL/MODEL).

        Returns the adjudication so the caller can redact on DENY.
        Returns None if recording is disabled or fails.
        """
        if not self._active or not self._harness:
            return None
        try:
            return await self._harness.adjudicate(
                Stage.POST_MODEL, Role.MODEL, PromptContent(text=text)
            )
        except Exception:
            _log.debug("Failed to adjudicate model response", exc_info=True)
            return None

    async def adjudicate_tool_request(
        self, tool_name: str, args: dict[str, Any]
    ) -> Adjudication | None:
        """Record and adjudicate tool call (PRE_TOOL/TOOL).

        Returns the adjudication so the caller can skip execution on DENY.
        Returns None if recording is disabled or fails.
        """
        if not self._active or not self._harness:
            return None
        try:
            return await self._harness.adjudicate(
                Stage.PRE_TOOL,
                Role.TOOL,
                ToolRequestContent(tool_id=tool_name, args=args),
            )
        except Exception:
            _log.debug(
                "Failed to adjudicate tool request: %s", tool_name, exc_info=True
            )
            return None

    async def adjudicate_tool_response(
        self, tool_name: str, result: Any
    ) -> Adjudication | None:
        """Record and adjudicate tool result (POST_TOOL/TOOL).

        Returns the adjudication so the caller can sanitize on DENY.
        Returns None if recording is disabled or fails.
        """
        if not self._active or not self._harness:
            return None
        try:
            response = result if isinstance(result, str) else json.dumps(result)
            return await self._harness.adjudicate(
                Stage.POST_TOOL,
                Role.TOOL,
                ToolResponseContent(tool_id=tool_name, response=response),
            )
        except Exception:
            _log.debug(
                "Failed to adjudicate tool response: %s", tool_name, exc_info=True
            )
            return None

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
