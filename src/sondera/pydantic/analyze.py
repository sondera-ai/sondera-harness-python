"""Pydantic AI agent analysis — build Sondera Agent cards from Pydantic AI agents."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from sondera.types import Agent, AgentCard, Parameter, ReActAgentCard, Tool

if TYPE_CHECKING:
    from pydantic_ai import Agent as PydanticAgent

logger = logging.getLogger(__name__)


def discover_tool_definitions(agent: PydanticAgent[Any]) -> list[dict[str, Any]]:
    """Extract raw tool definitions from a Pydantic AI agent.

    Returns a list of dicts with keys: name, description, parameters_json_schema.
    """
    tools: list[dict[str, Any]] = []
    for toolset in agent.toolsets:
        if hasattr(toolset, "tool_defs"):
            for td in toolset.tool_defs:  # type: ignore[attr-defined]
                tools.append(
                    {
                        "name": td.name,
                        "description": td.description or "",
                        "parameters_json_schema": td.parameters_json_schema,
                    }
                )
        elif hasattr(toolset, "tools"):
            for _name, tool in toolset.tools.items():  # type: ignore[attr-defined]
                td = tool.tool_def
                tools.append(
                    {
                        "name": td.name,
                        "description": td.description or "",
                        "parameters_json_schema": td.parameters_json_schema,
                    }
                )
    return tools


def _tool_def_to_sondera_tool(raw: dict[str, Any]) -> Tool:
    """Convert a raw tool definition dict to a Sondera Tool."""
    params_schema = raw.get("parameters_json_schema") or {}
    parameters: list[Parameter] = []
    properties = params_schema.get("properties", {})
    for param_name, prop in properties.items():
        param_type = prop.get("type", "string")
        description = prop.get("description", f"Parameter {param_name}")
        parameters.append(
            Parameter(name=param_name, description=description, param_type=param_type)
        )

    return Tool(
        name=raw["name"],
        description=raw.get("description", ""),
        parameters=parameters,
        parameters_json_schema=json.dumps(params_schema) if params_schema else None,
        response="Any",
    )


def build_agent_card(
    agent: PydanticAgent[Any],
    agent_id: str,
    name: str | None = None,
    provider_id: str = "pydantic-ai",
) -> Agent:
    """Build a Sondera Agent card from a Pydantic AI agent.

    Args:
        agent: The Pydantic AI agent to analyze.
        agent_id: Unique identifier for the Sondera agent.
        name: Optional human-readable name (defaults to agent_id).
        provider_id: Provider identifier (defaults to "pydantic-ai").

    Returns:
        A Sondera Agent with tool inventory derived from the Pydantic AI agent.
    """
    raw_tools = discover_tool_definitions(agent)
    sondera_tools = [_tool_def_to_sondera_tool(t) for t in raw_tools]

    instruction: str | None = None
    if isinstance(agent.instructions, str):
        instruction = agent.instructions

    return Agent(
        id=agent_id,
        provider=provider_id,
        card=AgentCard.react(
            ReActAgentCard(
                system_instruction=instruction,
                tools=sondera_tools,
            )
        ),
    )
