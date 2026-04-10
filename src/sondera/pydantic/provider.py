"""SonderaProvider -- top-level orchestrator for Sondera-governed Pydantic AI agents."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic_ai.agent import AgentRunResult
from pydantic_ai.tools import (
    DeferredToolRequests,
    DeferredToolResults,
    ToolApproved,
    ToolDenied,
)

from pydantic_ai import Agent as PydanticAgent
from sondera.harness import Harness
from sondera.pydantic.analyze import build_agent_card
from sondera.pydantic.toolset import (
    HarnessErrorPolicy,
    SonderaGovernedToolset,
    Strategy,
)
from sondera.types import Agent

logger = logging.getLogger(__name__)


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

        Registers a ``wrap_run`` hook for harness lifecycle management and
        wraps the agent's toolsets with ``SonderaGovernedToolset`` for
        per-tool policy adjudication.

        Args:
            agent: The Pydantic AI agent to govern.
            harness: The Sondera harness instance.
            agent_card: The Sondera Agent identity card.
            session_id: Optional session identifier. Overrides the provider-level
                ``session_id``.
            acknowledge_fail_open: Must be ``True`` when ``harness_error_policy``
                is ``FAIL_OPEN``. Enforces explicit opt-in for fail-open behavior.

        Warning:
            This mutates the agent in place by registering hooks and wrapping
            toolsets. The agent object is modified, not copied.
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

        effective_session_id = session_id or self._session_id

        @agent.hooks.wrap_run  # type: ignore[misc]
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

        governed_toolsets = [
            SonderaGovernedToolset(
                ts,
                harness=harness,
                strategy=self._strategy,
                harness_error_policy=self._harness_error_policy,
                enable_escalation=self._enable_escalation,
                include_tool_args_in_escalation=self._include_tool_args_in_escalation,
            )
            for ts in agent.toolsets
        ]
        agent.toolsets = governed_toolsets  # type: ignore[assignment]


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
        reviewer: Async callback that receives escalated tool calls and returns
            approval decisions.
        max_rounds: Maximum number of escalation rounds before raising.
        **kwargs: Additional keyword arguments forwarded to ``agent.run()``.

    Returns:
        The final ``AgentRunResult`` after all escalations are resolved.
    """
    # Preserve the agent's configured output type and union it with
    # DeferredToolRequests so escalations work without discarding
    # structured output types (e.g., Pydantic models).
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
