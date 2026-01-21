"""Sondera Harness Hook for Strands Agent SDK integration."""

import logging
from typing import Any

from strands.hooks import HookProvider, HookRegistry
from strands.hooks.events import (
    AfterInvocationEvent,
    AfterModelCallEvent,
    AfterToolCallEvent,
    BeforeInvocationEvent,
    BeforeModelCallEvent,
    BeforeToolCallEvent,
)

from sondera.harness import Harness
from sondera.strands.analyze import format_strands_agent
from sondera.types import (
    PromptContent,
    Role,
    Stage,
    ToolRequestContent,
    ToolResponseContent,
)

logger = logging.getLogger(__name__)


class SonderaHarnessHook(HookProvider):
    """Sondera Harness Hook for Strands integration.

    This hook implements the HookProvider protocol to integrate with
    Strands' hook system. It uses dependency injection for the Harness
    instance, allowing flexibility in choosing RemoteHarness or LocalHarness.

    The hook intercepts agent execution at key lifecycle points:
    - Before/after invocation: Initialize and finalize trajectory
    - Before/after model call: Evaluate model requests and responses
    - Before/after tool call: Evaluate tool calls and results

    Example:
        ```python
        from strands import Agent
        from sondera.strands import SonderaHarnessHook
        from sondera.harness import RemoteHarness

        # Create harness instance
        harness = RemoteHarness(
            sondera_harness_endpoint="localhost:50051",
            sondera_api_key="<YOUR_SONDERA_API_KEY>",
        )

        # Create hook with harness using dependency injection
        hook = SonderaHarnessHook(harness=harness)

        # Create Strands agent with hooks
        agent = Agent(
            system_prompt="You are a helpful assistant",
            model="anthropic.claude-3-5-sonnet-20241022-v2:0",
            hooks=[hook],
        )

        # Run agent (hooks will fire automatically)
        response = agent("What is 5 + 3?")
        ```

    Hook Lifecycle:
        1. BeforeInvocationEvent - Initialize trajectory
        2. BeforeModelCallEvent - Pre-model guardrails
        3. AfterModelCallEvent - Post-model guardrails
        4. BeforeToolCallEvent - Pre-tool guardrails (can cancel with event.cancel_tool)
        5. AfterToolCallEvent - Post-tool guardrails (can modify event.result)
        6. AfterInvocationEvent - Finalize trajectory
    """

    def __init__(
        self,
        harness: Harness,
        *,
        logger_instance: logging.Logger | None = None,
    ):
        """Initialize the Strands Harness Hook.

        Args:
            harness: The Sondera Harness instance to use for policy enforcement.
                     Can be RemoteHarness for production or LocalHarness for testing.
            logger_instance: Optional custom logger instance.
        """
        self._harness = harness
        self._log = logger_instance or logger
        self._strands_agent: Any | None = None

    # -------------------------------------------------------------------------
    # HookProvider interface - required by Strands
    # -------------------------------------------------------------------------

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register all Strands lifecycle hooks.

        This method is called by Strands when the agent is constructed with
        hooks=[SonderaHarnessHook(harness=...)].

        Args:
            registry: The Strands hook registry
            **kwargs: Additional keyword arguments (unused)
        """
        registry.add_callback(BeforeInvocationEvent, self._on_before_invocation)
        registry.add_callback(AfterInvocationEvent, self._on_after_invocation)
        registry.add_callback(BeforeModelCallEvent, self._on_before_model_call)
        registry.add_callback(AfterModelCallEvent, self._on_after_model_call)
        registry.add_callback(BeforeToolCallEvent, self._on_before_tool_call)
        registry.add_callback(AfterToolCallEvent, self._on_after_tool_call)

        self._log.info("[SonderaHarness] Registered Strands hooks")

    # -------------------------------------------------------------------------
    # Invocation Callbacks
    # -------------------------------------------------------------------------

    async def _on_before_invocation(self, event: BeforeInvocationEvent) -> None:
        """Callback for BeforeInvocationEvent - Initialize trajectory."""
        try:
            self._strands_agent = event.agent
            agent = format_strands_agent(event.agent)
            await self._harness.initialize(agent=agent)
            self._log.debug(
                f"[SonderaHarness] Initialized trajectory {self._harness.trajectory_id}"
            )
        except Exception as e:
            self._log.error(
                f"[SonderaHarness] Error in before_invocation: {e}", exc_info=True
            )

    async def _on_after_invocation(self, event: AfterInvocationEvent) -> None:
        """Callback for AfterInvocationEvent - Finalize trajectory."""
        try:
            trajectory_id = self._harness.trajectory_id
            await self._harness.finalize()
            self._log.info(f"[SonderaHarness] Finalized trajectory {trajectory_id}")
        except Exception as e:
            self._log.error(
                f"[SonderaHarness] Error in after_invocation: {e}", exc_info=True
            )

    # -------------------------------------------------------------------------
    # Model Callbacks
    # -------------------------------------------------------------------------

    async def _on_before_model_call(self, event: BeforeModelCallEvent) -> None:
        """Callback for BeforeModelCallEvent - Pre-model guardrails."""
        try:
            if not self._harness.trajectory_id:
                self._log.warning(
                    "[SonderaHarness] No active trajectory for before_model_call"
                )
                return

            content = self._extract_text_from_event(event)
            adjudication = await self._harness.adjudicate(
                Stage.PRE_MODEL, Role.MODEL, PromptContent(text=content)
            )
            self._log.info(
                f"[SonderaHarness] Before model adjudication for trajectory {self._harness.trajectory_id}"
            )

            if adjudication.is_denied:
                self._log.warning(
                    f"[SonderaHarness] Model call blocked: {adjudication.reason}"
                )
        except Exception as e:
            self._log.error(
                f"[SonderaHarness] Error in before_model_call: {e}", exc_info=True
            )

    async def _on_after_model_call(self, event: AfterModelCallEvent) -> None:
        """Callback for AfterModelCallEvent - Post-model guardrails."""
        try:
            if not self._harness.trajectory_id:
                self._log.warning(
                    "[SonderaHarness] No active trajectory for after_model_call"
                )
                return

            content = self._extract_text_from_event(event)
            if not content:
                return

            adjudication = await self._harness.adjudicate(
                Stage.POST_MODEL, Role.MODEL, PromptContent(text=content)
            )
            self._log.info(
                f"[SonderaHarness] After model adjudication for trajectory {self._harness.trajectory_id}"
            )

            if adjudication.is_denied:
                self._log.warning(
                    f"[SonderaHarness] Model response blocked: {adjudication.reason}"
                )
        except Exception as e:
            self._log.error(
                f"[SonderaHarness] Error in after_model_call: {e}", exc_info=True
            )

    # -------------------------------------------------------------------------
    # Tool Callbacks
    # -------------------------------------------------------------------------

    async def _on_before_tool_call(self, event: BeforeToolCallEvent) -> None:
        """Callback for BeforeToolCallEvent - Pre-tool guardrails."""
        try:
            if not self._harness.trajectory_id:
                self._log.warning(
                    "[SonderaHarness] No active trajectory for before_tool_call"
                )
                return

            tool_name = event.tool_use.get("name", "unknown")
            tool_input = event.tool_use.get("input", {})

            adjudication = await self._harness.adjudicate(
                Stage.PRE_TOOL,
                Role.TOOL,
                ToolRequestContent(
                    tool_id=tool_name,
                    args=tool_input
                    if isinstance(tool_input, dict)
                    else {"input": tool_input},
                ),
            )
            self._log.info(
                f"[SonderaHarness] Before tool adjudication for trajectory {self._harness.trajectory_id}"
            )

            if adjudication.is_denied:
                # Cancel the tool call using Strands' cancel_tool mechanism
                event.cancel_tool = f"Tool blocked by policy: {adjudication.reason}"
                self._log.warning(
                    f"[SonderaHarness] Blocked tool '{tool_name}': {adjudication.reason}"
                )
        except Exception as e:
            self._log.error(
                f"[SonderaHarness] Error in before_tool_call: {e}", exc_info=True
            )

    async def _on_after_tool_call(self, event: AfterToolCallEvent) -> None:
        """Callback for AfterToolCallEvent - Post-tool guardrails."""
        try:
            if not self._harness.trajectory_id:
                self._log.warning(
                    "[SonderaHarness] No active trajectory for after_tool_call"
                )
                return

            tool_name = event.tool_use.get("name", "unknown")

            adjudication = await self._harness.adjudicate(
                Stage.POST_TOOL,
                Role.TOOL,
                ToolResponseContent(tool_id=tool_name, response=event.result),
            )
            self._log.info(
                f"[SonderaHarness] After tool adjudication for trajectory {self._harness.trajectory_id}"
            )

            if adjudication.is_denied:
                # Modify the result to indicate policy violation
                event.result = {
                    "content": [
                        {"text": f"Tool result blocked: {adjudication.reason}"}
                    ],
                    "status": "error",
                    "toolUseId": event.tool_use.get("toolUseId", ""),
                }
                self._log.warning(
                    f"[SonderaHarness] Tool result blocked: {adjudication.reason}"
                )
        except Exception as e:
            self._log.error(
                f"[SonderaHarness] Error in after_tool_call: {e}", exc_info=True
            )

    # -------------------------------------------------------------------------
    # Helper methods
    # -------------------------------------------------------------------------

    def _extract_text_from_event(self, event: Any) -> str:
        """Extract text content from Strands events for adjudication.

        Args:
            event: The Strands hook event

        Returns:
            Extracted text content for adjudication
        """
        if isinstance(event, BeforeModelCallEvent):
            try:
                if (
                    hasattr(event.agent, "conversation_manager")
                    and event.agent.conversation_manager
                ):
                    messages = []
                    conv_mgr = event.agent.conversation_manager
                    messages_attr = getattr(conv_mgr, "messages", None)
                    if messages_attr:
                        for msg in messages_attr:
                            role = (
                                msg.get("role", "unknown")
                                if hasattr(msg, "get")
                                else getattr(msg, "role", "unknown")
                            )
                            content = (
                                msg.get("content", "")
                                if hasattr(msg, "get")
                                else getattr(msg, "content", "")
                            )
                            messages.append(f"{role}: {content}")
                    if messages:
                        return "\n".join(messages)
            except (AttributeError, TypeError) as e:
                self._log.debug(f"Could not extract conversation: {e}")
            return ""

        if isinstance(event, AfterModelCallEvent):
            if event.stop_response and event.stop_response.message:
                content = (
                    event.stop_response.message.get("content", "")
                    if hasattr(event.stop_response.message, "get")
                    else getattr(event.stop_response.message, "content", "")
                )
                return str(content)
            return ""

        return ""
