"""
Sondera Harness Plugin for Google ADK integration.

This plugin implements the ADK BasePlugin callback patterns for policy enforcement,
guardrails, and security controls across agent workflows using the Sondera Harness.
"""

import logging
from typing import Any, cast

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.llm_agent import LlmAgent
from google.adk.events.event import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types as genai_types

from sondera.adk.analyze import format
from sondera.harness import Harness
from sondera.types import (
    PromptContent,
    Role,
    Stage,
    ToolRequestContent,
    ToolResponseContent,
)

logger = logging.getLogger(__name__)


class SonderaHarnessPlugin(BasePlugin):
    """Sondera Harness Plugin for ADK integration.

    This plugin integrates with the Sondera Harness for policy enforcement,
    guardrails, and governance across ADK agent workflows. It implements
    the ADK BasePlugin interface and uses dependency injection for the
    Harness instance.

    The plugin intercepts agent execution at key points:
    - User message: Initialize trajectory and evaluate user input
    - Before/after model: Evaluate model requests and responses
    - Before/after tool: Evaluate tool calls and results
    - After run: Finalize the trajectory

    Example:
        ```python
        from sondera.adk import SonderaHarnessPlugin
        from sondera.harness import RemoteHarness
        from google.adk import Agent
        from google.adk.runners import Runner

        # Create a harness instance
        harness = RemoteHarness(
            sondera_harness_endpoint="localhost:50051",
            sondera_api_key="<YOUR_SONDERA_API_KEY>",
        )

        # Create the plugin with the harness
        plugin = SonderaHarnessPlugin(harness=harness)

        # Create agent and runner with the plugin
        agent = Agent(name="my-agent", model="gemini-2.5-flash", ...)
        runner = Runner(
            agent=agent,
            app_name="my-app",
            plugins=[plugin],
        )
        ```
    """

    def __init__(
        self,
        harness: Harness,
        *,
        logger_instance: logging.Logger | None = None,
    ):
        """Initialize the Sondera Harness Plugin.

        Args:
            harness: The Sondera Harness instance to use for policy enforcement.
                     Can be RemoteHarness for production or LocalHarness for testing.
            logger_instance: Optional custom logger instance.
        """
        super().__init__(name="sondera_harness")
        self._harness = harness
        self._log = logger_instance or logger

    # -------------------------------------------------------------------------
    # User Message Callback
    # -------------------------------------------------------------------------

    async def on_user_message_callback(
        self,
        *,
        invocation_context: InvocationContext,
        user_message: genai_types.Content,
    ) -> genai_types.Content | None:
        """Callback executed when a user message is received.

        Initializes the harness trajectory and evaluates the user input
        against policies before the agent processes it.

        Args:
            invocation_context: The context for the entire invocation.
            user_message: The message content input by user.

        Returns:
            Modified content if policy violation, None to proceed normally.
        """
        # Initialize trajectory with agent metadata
        agent = format(
            cast(LlmAgent, invocation_context.agent),
            invocation_context.app_name,
            invocation_context.app_name,
        )
        await self._harness.initialize(agent=agent)

        # Extract text content from user message
        content = None
        if user_message.parts is not None:
            content = user_message.parts[-1].text
        if not content:
            return None

        # Adjudicate user input
        adjudication = await self._harness.adjudicate(
            Stage.PRE_MODEL, Role.USER, PromptContent(text=content)
        )
        self._log.info(
            f"[SonderaHarness] User message adjudication for trajectory {self._harness.trajectory_id}"
        )

        if adjudication.is_denied:
            return genai_types.Content(
                parts=[genai_types.Part(text=adjudication.reason)]
            )
        return None

    # -------------------------------------------------------------------------
    # Agent Callbacks
    # -------------------------------------------------------------------------

    async def before_agent_callback(
        self,
        *,
        agent: BaseAgent,
        callback_context: CallbackContext,
    ) -> genai_types.Content | None:
        """Callback executed before an agent's primary logic is invoked.

        Args:
            agent: The agent that is about to run.
            callback_context: The context for the agent invocation.

        Returns:
            None to allow agent to proceed normally.
        """
        self._log.debug(f"[SonderaHarness] Before agent: {agent.name}")
        return None

    async def after_agent_callback(
        self,
        *,
        agent: BaseAgent,
        callback_context: CallbackContext,
    ) -> genai_types.Content | None:
        """Callback executed after an agent's primary logic has completed.

        Args:
            agent: The agent that has just run.
            callback_context: The context for the agent invocation.

        Returns:
            None to use original agent response.
        """
        self._log.debug(f"[SonderaHarness] After agent: {agent.name}")
        return None

    # -------------------------------------------------------------------------
    # Model Callbacks
    # -------------------------------------------------------------------------

    async def before_model_callback(
        self,
        *,
        callback_context: CallbackContext,
        llm_request: LlmRequest,
    ) -> LlmResponse | None:
        """Callback executed before a request is sent to the model.

        Evaluates the model request against policies.

        Args:
            callback_context: The context for the current agent call.
            llm_request: The prepared request object to be sent to the model.

        Returns:
            LlmResponse if policy violation, None to proceed normally.
        """
        self._log.debug(
            f"[SonderaHarness] Before model call for trajectory {self._harness.trajectory_id}"
        )
        adjudication = await self._harness.adjudicate(
            Stage.PRE_MODEL, Role.MODEL, PromptContent(text="")
        )
        self._log.info(
            f"[SonderaHarness] Before model adjudication for trajectory {self._harness.trajectory_id}"
        )

        if adjudication.is_denied:
            return LlmResponse(
                content=genai_types.Content(
                    parts=[genai_types.Part(text=adjudication.reason)]
                )
            )
        return None

    async def after_model_callback(
        self,
        *,
        callback_context: CallbackContext,
        llm_response: LlmResponse,
    ) -> LlmResponse | None:
        """Callback executed after a response is received from the model.

        Evaluates the model response against policies.

        Args:
            callback_context: The context for the current agent call.
            llm_response: The response object received from the model.

        Returns:
            Modified LlmResponse if policy violation, None to use original.
        """
        self._log.debug("[SonderaHarness] After model call")

        # Extract text content from response
        content = None
        if llm_response.content is not None and llm_response.content.parts is not None:
            content = llm_response.content.parts[-1].text

        if not content:
            return None

        adjudication = await self._harness.adjudicate(
            Stage.POST_MODEL, Role.MODEL, PromptContent(text=content)
        )
        self._log.info(
            f"[SonderaHarness] After model adjudication for trajectory {self._harness.trajectory_id}"
        )

        if adjudication.is_denied:
            return LlmResponse(
                content=genai_types.Content(
                    parts=[genai_types.Part(text=adjudication.reason)]
                )
            )
        return None

    # -------------------------------------------------------------------------
    # Tool Callbacks
    # -------------------------------------------------------------------------

    async def before_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
    ) -> dict[str, Any] | None:
        """Callback executed before a tool is called.

        Evaluates the tool request against policies.

        Args:
            tool: The tool instance that is about to be executed.
            tool_args: The dictionary of arguments for the tool.
            tool_context: The context specific to the tool execution.

        Returns:
            Dict result if policy violation (stops tool), None to proceed.
        """
        self._log.debug(f"[SonderaHarness] Before tool: {tool.name}")

        adjudication = await self._harness.adjudicate(
            Stage.PRE_TOOL,
            Role.TOOL,
            ToolRequestContent(tool_id=tool.name, args=tool_args),
        )
        self._log.info(
            f"[SonderaHarness] Before tool adjudication for trajectory {self._harness.trajectory_id}"
        )

        if adjudication.is_denied:
            return {"error": f"Tool blocked: {adjudication.reason}"}
        return None

    async def after_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
        result: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Callback executed after a tool has been called.

        Evaluates the tool result against policies.

        Args:
            tool: The tool instance that has just been executed.
            tool_args: The original arguments passed to the tool.
            tool_context: The context specific to the tool execution.
            result: The dictionary returned by the tool invocation.

        Returns:
            Modified result dict if policy violation, None to use original.
        """
        self._log.debug(f"[SonderaHarness] After tool: {tool.name}")

        adjudication = await self._harness.adjudicate(
            Stage.POST_TOOL,
            Role.TOOL,
            ToolResponseContent(tool_id=tool.name, response=result),
        )
        self._log.info(
            f"[SonderaHarness] After tool adjudication for trajectory {self._harness.trajectory_id}"
        )

        if adjudication.is_denied:
            return {"error": f"Tool result blocked: {adjudication.reason}"}
        return None

    # -------------------------------------------------------------------------
    # Event Callback
    # -------------------------------------------------------------------------

    async def on_event_callback(
        self,
        *,
        invocation_context: InvocationContext,
        event: Event,
    ) -> Event | None:
        """Callback executed after an event is yielded from runner.

        Args:
            invocation_context: The context for the entire invocation.
            event: The event raised by the runner.

        Returns:
            None to use original event.
        """
        self._log.debug(f"[SonderaHarness] Event: {event.author}")
        return None

    # -------------------------------------------------------------------------
    # Runner Lifecycle Callbacks
    # -------------------------------------------------------------------------

    async def after_run_callback(
        self,
        *,
        invocation_context: InvocationContext,
    ) -> None:
        """Callback executed after an ADK runner run has completed.

        Finalizes the harness trajectory.

        Args:
            invocation_context: The context for the entire invocation.
        """
        self._log.info(
            f"[SonderaHarness] Finalizing trajectory {self._harness.trajectory_id}"
        )
        await self._harness.finalize()

    async def close(self) -> None:
        """Method executed when the runner is closed.

        Used for cleanup tasks such as closing network connections.
        """
        self._log.debug("[SonderaHarness] Plugin closed")
