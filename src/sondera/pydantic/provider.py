"""SonderaProvider -- top-level orchestrator for Sondera-governed Pydantic AI agents.

This module wires Pydantic AI agents to the Sondera governance harness using
the native pydantic-ai Hooks API (``pydantic_ai.capabilities.Hooks``). Four
hook points are registered on the agent:

* ``run`` -- harness lifecycle (initialize / finalize / fail).
* ``before_model_request`` -- pre-prompt adjudication; raises
  ``SkipModelRequest`` with a synthetic denial response on Deny+Govern.
* ``after_model_request`` -- post-response adjudication; substitutes a denial
  response on Deny+Govern. Does **not** fire for streamed runs.
* ``tool_execute`` -- per-tool adjudication, escalation, and post-tool
  redaction.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic_ai.agent import AgentRunResult
from pydantic_ai.capabilities import CapabilityOrdering, CombinedCapability, Hooks
from pydantic_ai.exceptions import (
    ApprovalRequired,
    ModelRetry,
    SkipModelRequest,
    SkipToolExecution,
)
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.tools import (
    DeferredToolRequests,
    DeferredToolResults,
    ToolApproved,
    ToolDenied,
)

from pydantic_ai import Agent as PydanticAgent
from sondera._serde import to_json_str
from sondera.exceptions import AuthenticationError
from sondera.harness import Harness
from sondera.pydantic.analyze import build_agent_card
from sondera.types import (
    Agent,
    Decision,
    Event,
    HarnessErrorPolicy,
    Mode,
    Prompt,
    PromptRole,
    Strategy,
    ToolCall,
    ToolOutput,
)

logger = logging.getLogger(__name__)

_POST_TOOL_REDACTED = (
    "Tool output was redacted by policy. The tool executed but its output "
    "cannot be shown. Do not retry this tool call."
)


class SonderaProvider:
    """Top-level provider that wires Pydantic AI agents to Sondera governance.

    The default strategy is ``BLOCK``, which ensures policy denials halt tool
    execution immediately. Use ``STEER`` if you want the model to receive a
    ``ModelRetry`` hint and self-correct instead.

    Example::

        from pydantic_ai import Agent
        from sondera.harness import SonderaRemoteHarness
        from sondera.pydantic import SonderaProvider, Strategy

        provider = SonderaProvider(strategy=Strategy.BLOCK)
        agent = Agent("openai:gpt-4o", tools=[...])

        card = provider.build_agent_card(agent, agent_id="my-agent")
        harness = SonderaRemoteHarness()

        provider.govern(agent, harness=harness, agent_card=card)
        result = await agent.run("Hello!")

    Streaming limitation:
        Streamed runs (``agent.run_stream``) receive pre-prompt and per-tool
        adjudication, but ``after_model_request`` is **not** invoked on
        streamed responses. If your policy requires response-side checks,
        use ``agent.run`` instead.
    """

    def __init__(
        self,
        *,
        strategy: Strategy = Strategy.BLOCK,
        harness_error_policy: HarnessErrorPolicy = HarnessErrorPolicy.FAIL_CLOSED,
        enable_escalation: bool = False,
        include_tool_args_in_escalation: bool = False,
        session_id: str | None = None,
    ) -> None:
        self._strategy = strategy
        self._harness_error_policy = harness_error_policy
        self._enable_escalation = enable_escalation
        self._include_tool_args_in_escalation = include_tool_args_in_escalation
        self._session_id = session_id

    def build_agent_card(
        self,
        agent: PydanticAgent[Any],
        agent_id: str,
        name: str | None = None,
    ) -> Agent:
        """Build a Sondera Agent card from a Pydantic AI agent."""
        return build_agent_card(agent, agent_id, name=name)

    def govern(
        self,
        agent: PydanticAgent[Any],
        *,
        harness: Harness,
        agent_card: Agent,
        session_id: str | None = None,
        acknowledge_fail_open: bool = False,
    ) -> None:
        """Mutate a Pydantic AI agent to add Sondera governance.

        Builds a ``Hooks`` capability with four hook registrations
        (``run``, ``before_model_request``, ``after_model_request``,
        ``tool_execute``) and composes it with the agent's existing root
        capability via ``CombinedCapability``.

        Args:
            agent: The Pydantic AI agent to govern.
            harness: The Sondera harness instance.
            agent_card: The Sondera Agent identity card.
            session_id: Optional session identifier. Overrides the
                provider-level ``session_id``.
            acknowledge_fail_open: Must be ``True`` when ``harness_error_policy``
                is ``FAIL_OPEN``. Enforces explicit opt-in for fail-open
                behavior.

        Raises:
            ValueError: If ``acknowledge_fail_open`` is required but not given.
            RuntimeError: If ``govern()`` was already applied to this agent.

        Warning:
            This mutates the agent in place by composing hooks into its root
            capability. The agent object is modified, not copied.

        Note:
            pydantic-ai 1.78+ does not yet expose a public API for attaching
            a capability to an already-constructed ``Agent`` (``capabilities=``
            is a constructor-only argument; ``agent.root_capability`` is a
            read-only property). To preserve the ``govern(agent, ...)``
            contract that was established before the Hooks API existed, this
            method writes ``agent._root_capability`` directly. If pydantic-ai
            adds a public registration API in a later release, switch to it.
        """
        if (
            self._harness_error_policy == HarnessErrorPolicy.FAIL_OPEN
            and not acknowledge_fail_open
        ):
            raise ValueError(
                "HarnessErrorPolicy.FAIL_OPEN requires acknowledge_fail_open=True. "
                "Fail-open mode allows tools to execute without policy adjudication "
                "when the harness is unreachable."
            )

        if getattr(agent, "_sondera_governed", False):
            raise RuntimeError(
                "govern() has already been applied to this agent. Calling it "
                "again would double-register hooks and cause every event to be "
                "adjudicated twice."
            )

        effective_session_id = session_id or self._session_id

        # Closure-bound state shared across the four hook callables.
        approved_calls: set[str] = set()
        strategy = self._strategy
        harness_error_policy = self._harness_error_policy
        enable_escalation = self._enable_escalation
        include_tool_args = self._include_tool_args_in_escalation

        def _handle_harness_error(exc: Exception, *, context: str) -> None:
            """Apply ``harness_error_policy`` to a transport/auth/parse error.

            On FAIL_CLOSED, re-raises as ``RuntimeError``. On FAIL_OPEN, logs
            a warning and returns (caller proceeds without adjudication).
            ``AuthenticationError`` is always fail-closed regardless of policy.
            """
            if isinstance(exc, AuthenticationError):
                raise RuntimeError(
                    f"Harness authentication error ({context}): {exc}"
                ) from exc
            if harness_error_policy == HarnessErrorPolicy.FAIL_CLOSED:
                raise RuntimeError(
                    f"Harness unavailable, fail-closed ({context}): "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
            logger.warning(
                "[SonderaProvider] Harness error (fail-open, %s): %s: %s",
                context,
                type(exc).__name__,
                exc,
            )

        # `position="outermost"` is load-bearing: pydantic-ai's
        # CombinedCapability.__post_init__ runs sort_capabilities() whenever
        # any leaf has explicit ordering metadata, and built-in capabilities
        # like `ToolSearch` already declare themselves outermost. Without an
        # explicit position here, Sondera hooks would land inside the user's
        # existing capabilities -- meaning a short-circuiting wrap (e.g. a
        # response cache that returns without calling its inner handler)
        # could silently bypass adjudication. Pinning Sondera outermost
        # guarantees governance fires first for every prompt, response, and
        # tool call.
        hooks = Hooks(ordering=CapabilityOrdering(position="outermost"))

        @hooks.on.run
        async def _sondera_lifecycle(ctx: Any, *, handler: Any) -> AgentRunResult[Any]:
            await harness.initialize(agent=agent_card, session_id=effective_session_id)
            try:
                result = await handler()
                await harness.finalize()
                return result
            except Exception as exc:
                try:
                    await harness.fail(reason=str(exc))
                except Exception:
                    logger.debug(
                        "Harness fail() error during cleanup (suppressed)",
                        exc_info=True,
                    )
                raise

        @hooks.on.before_model_request
        async def _sondera_pre_model(ctx: Any, request_context: Any) -> Any:
            if harness.agent is None or harness.trajectory_id is None:
                return request_context

            user_text = _extract_last_user_text(request_context.messages)
            if not user_text:
                return request_context

            pre_event = Event(
                agent=harness.agent,
                trajectory_id=harness.trajectory_id,
                event=Prompt(role=PromptRole.USER, content=user_text),
            )
            try:
                pre_adj = await harness.adjudicate(pre_event)
            except Exception as exc:
                _handle_harness_error(exc, context="pre-model")
                return request_context

            if pre_adj.decision == Decision.DENY:
                reason = pre_adj.reason or "Request denied by policy"
                if pre_adj.mode == Mode.GOVERN:
                    logger.warning(
                        "[SonderaProvider] Pre-model deny (Govern): %s", reason
                    )
                    raise SkipModelRequest(_denial_response(reason))
                logger.info(
                    "[SonderaProvider] Pre-model deny (mode=%s) -- allowing",
                    pre_adj.mode,
                )
            return request_context

        @hooks.on.after_model_request
        async def _sondera_post_model(
            ctx: Any, request_context: Any, response: ModelResponse
        ) -> ModelResponse:
            if harness.agent is None or harness.trajectory_id is None:
                return response

            response_text = _extract_response_text(response)
            if not response_text:
                return response

            post_event = Event(
                agent=harness.agent,
                trajectory_id=harness.trajectory_id,
                event=Prompt(role=PromptRole.ASSISTANT, content=response_text),
            )
            try:
                post_adj = await harness.adjudicate(post_event)
            except Exception as exc:
                _handle_harness_error(exc, context="post-model")
                return response

            if post_adj.decision == Decision.DENY:
                reason = post_adj.reason or "Response denied by policy"
                if post_adj.mode == Mode.GOVERN:
                    logger.warning(
                        "[SonderaProvider] Post-model deny (Govern): %s", reason
                    )
                    return _denial_response(reason)
                logger.info(
                    "[SonderaProvider] Post-model deny (mode=%s) -- allowing",
                    post_adj.mode,
                )
            return response

        @hooks.on.tool_execute
        async def _sondera_tool(
            ctx: Any,
            *,
            call: Any,
            tool_def: Any,
            args: dict[str, Any],
            handler: Callable[[dict[str, Any]], Awaitable[Any]],
        ) -> Any:
            tool_name = call.tool_name
            call_id = call.tool_call_id

            if harness.agent is None or harness.trajectory_id is None:
                return await handler(args)

            # --- PRE-TOOL adjudication ---
            pre_event = _tool_call_event(
                agent=harness.agent,
                trajectory_id=harness.trajectory_id,
                tool_name=tool_name,
                tool_args=args,
                call_id=call_id,
            )
            try:
                pre_adj = await harness.adjudicate(pre_event)
            except Exception as exc:
                _handle_harness_error(exc, context=f"pre-tool {tool_name}")
                return await handler(args)

            if pre_adj.decision == Decision.DENY:
                reason = pre_adj.deny_message(f"Tool '{tool_name}' denied by policy")
                logger.warning(
                    "[SonderaProvider] Tool '%s' denied (mode=%s, strategy=%s): %s",
                    tool_name,
                    pre_adj.mode,
                    strategy,
                    reason,
                )
                if pre_adj.mode == Mode.GOVERN:
                    if strategy == Strategy.BLOCK:
                        raise SkipToolExecution("Tool call denied by policy.")
                    raise ModelRetry("Policy requires a different approach.")

            if pre_adj.decision == Decision.ESCALATE:
                escalate_reason = (
                    pre_adj.reason or f"Tool '{tool_name}' requires approval"
                )
                logger.info(
                    "[SonderaProvider] Tool '%s' escalated (call_id=%s): %s",
                    tool_name,
                    call_id,
                    escalate_reason,
                )
                # Dedupe by tool_call_id (issued by pydantic-ai per call) so
                # two distinct invocations of the same tool with identical args
                # each get their own approval round.
                if call_id in approved_calls:
                    approved_calls.discard(call_id)
                    logger.info(
                        "[SonderaProvider] Tool '%s' (call_id=%s) already approved",
                        tool_name,
                        call_id,
                    )
                elif enable_escalation:
                    approved_calls.add(call_id)
                    metadata: dict[str, Any] = {
                        "sondera_call_id": call_id,
                        "tool_name": tool_name,
                        "reason": escalate_reason,
                    }
                    if include_tool_args:
                        metadata["tool_args"] = args
                    else:
                        metadata["tool_args"] = (
                            "<redacted -- set include_tool_args_in_escalation=True>"
                        )
                    raise ApprovalRequired(metadata=metadata)
                else:
                    raise RuntimeError(
                        f"Tool '{tool_name}' requires approval but escalation "
                        f"is not enabled. Set enable_escalation=True on "
                        f"SonderaProvider to handle escalations."
                    )

            # --- Execute the wrapped tool ---
            result = await handler(args)

            # --- POST-TOOL adjudication ---
            try:
                output_str = to_json_str(result)
            except (TypeError, ValueError):
                output_str = str(result)

            post_event = _tool_result_event(
                agent=harness.agent,
                trajectory_id=harness.trajectory_id,
                call_id=call_id,
                output=output_str,
            )
            try:
                post_adj = await harness.adjudicate(post_event)
            except Exception as exc:
                _handle_harness_error(exc, context=f"post-tool {tool_name}")
                return result

            if post_adj.decision == Decision.DENY:
                reason = post_adj.deny_message(
                    f"Tool '{tool_name}' output denied by policy"
                )
                logger.warning(
                    "[SonderaProvider] Tool '%s' output denied (mode=%s): %s",
                    tool_name,
                    post_adj.mode,
                    reason,
                )
                if post_adj.mode == Mode.GOVERN:
                    return _POST_TOOL_REDACTED

            return result

        # Compose the new Hooks capability with the agent's existing root
        # capability so the user's own toolsets, tools, and instructions are
        # preserved alongside Sondera adjudication.
        #
        # Sondera hooks must be OUTERMOST. CombinedCapability builds wrap
        # chains via `reversed(self.capabilities)` (see pydantic_ai.capabilities
        # CombinedCapability.wrap_run / wrap_model_request / wrap_tool_execute),
        # so the first item in the list is the outermost wrapper. If any
        # pre-existing capability short-circuits without invoking its inner
        # handler -- e.g. a response cache or a tool-skip optimisation -- we
        # still need adjudication to fire first. Putting the user's existing
        # capability before Sondera would let it bypass governance.
        existing = agent._root_capability  # noqa: SLF001
        agent._root_capability = CombinedCapability(  # noqa: SLF001
            capabilities=[hooks, existing]
        )
        agent._sondera_governed = True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_last_user_text(messages: list[ModelMessage]) -> str:
    """Extract the text content of the last user prompt from a message list."""
    for msg in reversed(messages):
        if not isinstance(msg, ModelRequest):
            continue
        for part in reversed(msg.parts):
            if isinstance(part, UserPromptPart):
                content = part.content
                if isinstance(content, str):
                    return content
                texts: list[str] = [item for item in content if isinstance(item, str)]
                return " ".join(texts) if texts else ""
    return ""


def _extract_response_text(response: ModelResponse) -> str:
    """Extract concatenated text from a ``ModelResponse``."""
    return " ".join(p.content for p in response.parts if isinstance(p, TextPart))


def _denial_response(reason: str) -> ModelResponse:
    """Build a ``ModelResponse`` containing only a denial text part."""
    return ModelResponse(parts=[TextPart(content=reason)])


def _tool_call_event(
    *,
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
    *,
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
# run_with_approval -- convenience for the DeferredToolRequests loop
# ---------------------------------------------------------------------------

ReviewerFn = Callable[
    [list[Any]],
    Awaitable[dict[str, ToolApproved | ToolDenied]],
]


async def run_with_approval(
    agent: PydanticAgent[Any],
    prompt: str,
    *,
    reviewer: ReviewerFn,
    max_rounds: int = 10,
    **kwargs: Any,
) -> AgentRunResult[Any]:
    """Run a governed agent with automatic escalation handling.

    When the agent encounters tools that require approval (Escalate verdict),
    the ``reviewer`` callback is called with the list of tool calls needing
    approval. The callback should return a dict mapping tool_call_id to
    ``ToolApproved()`` or ``ToolDenied(message)``.

    Args:
        agent: A governed Pydantic AI agent (must have ``govern()`` applied
            with ``enable_escalation=True``).
        prompt: The initial user prompt.
        reviewer: Async callback that receives escalated tool calls and
            returns approval decisions.
        max_rounds: Maximum number of escalation rounds before raising.
        **kwargs: Additional keyword arguments forwarded to ``agent.run()``.

    Returns:
        The final ``AgentRunResult`` after all escalations are resolved.
    """
    caller_output_type = kwargs.pop("output_type", None)
    base_type = (
        caller_output_type if caller_output_type is not None else agent.output_type
    )
    effective_output_type = [base_type, DeferredToolRequests]

    result = await agent.run(
        prompt,
        output_type=effective_output_type,  # type: ignore[arg-type]
        **kwargs,
    )

    for _round in range(max_rounds):
        if not isinstance(result.output, DeferredToolRequests):
            return result
        if not result.output.approvals:
            return result

        decisions = await reviewer(result.output.approvals)

        result = await agent.run(
            None,  # type: ignore[arg-type]
            output_type=effective_output_type,  # type: ignore[arg-type]
            deferred_tool_results=DeferredToolResults(approvals=decisions),
            message_history=result.all_messages(),
            **kwargs,
        )

    if isinstance(result.output, DeferredToolRequests):
        raise RuntimeError(
            f"Escalation loop exceeded {max_rounds} rounds without resolution."
        )

    return result
