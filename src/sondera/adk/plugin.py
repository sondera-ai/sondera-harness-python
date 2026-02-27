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
    Decision,
    ModelMetadata,
    PromptContent,
    Role,
    Stage,
    ToolRequestContent,
    ToolResponseContent,
)

logger = logging.getLogger(__name__)


def _extract_text(content: genai_types.Content | None) -> str:
    """Concatenate all text and code parts from a Content object.

    Extracts ``p.text``, ``p.executable_code.code``, and
    ``p.code_execution_result.output`` so that generated code and execution
    output are also evaluated by the policy engine.

    Returns an empty string when no extractable text is found.
    """
    if content is None or content.parts is None:
        return ""
    texts: list[str] = []
    for p in content.parts:
        if p.text:
            texts.append(p.text)
        elif p.executable_code and p.executable_code.code:
            texts.append(p.executable_code.code)
        elif p.code_execution_result and p.code_execution_result.output:
            texts.append(p.code_execution_result.output)
    return "\n".join(texts)


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
            sondera_api_key="<YOUR_API_TOKEN>",
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
        self._current_model_name: str | None = None
        # Track the active session so we resume the same trajectory
        # across multiple messages in a single conversation.
        self._active_session_id: str | None = None

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
        agent = format(
            cast(LlmAgent, invocation_context.agent),
            invocation_context.app_name,
            invocation_context.app_name,
        )
        session_id = (
            invocation_context.session.id if invocation_context.session else None
        )

        # Continue the existing trajectory when the session is unchanged,
        # otherwise start a fresh one.
        same_session = (
            session_id is not None
            and session_id == self._active_session_id
            and self._harness.trajectory_id is not None
        )
        if same_session:
            # Trajectory is already active — nothing to do.
            pass
        else:
            # Finalize any previous trajectory before starting a new session
            if self._harness.trajectory_id is not None:
                await self._harness.finalize()
            await self._harness.initialize(agent=agent, session_id=session_id)
            self._active_session_id = session_id

        # Extract text from all parts of the user message
        content = _extract_text(user_message)
        if not content:
            return None

        # Adjudicate user input
        adjudication = await self._harness.adjudicate(
            Stage.PRE_MODEL, Role.USER, PromptContent(text=content)
        )
        self._log.info(
            "[SonderaHarness] User message adjudication for trajectory %s",
            self._harness.trajectory_id,
        )

        if adjudication.decision == Decision.DENY:
            return genai_types.Content(
                parts=[genai_types.Part(text=adjudication.reason)]
            )
        if adjudication.decision == Decision.ESCALATE:
            self._log.warning(
                "[SonderaHarness] ESCALATE: %s (trajectory %s)",
                adjudication.reason,
                self._harness.trajectory_id,
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
        self._log.debug("[SonderaHarness] Before agent: %s", agent.name)
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
        self._log.debug("[SonderaHarness] After agent: %s", agent.name)
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
            "[SonderaHarness] Before model call for trajectory %s",
            self._harness.trajectory_id,
        )

        # Extract the last user message from the request contents
        content = ""
        if llm_request.contents:
            for c in reversed(llm_request.contents):
                if c.role == "user":
                    content = _extract_text(c)
                    break

        # Capture model name for metadata (also store for after_model_callback)
        self._current_model_name = llm_request.model
        metadata = (
            ModelMetadata(model_name=llm_request.model) if llm_request.model else None
        )

        adjudication = await self._harness.adjudicate(
            Stage.PRE_MODEL,
            Role.MODEL,
            PromptContent(text=content),
            model_metadata=metadata,
        )
        self._log.info(
            "[SonderaHarness] Before model adjudication for trajectory %s",
            self._harness.trajectory_id,
        )

        if adjudication.decision == Decision.DENY:
            return LlmResponse(
                content=genai_types.Content(
                    parts=[genai_types.Part(text=adjudication.reason)]
                )
            )
        if adjudication.decision == Decision.ESCALATE:
            self._log.warning(
                "[SonderaHarness] ESCALATE: %s (trajectory %s)",
                adjudication.reason,
                self._harness.trajectory_id,
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

        # Extract text from all parts of the model response
        content = _extract_text(llm_response.content)
        if not content:
            return None

        # Reuse model name captured from before_model_callback
        metadata = (
            ModelMetadata(model_name=self._current_model_name)
            if self._current_model_name
            else None
        )

        adjudication = await self._harness.adjudicate(
            Stage.POST_MODEL,
            Role.MODEL,
            PromptContent(text=content),
            model_metadata=metadata,
        )
        self._log.info(
            "[SonderaHarness] After model adjudication for trajectory %s",
            self._harness.trajectory_id,
        )

        if adjudication.decision == Decision.DENY:
            return LlmResponse(
                content=genai_types.Content(
                    parts=[genai_types.Part(text=adjudication.reason)]
                )
            )
        if adjudication.decision == Decision.ESCALATE:
            self._log.warning(
                "[SonderaHarness] ESCALATE: %s (trajectory %s)",
                adjudication.reason,
                self._harness.trajectory_id,
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
        self._log.debug("[SonderaHarness] Before tool: %s", tool.name)

        adjudication = await self._harness.adjudicate(
            Stage.PRE_TOOL,
            Role.TOOL,
            ToolRequestContent(tool_id=tool.name, args=tool_args),
        )
        self._log.info(
            "[SonderaHarness] Before tool adjudication for trajectory %s - %s",
            self._harness.trajectory_id,
            adjudication,
        )

        if adjudication.decision == Decision.DENY:
            return {"error": f"Tool blocked: {adjudication.reason}"}
        if adjudication.decision == Decision.ESCALATE:
            self._log.warning(
                "[SonderaHarness] ESCALATE: %s (trajectory %s)",
                adjudication.reason,
                self._harness.trajectory_id,
            )
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
        self._log.debug("[SonderaHarness] After tool: %s", tool.name)

        if "error" in result:
            # There's already an error from the before_tool callback, skip adjudication.
            return result

        adjudication = await self._harness.adjudicate(
            Stage.POST_TOOL,
            Role.TOOL,
            ToolResponseContent(tool_id=tool.name, response=result),
        )
        self._log.info(
            "[SonderaHarness] After tool adjudication for trajectory %s - %s",
            self._harness.trajectory_id,
            adjudication,
        )

        if adjudication.decision == Decision.DENY:
            return {"error": f"Tool result blocked: {adjudication.reason}"}
        if adjudication.decision == Decision.ESCALATE:
            self._log.warning(
                "[SonderaHarness] ESCALATE: %s (trajectory %s)",
                adjudication.reason,
                self._harness.trajectory_id,
            )
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
        self._log.debug("[SonderaHarness] Event: %s", event.author)
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

        Does NOT finalize the trajectory here — finalization happens when the
        session changes (on_user_message_callback) or when the plugin is closed.
        This keeps a single trajectory alive across multiple turns.

        Args:
            invocation_context: The context for the entire invocation.
        """
        self._log.debug(
            "[SonderaHarness] Run completed for trajectory %s",
            self._harness.trajectory_id,
        )

    async def close(self) -> None:
        """Method executed when the runner is closed.

        Finalizes the active trajectory and cleans up resources.
        """
        if self._harness.trajectory_id is not None:
            self._log.info(
                "[SonderaHarness] Finalizing trajectory %s",
                self._harness.trajectory_id,
            )
            await self._harness.finalize()
            self._active_session_id = None
        self._log.debug("[SonderaHarness] Plugin closed")
