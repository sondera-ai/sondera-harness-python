"""Sondera Harness Middleware for LangGraph."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    hook_config,
)
from langchain.messages import ToolMessage
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.runtime import Runtime
from langgraph.types import Command

try:
    from langgraph.graph import END
except ImportError:
    # Fallback for older versions
    END = "__end__"

from sondera.harness import Harness
from sondera.types import (
    PromptContent,
    Role,
    Stage,
    ToolRequestContent,
    ToolResponseContent,
)

_LOGGER = logging.getLogger(__name__)


class Strategy(str, Enum):
    """Strategy for handling policy violations."""

    BLOCK = "block"
    """Jump to end immediately when a policy violation is detected."""
    STEER = "steer"
    """Allow continuation with modified content when a policy violation is detected."""


class State(AgentState):
    """Agent state with additional Sondera Harness-related fields."""

    trajectory_id: str | None


class SonderaHarnessMiddleware(AgentMiddleware[State]):
    """LangGraph middleware that integrates with Sondera Harness for policy enforcement.

    This middleware intercepts agent execution at key points (before/after agent,
    model calls, tool calls) and delegates policy evaluation to the Sondera Harness
    Service. Based on the adjudication result, it can either allow execution to
    proceed, block and jump to end, or steer the response with modified content.

    Example:
        ```python
        from sondera.langgraph.middleware import SonderaHarnessMiddleware, Strategy
        from sondera.harness import RemoteHarness
        from sondera.types import Agent
        from langchain.agents import create_agent

        # Create a harness instance
        harness = RemoteHarness(
            endpoint="localhost:50051",
            organization_id="my-tenant",
            agent=Agent(
                id="my-agent",
                provider_id="langchain",
                name="My Agent",
                description="An agent with Sondera governance",
                instruction="Be helpful",
                tools=[],
            ),
        )

        # Create middleware with the harness
        middleware = SonderaHarnessMiddleware(
            harness=harness,
            strategy=Strategy.BLOCK,
        )

        agent = create_agent(
            model="gpt-4o",
            tools=[...],
            middleware=[middleware],
        )
        ```
    """

    state_schema = State

    def __init__(
        self,
        harness: Harness,
        *,
        strategy: Strategy = Strategy.BLOCK,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the Sondera Harness Middleware.

        Args:
            harness: The Sondera Harness instance to use
            strategy: How to handle policy violations (BLOCK or STEER)
        """
        self._harness = harness
        self._strategy = strategy
        self._log = logger or _LOGGER
        super().__init__()

    @hook_config(can_jump_to=["end"])
    async def abefore_agent(
        self, state: State, runtime: Runtime
    ) -> dict[str, Any] | None:
        """Execute before agent starts.

        Initializes the trajectory and evaluates the user's input message
        against policies before the agent begins processing.

        Args:
            state: The current agent state containing messages
            runtime: The LangGraph runtime

        Returns:
            None to continue, or a dict with state updates (including optional jump_to)
        """
        trajectory_id = state.get("trajectory_id")
        updates = {}

        if trajectory_id and trajectory_id.strip():  # Check for non-empty string
            # Resume an existing trajectory.
            await self._harness.resume(trajectory_id)
            self._log.debug(
                f"[SonderaHarness] Resumed trajectory: {self._harness.trajectory_id}"
            )
        else:
            # Initialize a new trajectory if needed.
            if self._harness.trajectory_id is None:
                await self._harness.initialize()
            updates["trajectory_id"] = self._harness.trajectory_id
            self._log.debug(
                f"[SonderaHarness] Initialized trajectory: {self._harness.trajectory_id}"
            )

        # Extract user message from state
        user_message = _extract_last_user_message(state)
        if user_message is None:
            self._log.debug(
                "[SonderaHarness] No user message found in state, skipping pre-agent check"
            )
            # Still return trajectory_id if we just created one
            return updates if updates else None

        content = _message_to_text(user_message)
        self._log.debug(
            f"[SonderaHarness] Evaluating user input for trajectory {self._harness.trajectory_id}"
        )

        adjudication = await self._harness.adjudicate(
            Stage.PRE_MODEL,
            Role.USER,
            PromptContent(text=content),
        )
        self._log.info(
            f"[SonderaHarness] Before Agent Adjudication for trajectory {self._harness.trajectory_id}"
        )

        if adjudication.is_denied:
            self._log.warning(
                f"[SonderaHarness] Policy violation detected (strategy={self._strategy.value}): "
                f"{adjudication.reason}"
            )
            if self._strategy == Strategy.BLOCK:
                # BLOCK: Jump to end immediately with policy message
                return {
                    "messages": [AIMessage(content=adjudication.reason)],
                    "jump_to": "end",
                    **updates,  # Include trajectory_id in the response
                }
            # STEER: Replace user message with policy guidance and continue
            return {
                "messages": [
                    AIMessage(
                        content=f"Policy violation in user message: {adjudication.reason}"
                    )
                ],
                **updates,  # Include trajectory_id in the response
            }

        # Return trajectory_id if we just created one
        return updates if updates else None

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """Wrap model calls with policy evaluation.

        Evaluates the model request before calling the model, then evaluates
        the model's response after it returns.

        Args:
            request: The model request containing messages and configuration
            handler: The handler function to call the actual model

        Returns:
            The model response, potentially modified based on policy
        """
        if isinstance(request.messages[-1], AIMessage):
            # Last message is an AIMessage, so we need to adjudicate it. HumanMessage was checked in abefore_agent.
            _LOGGER.debug(
                f"[SonderaHarness] Pre-model check for trajectory {self._harness.trajectory_id} {request.messages}"
            )
            pre_adjudication = await self._harness.adjudicate(
                Stage.PRE_MODEL,
                Role.MODEL,
                PromptContent(text=_message_to_text(request.messages[-1])),
            )

            if pre_adjudication.is_denied:
                _LOGGER.warning(
                    f"[SonderaHarness] Pre-model policy violation (strategy={self._strategy.value}): "
                    f"{pre_adjudication.reason}"
                )
                message = AIMessage(
                    content=f"Replaced message due to policy violation: {pre_adjudication.reason}"
                )
                if self._strategy == Strategy.STEER:
                    # STEER: Replace the last message with the policy message
                    request.messages[-1] = message
                else:
                    # BLOCK: Return early with the policy message
                    return ModelResponse(
                        result=[message],
                        structured_response=None,
                    )

        # Call the actual model
        response: ModelResponse = await handler(request)

        # Post-model check on each AI message in the response
        sanitized_messages: list[BaseMessage] = []
        for message in response.result:
            if isinstance(message, AIMessage):
                post_adjudication = await self._harness.adjudicate(
                    Stage.POST_MODEL,
                    Role.MODEL,
                    PromptContent(text=message.text),
                )
                self._log.info(
                    f"[SonderaHarness] Post-model Adjudication for trajectory {self._harness.trajectory_id}"
                )
                if post_adjudication.is_denied:
                    self._log.warning(
                        f"[SonderaHarness] Post-model policy violation (strategy={self._strategy.value}): "
                        f"{post_adjudication.reason}"
                    )
                    message = AIMessage(
                        content=f"Replaced message due to policy violation: {post_adjudication.reason}"
                    )
                    if self._strategy == Strategy.STEER:
                        # STEER: Replace the message with the policy message
                        sanitized_messages.append(message)
                    else:
                        # BLOCK: Return early with the policy message
                        return ModelResponse(
                            result=[message],
                            structured_response=response.structured_response,
                        )
                else:
                    sanitized_messages.append(message)
            else:
                self._log.debug(
                    f"[SonderaHarness] Non-AIMessage in response: {message} in trajectory {self._harness.trajectory_id}"
                )
                sanitized_messages.append(message)

        return ModelResponse(
            result=sanitized_messages,
            structured_response=response.structured_response,
        )

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        """Wrap tool calls with policy evaluation.

        Evaluates the tool request before execution, then evaluates
        the tool's response after it returns.

        Args:
            request: The tool call request containing tool name and arguments
            handler: The handler function to execute the actual tool

        Returns:
            The tool response, potentially modified based on policy
        """
        tool_name = request.tool_call.get("name", "unknown_tool")
        tool_args = request.tool_call.get("args", {})
        tool_call_id = request.tool_call.get("id", "")

        # Pre-tool check
        self._log.debug(
            f"[SonderaHarness] Pre-tool check for {tool_name} in trajectory {self._harness.trajectory_id}"
        )
        pre_adjudication = await self._harness.adjudicate(
            Stage.PRE_TOOL,
            Role.TOOL,
            ToolRequestContent(tool_id=tool_name, args=tool_args),
        )

        self._log.info(
            f"[SonderaHarness] Before Tool Adjudication for trajectory {self._harness.trajectory_id}"
        )

        if pre_adjudication.is_denied:
            self._log.warning(
                f"[SonderaHarness] Pre-tool policy violation for {tool_name} "
                f"(strategy={self._strategy.value}): {pre_adjudication.reason}"
            )
            if self._strategy == Strategy.BLOCK:
                # BLOCK: Jump to end using Command
                return Command(
                    goto=END,
                    update={
                        "messages": [
                            ToolMessage(
                                content=f"Tool execution was blocked. {pre_adjudication.reason}",
                                tool_call_id=tool_call_id,
                                name=tool_name,
                            )
                        ]
                    },
                )
            # STEER: Return tool message with policy violation instead of allowing execution
            return ToolMessage(
                content=f"Tool execution modified due to policy concern: {pre_adjudication.reason}",
                tool_call_id=tool_call_id,
                name=tool_name,
            )

        # Execute the actual tool
        result = await handler(request)

        # Post-tool check
        if isinstance(result, ToolMessage):
            output_text = _tool_message_to_text(result)

            post_adjudication = await self._harness.adjudicate(
                Stage.POST_TOOL,
                Role.TOOL,
                ToolResponseContent(tool_id=tool_name, response=output_text),
            )

            self._log.info(
                f"[SonderaHarness] After Tool Adjudication for trajectory {self._harness.trajectory_id}"
            )

            if post_adjudication.is_denied:
                self._log.warning(
                    f"[SonderaHarness] Post-tool policy violation for {tool_name} "
                    f"(strategy={self._strategy.value}): {post_adjudication.reason}"
                )
                if self._strategy == Strategy.BLOCK:
                    # BLOCK: Jump to end using Command
                    return Command(
                        goto=END,
                        update={
                            "messages": [
                                ToolMessage(
                                    content=f"Tool result was blocked. {post_adjudication.reason}",
                                    tool_call_id=tool_call_id,
                                    name=tool_name,
                                )
                            ]
                        },
                    )
                # STEER: Return modified ToolMessage with policy violation message
                return ToolMessage(
                    content=f"Tool result was modified. {post_adjudication.reason}",
                    tool_call_id=tool_call_id,
                    name=tool_name,
                )

        return result

    async def aafter_agent(
        self, state: AgentState, runtime: Runtime
    ) -> dict[str, Any] | None:
        """Execute after agent completes.

        Args:
            state: The final agent state containing messages
            runtime: The LangGraph runtime

        Returns:
            None to continue, or a dict with state updates
        """
        # Finalize the trajectory
        trajectory_id = self._harness.trajectory_id
        await self._harness.finalize()
        self._log.info(f"[SonderaHarness] Trajectory finalized: {trajectory_id}")

        # Preserve trajectory_id in final state for next conversation
        return {"trajectory_id": trajectory_id} if trajectory_id else None


def _extract_last_user_message(state: AgentState) -> BaseMessage | None:
    """Extract the last user message from agent state."""
    messages = state.get("messages", [])
    if not messages:
        return None

    # Look for the last HumanMessage
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return message
        if isinstance(message, dict) and message.get("role") == "user":
            return HumanMessage(content=message.get("content", ""))

    # Fallback to last message if it looks like user input
    last = messages[-1]
    if isinstance(last, dict):
        return HumanMessage(content=last.get("content", ""))
    return None


def _message_to_text(message: BaseMessage) -> str:
    """Convert a message to text content."""
    if isinstance(message.content, str):
        return message.content
    if isinstance(message.content, list):
        return " ".join(str(chunk) for chunk in message.content)
    return str(message.content)


def _tool_message_to_text(message: ToolMessage) -> str:
    """Convert a tool message to text content."""
    if isinstance(message.content, str):
        return message.content
    if isinstance(message.content, list):
        return " ".join(str(chunk) for chunk in message.content)
    return str(message.content)
