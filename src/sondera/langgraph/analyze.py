"""LangGraph agent analysis and automatic Agent message generation."""

import contextlib
import inspect
import json
import logging
from collections.abc import Callable
from typing import Any, get_type_hints

from langchain_core.tools import BaseTool

from sondera.types import Agent, Parameter, SourceCode, Tool

logger = logging.getLogger(__name__)


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


def _extract_json_schema_from_pydantic(schema_class: Any) -> str | None:
    """Extract JSON schema from a Pydantic model class.

    Works with both Pydantic v1 and v2.
    """
    if schema_class is None:
        return None

    try:
        # Try Pydantic v2 style first
        if hasattr(schema_class, "model_json_schema"):
            return json.dumps(schema_class.model_json_schema())
        # Fallback to Pydantic v1 style
        elif hasattr(schema_class, "schema"):
            return json.dumps(schema_class.schema())
    except Exception as e:
        logger.debug(f"Could not extract JSON schema from Pydantic model: {e}")

    return None


def _extract_tool_json_schemas(tool: Any) -> tuple[str | None, str | None]:
    """Extract parameters and response JSON schemas from a LangChain tool.

    Args:
        tool: A LangChain tool (BaseTool instance or decorated function)

    Returns:
        Tuple of (parameters_json_schema, response_json_schema)
    """
    parameters_json_schema = None
    response_json_schema = None

    try:
        # For BaseTool instances, extract from args_schema
        if hasattr(tool, "args_schema") and tool.args_schema is not None:
            parameters_json_schema = _extract_json_schema_from_pydantic(
                tool.args_schema
            )

        # Try to get the tool's input schema directly (LangChain provides this)
        if parameters_json_schema is None and hasattr(tool, "get_input_schema"):
            try:
                input_schema = tool.get_input_schema()
                if input_schema is not None:
                    parameters_json_schema = _extract_json_schema_from_pydantic(
                        input_schema
                    )
            except Exception:
                pass

        # For decorated functions, try to build schema from function signature
        func = None
        if inspect.isfunction(tool):
            func = tool
        elif hasattr(tool, "func") and inspect.isfunction(tool.func):
            func = tool.func

        if func is not None and parameters_json_schema is None:
            parameters_json_schema = _build_json_schema_from_function(func)

        # Extract response schema from return type
        if func is not None:
            response_json_schema = _build_response_schema_from_function(func)

    except Exception as e:
        logger.debug(f"Could not extract JSON schemas from tool: {e}")

    return parameters_json_schema, response_json_schema


def _build_json_schema_from_function(func: Callable) -> str | None:
    """Build a JSON schema from function signature and type hints."""
    try:
        sig = inspect.signature(func)
        type_hints = {}
        with contextlib.suppress(Exception):
            type_hints = get_type_hints(func)

        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            # Skip special parameters
            if param_name in ["self", "cls", "callbacks", "run_manager"]:
                continue

            # Determine the type
            param_type = "string"  # default
            if param.annotation != inspect.Parameter.empty:
                if isinstance(param.annotation, type):
                    param_type = _python_type_to_json_schema_type(
                        param.annotation.__name__
                    )
                else:
                    type_str = str(param.annotation)
                    # Handle common typing module types
                    if "str" in type_str.lower():
                        param_type = "string"
                    elif "int" in type_str.lower():
                        param_type = "integer"
                    elif "float" in type_str.lower():
                        param_type = "number"
                    elif "bool" in type_str.lower():
                        param_type = "boolean"
                    elif "list" in type_str.lower():
                        param_type = "array"
                    elif "dict" in type_str.lower():
                        param_type = "object"
            elif param_name in type_hints:
                hint = type_hints[param_name]
                if isinstance(hint, type):
                    param_type = _python_type_to_json_schema_type(hint.__name__)

            # Extract description from docstring
            description = f"Parameter {param_name}"
            if func.__doc__:
                lines = func.__doc__.split("\n")
                for line in lines:
                    if param_name in line and ":" in line:
                        parts = line.split(":")
                        if len(parts) > 1:
                            description = parts[1].strip()
                            break

            properties[param_name] = {"type": param_type, "description": description}

            # Check if parameter is required (no default value)
            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        if not properties:
            return None

        schema = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required

        return json.dumps(schema)

    except Exception as e:
        logger.debug(f"Could not build JSON schema from function: {e}")
        return None


def _build_response_schema_from_function(func: Callable) -> str | None:
    """Build a response JSON schema from function return type."""
    try:
        sig = inspect.signature(func)
        return_type = None

        if sig.return_annotation != inspect.Signature.empty:
            if isinstance(sig.return_annotation, type):
                return_type = sig.return_annotation.__name__
            else:
                return_type = str(sig.return_annotation)

        if return_type is None:
            try:
                type_hints = get_type_hints(func)
                if "return" in type_hints:
                    hint = type_hints["return"]
                    return_type = hint.__name__ if isinstance(hint, type) else str(hint)
            except Exception:
                pass

        if return_type and return_type not in ["Any", "None", "NoneType"]:
            json_type = _python_type_to_json_schema_type(return_type)
            return json.dumps(
                {
                    "type": json_type,
                    "description": f"Return value of type {return_type}",
                }
            )

    except Exception as e:
        logger.debug(f"Could not build response schema from function: {e}")

    return None


def _get_function_source(func: Callable) -> tuple[str, str]:
    """Extract source code and language from a function."""
    try:
        source = inspect.getsource(func)
        return "python", source
    except (OSError, TypeError):
        # Source not available (e.g., built-in function)
        return "python", f"# Source code not available for {func.__name__}"


def _analyze_function_parameters(func: Callable) -> list[Parameter]:
    """Analyze function parameters and return Sondera format Parameters."""
    parameters = []
    sig = inspect.signature(func)

    # Try to get type hints for better type information
    try:
        type_hints = get_type_hints(func)
    except Exception:
        type_hints = {}

    for param_name, param in sig.parameters.items():
        # Skip special parameters that LangChain injects
        if param_name in ["self", "cls", "callbacks", "run_manager"]:
            continue

        # Get parameter type
        param_type = "Any"
        if param.annotation != inspect.Parameter.empty:
            if isinstance(param.annotation, type):
                param_type = param.annotation.__name__
            else:
                param_type = str(param.annotation)
        elif param_name in type_hints:
            hint = type_hints[param_name]
            param_type = hint.__name__ if isinstance(hint, type) else str(hint)

        # Extract parameter description from docstring if available
        description = f"Parameter {param_name}"
        if func.__doc__:
            # Simple extraction - could be enhanced with proper docstring parsing
            lines = func.__doc__.split("\n")
            for line in lines:
                if param_name in line and ":" in line:
                    # Try to extract description after parameter name
                    parts = line.split(":")
                    if len(parts) > 1:
                        description = parts[1].strip()
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

    # Try type hints as fallback
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


def _analyze_langchain_tool(tool: Any) -> Tool:
    """Analyze a LangChain tool and convert it to Sondera Tool format."""
    # Extract JSON schemas for the tool (works for all tool types)
    parameters_json_schema, response_json_schema = _extract_tool_json_schemas(tool)

    if inspect.isfunction(tool):
        # It's a raw function decorated with @tool
        func = tool
        tool_name = func.__name__
        tool_description = func.__doc__ or f"Function {tool_name}"

        # Analyze function signature for parameters
        parameters = _analyze_function_parameters(func)

        # Get return type
        response_type = _get_function_return_type(func)

        # Extract source code
        language, source_code = _get_function_source(func)

        return Tool(
            name=tool_name,
            description=tool_description.strip(),
            parameters=parameters,
            parameters_json_schema=parameters_json_schema,
            response=response_type,
            response_json_schema=response_json_schema,
            source=SourceCode(language=language, code=source_code),
        )

    elif isinstance(tool, BaseTool) or hasattr(tool, "func"):
        # It's a BaseTool instance (including StructuredTool from @tool decorator)
        tool_name = tool.name
        tool_description = tool.description or f"Tool {tool_name}"

        # If it has a func attribute (from @tool decorator), analyze the underlying function
        # Note: StructuredTool has func attr, but BaseTool doesn't - use getattr for type safety
        if (func := getattr(tool, "func", None)) and inspect.isfunction(func):
            parameters = _analyze_function_parameters(func)
            response_type = _get_function_return_type(func)
            language, source_code = _get_function_source(func)
        else:
            # For other BaseTool instances, try to extract parameters from the schema
            parameters = []
            if hasattr(tool, "args_schema") and tool.args_schema:
                schema = tool.args_schema
                # Pydantic v1 style - has __fields__ dict with ModelField objects
                if v1_fields := getattr(schema, "__fields__", None):
                    for field_name, field_info in v1_fields.items():
                        param_type = "Any"
                        # Pydantic v1 ModelField uses type_ attribute
                        if field_type := getattr(field_info, "type_", None):
                            if isinstance(field_type, type):
                                param_type = field_type.__name__
                            else:
                                param_type = str(field_type)

                        description = getattr(
                            field_info, "description", f"Parameter {field_name}"
                        )
                        if description is None:
                            description = f"Parameter {field_name}"
                        parameters.append(
                            Parameter(
                                name=field_name,
                                description=description,
                                type=param_type,
                            )
                        )
                # Pydantic v2 style - has model_fields dict with FieldInfo objects
                elif v2_fields := getattr(schema, "model_fields", None):
                    for field_name, field_info in v2_fields.items():
                        param_type = "Any"
                        if annotation := getattr(field_info, "annotation", None):
                            if isinstance(annotation, type):
                                param_type = annotation.__name__
                            else:
                                param_type = str(annotation)

                        description = getattr(
                            field_info, "description", f"Parameter {field_name}"
                        )
                        if description is None:
                            description = f"Parameter {field_name}"
                        parameters.append(
                            Parameter(
                                name=field_name,
                                description=description,
                                type=param_type,
                            )
                        )

            response_type = "Any"

            # Try to get source code from various methods
            language = "python"
            source_code = f"# BaseTool instance: {tool_name}"
            for method_name in ["_run", "_arun", "run", "__call__"]:
                if hasattr(tool, method_name):
                    try:
                        method = getattr(tool, method_name)
                        source_code = inspect.getsource(method)
                        break
                    except Exception:
                        pass

        return Tool(
            name=tool_name,
            description=tool_description,
            parameters=parameters,
            parameters_json_schema=parameters_json_schema,
            response=response_type,
            response_json_schema=response_json_schema,
            source=SourceCode(language=language, code=source_code),
        )

    else:
        # Unknown tool type, do our best
        tool_name = getattr(tool, "name", tool.__class__.__name__)
        tool_description = getattr(tool, "description", f"Tool {tool_name}")

        return Tool(
            name=tool_name,
            description=tool_description,
            parameters=[],
            parameters_json_schema=parameters_json_schema,
            response="Any",
            response_json_schema=response_json_schema,
            source=SourceCode(
                language="python", code=f"# Unknown tool type: {type(tool)}"
            ),
        )


def analyze_langchain_tools(
    tools: list[Any],
    agent_id: str,
    agent_name: str | None = None,
    agent_description: str | None = None,
    agent_instruction: str | None = None,
    provider_id: str = "langchain",
) -> Agent:
    """Analyze LangChain tools and generate a Sondera Agent object.

    Args:
        tools: List of LangChain tools (functions decorated with @tool or BaseTool instances)
        agent_id: Unique identifier for the agent
        agent_name: Name of the agent (defaults to agent_id)
        agent_description: Description of the agent
        agent_instruction: Instruction or goal of the agent
        provider_id: Provider identifier (defaults to "langchain")

    Returns:
        Agent object with automatically analyzed tools
    """
    agent_name = agent_name or agent_id
    agent_description = agent_description or f"Agent {agent_name}"
    agent_instruction = agent_instruction or "Execute tasks using available tools"

    sondera_tools = []
    for tool in tools:
        try:
            sondera_tool = _analyze_langchain_tool(tool)
            sondera_tools.append(sondera_tool)
        except Exception as e:
            # Log the error but continue with other tools
            import logging

            logging.warning(f"Failed to analyze tool {tool}: {e}")
            # Create a minimal tool entry
            tool_name = getattr(tool, "name", str(tool))
            sondera_tools.append(
                Tool(
                    name=tool_name,
                    description=f"Tool {tool_name} (analysis failed)",
                    parameters=[],
                    response="Any",
                    source=SourceCode(
                        language="python", code=f"# Analysis failed for {tool_name}"
                    ),
                )
            )

    return Agent(
        id=agent_id,
        provider_id=provider_id,
        name=agent_name,
        description=agent_description,
        instruction=agent_instruction,
        tools=sondera_tools,
    )


def create_agent_from_langchain_tools(
    tools: list[Any],
    agent_id: str,
    agent_name: str | None = None,
    agent_description: str | None = None,
    agent_instruction: str | None = None,
    provider_id: str = "langchain",
    system_prompt_func: Callable[[], str] | None = None,
) -> Agent:
    """Convenience function to create a Sondera Agent from LangChain tools.

    This function automatically analyzes LangChain tools and creates a Sondera Agent.
    It can also extract system instructions from a provided system prompt function.

    Args:
        tools: List of LangChain tools (functions decorated with @tool or BaseTool instances)
        agent_id: Unique identifier for the agent
        agent_name: Human-readable name for the agent
        agent_description: Description of what the agent does
        agent_instruction: Instructions for the agent behavior (optional if system_prompt_func provided)
        provider_id: Provider identifier (default: "langchain")
        system_prompt_func: Optional function that returns system prompt/instructions

    Returns:
        Agent: Configured Sondera Agent with automatically analyzed tools
    """

    # Extract system instruction from system_prompt_func if provided and agent_instruction is None
    final_instruction = agent_instruction
    if final_instruction is None and system_prompt_func is not None:
        try:
            system_prompt = system_prompt_func()
            if isinstance(system_prompt, str) and system_prompt.strip():
                final_instruction = system_prompt.strip()
                logger.info(
                    f"Extracted system instruction from system_prompt_func: {len(final_instruction)} characters"
                )
        except Exception as e:
            logger.warning(
                f"Failed to extract system instruction from system_prompt_func: {e}"
            )

    # Fallback to a default instruction if none provided
    if final_instruction is None:
        final_instruction = (
            "Use the available tools to assist users effectively and safely."
        )
        logger.info("Using default agent instruction")

    return analyze_langchain_tools(
        tools=tools,
        agent_id=agent_id,
        agent_name=agent_name,
        agent_description=agent_description,
        agent_instruction=final_instruction,
        provider_id=provider_id,
    )
