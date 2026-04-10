"""Governed toolset that wraps Pydantic AI tools with Sondera policy enforcement."""

from __future__ import annotations

import json
import logging
import uuid
from enum import StrEnum
from typing import Any

from pydantic_ai.exceptions import ModelRetry, SkipToolExecution
from pydantic_ai.toolsets import WrapperToolset
from pydantic_ai.toolsets.abstract import AbstractToolset, ToolsetTool

from sondera.harness import Harness
from sondera.types import (
    Agent,
    Decision,
    Event,
    Mode,
    ToolCall,
    ToolOutput,
)

logger = logging.getLogger(__name__)


class Strategy(StrEnum):
    """Strategy for handling policy violations on tool calls.

    Note:
        ``Strategy`` is only applied when the server-side ``Mode`` is
        ``Mode.Govern``.  Deny verdicts returned in ``Mode.Monitor`` or
        ``Mode.Steer`` are treated as *observe-only* and the request is
        allowed through regardless of this setting.
    """

    BLOCK = "block"
    """Skip tool execution and return a generic denial message to the model."""
    STEER = "steer"
    """Raise ModelRetry so the model can self-correct."""


class HarnessErrorPolicy(StrEnum):
    """How to handle errors when the harness is unreachable or returns invalid responses."""

    FAIL_CLOSED = "fail_closed"
    """Default. Raise RuntimeError -- the agent stops."""
    FAIL_OPEN = "fail_open"
    """Log a warning and allow the tool to execute without adjudication."""


# ---------------------------------------------------------------------------
# Event builder helpers (inlined from deleted content.py)
# ---------------------------------------------------------------------------


def _tool_call_event(
    agent: Agent,
    trajectory_id: str,
    tool_name: str,
    tool_args: dict[str, Any],
    call_id: str,
) -> Event:
    args_str = json.dumps(tool_args) if isinstance(tool_args, dict) else str(tool_args)
    return Event(
        agent=agent,
        trajectory_id=trajectory_id,
        event=ToolCall(tool=tool_name, arguments=args_str, call_id=call_id),
    )


def _tool_result_event(
    agent: Agent,
    trajectory_id: str,
    call_id: str,
    output: str,
) -> Event:
    return Event(
        agent=agent,
        trajectory_id=trajectory_id,
        event=ToolOutput.from_success(call_id, output),
    )


# ---------------------------------------------------------------------------
# Governed toolset
# ---------------------------------------------------------------------------

_POST_TOOL_REDACTED = (
    "Tool output was redacted by policy. The tool executed but its output "
    "cannot be shown. Do not retry this tool call."
)


class SonderaGovernedToolset(WrapperToolset):  # type: ignore[type-arg]
    """A toolset wrapper that adjudicates each tool call through the Sondera Harness.

    Before executing a tool, the harness is consulted. Depending on the
    adjudication result and the configured strategy, the call is either allowed,
    blocked (``SkipToolExecution``), or steered (``ModelRetry``).

    Mode precedence:
        The server-side ``Mode`` attached to each ``Adjudicated`` verdict takes
        precedence over the local ``Strategy`` setting.  Only verdicts with
        ``mode == Mode.Govern`` are enforced; ``Mode.Monitor`` and ``Mode.Steer``
        verdicts are logged but do **not** block or modify execution.
    """

    wrapped: AbstractToolset[Any]

    def __init__(
        self,
        wrapped: AbstractToolset[Any],
        *,
        harness: Harness,
        strategy: Strategy = Strategy.BLOCK,
        harness_error_policy: HarnessErrorPolicy = HarnessErrorPolicy.FAIL_CLOSED,
        enable_escalation: bool = False,
        include_tool_args_in_escalation: bool = False,
    ) -> None:
        super().__init__(wrapped=wrapped)
        self._harness = harness
        self._strategy = strategy
        self._harness_error_policy = harness_error_policy
        self._enable_escalation = enable_escalation
        self._include_tool_args_in_escalation = include_tool_args_in_escalation
        self._approved_calls: set[str] = set()

    @property
    def id(self) -> str | None:
        wrapped_id = getattr(self.wrapped, "id", None) or "default"
        return f"sondera-governed-{wrapped_id}"

    def _handle_harness_error(self, exc: Exception, *, context: str) -> None:
        """Handle a harness communication error according to policy.

        For FAIL_CLOSED: re-raises as RuntimeError.
        For FAIL_OPEN: logs a warning and returns (caller should proceed).
        Auth errors are always fail-closed regardless of policy.
        """
        from sondera.exceptions import AuthenticationError

        if isinstance(exc, AuthenticationError):
            raise RuntimeError(
                f"Harness authentication error ({context}): {exc}"
            ) from exc

        if self._harness_error_policy == HarnessErrorPolicy.FAIL_CLOSED:
            raise RuntimeError(
                f"Harness unavailable, fail-closed ({context}): {type(exc).__name__}: {exc}"
            ) from exc

        logger.warning(
            "[SonderaGovernedToolset] Harness error (fail-open, %s): %s: %s",
            context,
            type(exc).__name__,
            exc,
        )

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: Any,
        tool: ToolsetTool[Any],
    ) -> Any:
        """Adjudicate the tool call, then delegate to the wrapped toolset."""
        agent = self._harness.agent
        trajectory_id = self._harness.trajectory_id
        if agent is None or trajectory_id is None:
            return await self.wrapped.call_tool(name, tool_args, ctx, tool)

        call_id = f"{name}-{uuid.uuid4().hex[:12]}"

        # --- PRE-TOOL adjudication ---
        event = _tool_call_event(
            agent=agent,
            trajectory_id=trajectory_id,
            tool_name=name,
            tool_args=tool_args,
            call_id=call_id,
        )

        try:
            adjudicated = await self._harness.adjudicate(event)
        except Exception as exc:
            self._handle_harness_error(exc, context=f"pre-tool {name}")
            # If we reach here, policy is FAIL_OPEN -- proceed without adjudication
            return await self.wrapped.call_tool(name, tool_args, ctx, tool)

        if adjudicated.decision == Decision.Deny:
            reason = adjudicated.deny_message(f"Tool '{name}' denied by policy")
            logger.warning(
                "[SonderaGovernedToolset] Tool '%s' denied (mode=%s, strategy=%s): %s",
                name,
                adjudicated.mode,
                self._strategy.value,
                reason,
            )
            if adjudicated.mode == Mode.Govern:
                if self._strategy == Strategy.BLOCK:
                    raise SkipToolExecution("Tool call denied by policy.")
                raise ModelRetry("Policy requires a different approach.")

        if adjudicated.decision == Decision.Escalate:
            escalate_reason = adjudicated.reason or f"Tool '{name}' requires approval"
            logger.info(
                "[SonderaGovernedToolset] Tool '%s' escalated: %s",
                name,
                escalate_reason,
            )
            # Check if this tool call was already approved in a prior round.
            # Pydantic AI re-invokes call_tool for approved deferred calls,
            # but the harness doesn't track client-side approvals and will
            # return Escalate again — skip re-escalation to avoid looping.
            approval_key = f"{name}:{json.dumps(tool_args, sort_keys=True)}"
            if approval_key in self._approved_calls:
                self._approved_calls.discard(approval_key)
                logger.info(
                    "[SonderaGovernedToolset] Tool '%s' already approved, proceeding",
                    name,
                )
            elif self._enable_escalation:
                from pydantic_ai.exceptions import ApprovalRequired

                # Record so the re-invocation after approval skips escalation
                self._approved_calls.add(approval_key)

                metadata: dict[str, Any] = {
                    "sondera_call_id": call_id,
                    "tool_name": name,
                    "reason": escalate_reason,
                }
                if self._include_tool_args_in_escalation:
                    metadata["tool_args"] = tool_args
                else:
                    metadata["tool_args"] = (
                        "<redacted -- set include_tool_args_in_escalation=True>"
                    )
                raise ApprovalRequired(metadata=metadata)
            else:
                raise RuntimeError(
                    f"Tool '{name}' requires approval but escalation is not enabled. "
                    f"Set enable_escalation=True on SonderaProvider to handle escalations."
                )

        # --- Execute the actual tool ---
        result = await self.wrapped.call_tool(name, tool_args, ctx, tool)

        # --- POST-TOOL adjudication ---
        if isinstance(result, str):
            output_str = result
        else:
            try:
                output_str = json.dumps(result)
            except (TypeError, ValueError):
                output_str = str(result)

        post_event = _tool_result_event(
            agent=agent,
            trajectory_id=trajectory_id,
            call_id=call_id,
            output=output_str,
        )

        try:
            post_adjudicated = await self._harness.adjudicate(post_event)
        except Exception as exc:
            self._handle_harness_error(exc, context=f"post-tool {name}")
            return result

        if post_adjudicated.decision == Decision.Deny:
            reason = post_adjudicated.deny_message(
                f"Tool '{name}' output denied by policy"
            )
            logger.warning(
                "[SonderaGovernedToolset] Tool '%s' output denied (mode=%s): %s",
                name,
                post_adjudicated.mode,
                reason,
            )
            if post_adjudicated.mode == Mode.Govern:
                return _POST_TOOL_REDACTED

        return result
