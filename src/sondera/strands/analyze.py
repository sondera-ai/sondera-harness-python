"""Strands Agent analysis utilities."""

import inspect
import json
import logging
from collections.abc import Callable
from typing import Any, get_type_hints

from sondera.types import Agent, Parameter, SourceCode, Tool

logger = logging.getLogger(__name__)


def _get_function_source(func: Callable) -> tuple[str, str]:
    """Extract source code and language from a function."""
    try:
        source = inspect.getsource(func)
        return "python", source
    except (OSError, TypeError):
        return "python", f"# Source code not available for {func.__name__}"


def _analyze_function_parameters(func: Callable) -> list[Parameter]:
    """Analyze function parameters and return Sondera format Parameters."""
    parameters = []
    sig = inspect.signature(func)

    try:
        type_hints = get_type_hints(func)
    except Exception:
        type_hints = {}

    for param_name, param in sig.parameters.items():
        if param_name in ["tool_context", "self", "cls"]:
            continue

        param_type = "Any"
        if param.annotation != inspect.Parameter.empty:
            if isinstance(param.annotation, type):
                param_type = param.annotation.__name__
            else:
                param_type = str(param.annotation)
        elif param_name in type_hints:
            hint = type_hints[param_name]
            param_type = hint.__name__ if isinstance(hint, type) else str(hint)

        description = f"Parameter {param_name}"
        if func.__doc__:
            lines = func.__doc__.split("\n")
            for line in lines:
                if param_name in line:
                    description = line.strip()
                    break

        parameters.append(
            Parameter(name=param_name, description=description, type=param_type)
        )

    return parameters


def _get_function_return_type(func: Callable) -> str:
    """Extract the return type from a function."""
    sig = inspect.signature(func)
    if sig.return_annotation != inspect.Signature.empty:
        if isinstance(sig.return_annotation, type):
            return sig.return_annotation.__name__
        else:
            return str(sig.return_annotation)

    try:
        type_hints = get_type_hints(func)
        if "return" in type_hints:
            hint = type_hints["return"]
            if isinstance(hint, type):
                return hint.__name__
            else:
                return str(hint)
    except Exception:
        pass

    return "Any"


def _extract_strands_tool_schema(tool: Any) -> tuple[str | None, str | None]:
    """Extract JSON schemas from a Strands tool.

    Strands tools decorated with @tool have a tool_spec attribute containing:
    - name: tool name
    - description: tool description
    - inputSchema: dict with 'json' key containing the JSON schema

    Args:
        tool: A Strands tool (decorated function or tool object)

    Returns:
        Tuple of (parameters_json_schema, response_json_schema)
    """
    parameters_json_schema = None
    response_json_schema = None

    try:
        # Check for tool_spec attribute (Strands @tool decorated functions)
        tool_spec = getattr(tool, "tool_spec", None)
        if tool_spec and isinstance(tool_spec, dict):
            # Extract inputSchema from tool_spec
            input_schema = tool_spec.get("inputSchema", {})
            if input_schema:
                # Strands stores the JSON schema under the 'json' key
                json_schema = input_schema.get("json", input_schema)
                if json_schema:
                    parameters_json_schema = json.dumps(json_schema)

        # Try to generate response schema from return type annotation
        if callable(tool):
            return_type = _get_function_return_type(tool)
            if return_type and return_type != "Any":
                response_json_schema = json.dumps(
                    {
                        "type": _python_type_to_json_schema_type(return_type),
                        "description": f"Return value of type {return_type}",
                    }
                )
    except Exception as e:
        logger.debug(f"Could not extract JSON schema from tool: {e}")

    return parameters_json_schema, response_json_schema


def _python_type_to_json_schema_type(python_type: str) -> str:
    """Convert Python type name to JSON Schema type."""
    type_mapping = {
        "str": "string",
        "int": "integer",
        "float": "number",
        "bool": "boolean",
        "list": "array",
        "dict": "object",
        "None": "null",
        "NoneType": "null",
    }
    return type_mapping.get(python_type, "string")


def _extract_tool_info(tool: Any) -> dict[str, Any]:
    """Extract all tool information from a Strands tool.

    Args:
        tool: A Strands tool

    Returns:
        Dictionary with tool name, description, and schemas
    """
    # Get tool_spec if available (Strands @tool decorated functions)
    tool_spec = getattr(tool, "tool_spec", None)

    if tool_spec and isinstance(tool_spec, dict):
        tool_name = tool_spec.get(
            "name", getattr(tool, "tool_name", getattr(tool, "__name__", "unknown"))
        )
        tool_description = tool_spec.get("description", "")
    else:
        tool_name = getattr(
            tool,
            "tool_name",
            getattr(tool, "name", getattr(tool, "__name__", "unknown")),
        )
        tool_description = getattr(
            tool, "description", tool.__doc__ or f"Tool {tool_name}"
        )

    return {
        "name": tool_name,
        "description": tool_description,
    }


def format_strands_agent(agent: Any) -> Agent:
    """Transform a Strands agent into Sondera Agent format.

    Extracts tool metadata including JSON schemas for parameters and responses.

    Args:
        agent: The Strands agent instance

    Returns:
        Sondera Agent representation with full tool schemas
    """
    # Extract agent metadata
    agent_name = getattr(agent, "name", "strands-agent")
    agent_id = agent_name
    system_prompt = getattr(agent, "system_prompt", "")
    description = getattr(agent, "description", f"Strands agent: {agent_name}")

    # Extract tools
    tools = []
    agent_tools = getattr(agent, "tools", []) or []

    for tool in agent_tools:
        try:
            # Extract tool info from tool_spec or attributes
            tool_info = _extract_tool_info(tool)
            tool_name = tool_info["name"]
            tool_description = tool_info["description"]

            # Extract JSON schemas
            parameters_json_schema, response_json_schema = _extract_strands_tool_schema(
                tool
            )

            # Analyze function for additional info
            if callable(tool):
                parameters = _analyze_function_parameters(tool)
                response_type = _get_function_return_type(tool)
                language, source_code = _get_function_source(tool)
            else:
                parameters = []
                response_type = "Any"
                language, source_code = "python", f"# Tool object: {tool_name}"

            tools.append(
                Tool(
                    name=tool_name,
                    description=tool_description.strip()
                    if isinstance(tool_description, str)
                    else str(tool_description),
                    parameters=parameters,
                    parameters_json_schema=parameters_json_schema,
                    response=response_type,
                    response_json_schema=response_json_schema,
                    source=SourceCode(language=language, code=source_code),
                )
            )
        except Exception as e:
            logger.warning(f"Could not analyze tool {tool}: {e}")

    return Agent(
        id=agent_id,
        provider_id="strands",
        name=agent_name,
        instruction=system_prompt,
        description=description,
        tools=tools,
    )
