import inspect
import logging
from collections.abc import Callable
from typing import get_type_hints

from google.adk import Agent as AdkAgent
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.function_tool import FunctionTool

from sondera.types import Agent, Parameter, SourceCode, Tool

logger = logging.getLogger(__name__)


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
        # Skip special parameters like tool_context that ADK injects
        if param_name in ["tool_context", "self", "cls"]:
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


def _extract_json_schemas(func_decl) -> tuple[str | None, str | None]:
    """Extract parameters and response JSON schemas from a function declaration."""
    parameters_json_schema = None
    response_json_schema = None

    if func_decl and func_decl.parameters is not None:
        parameters_json_schema = func_decl.parameters.model_dump_json(
            exclude_unset=True
        )
    if func_decl and func_decl.response is not None:
        response_json_schema = func_decl.response.model_dump_json(exclude_unset=True)

    return parameters_json_schema, response_json_schema


def _extract_source_code(obj: Callable | object, default_name: str) -> tuple[str, str]:
    """Extract source code from a function or tool object."""
    # If it's a function, get source directly
    if inspect.isfunction(obj):
        return _get_function_source(obj)

    # For BaseTool instances, try to find source from methods
    language = "python"
    source_code = f"# {obj.__class__.__name__} instance: {default_name}"
    for method_name in ["run_async", "run", "execute", "__call__"]:
        if hasattr(obj, method_name):
            try:
                method = getattr(obj, method_name)
                source_code = inspect.getsource(method)
                break
            except Exception:
                pass

    return language, source_code


def format(
    agent: AdkAgent, agent_name: str | None = None, agent_id: str | None = None
) -> Agent:
    """Transform the ADK agent into the Sondera Format."""

    agent_name = agent_name or agent.name
    agent_id = agent_id or agent.name

    if type(agent) is not AdkAgent:
        raise ValueError("Agent must be an ADK agent")

    # Extract instruction from various ADK instruction provider types
    if isinstance(agent.instruction, str):
        instruction = agent.instruction
    elif (render := getattr(agent.instruction, "render", None)) and callable(render):
        # Handle InstructionProvider with render method
        try:
            instruction = render()
            if not isinstance(instruction, str):
                raise TypeError(
                    f"Expected render() to return str, got {type(instruction).__name__}"
                )
        except TypeError:
            raise
        except Exception:
            instruction = str(agent.instruction)
    elif agent.instruction is not None:
        # Fallback for other types - convert to string
        instruction = str(agent.instruction)
    else:
        instruction = ""

    tools = []
    for tool in agent.tools:
        logger.info(f"Analyzing tool: {tool}")
        # ADK tools can be functions or BaseTool/BaseToolset instances
        if inspect.isfunction(tool):
            # It's a raw function - wrap it in FunctionTool to get JSON schemas
            func = tool
            tool_name = func.__name__
            tool_description = func.__doc__ or f"Function {tool_name}"

            # Wrap function in FunctionTool to get JSON schema declarations
            function_tool = FunctionTool(func)
            func_decl = function_tool._get_declaration()
            parameters_json_schema, response_json_schema = _extract_json_schemas(
                func_decl
            )

            # Analyze function signature for parameters (fallback if JSON schema unavailable)
            parameters = _analyze_function_parameters(func)
            response_type = _get_function_return_type(func)
            language, source_code = _extract_source_code(func, tool_name)

        elif isinstance(tool, BaseTool):
            # It's a BaseTool instance or similar
            tool_name = getattr(tool, "name", tool.__class__.__name__)
            tool_description = getattr(tool, "description", f"Tool {tool_name}")

            # Try to get JSON schema from tool declaration
            func_decl = tool._get_declaration()
            parameters_json_schema, response_json_schema = _extract_json_schemas(
                func_decl
            )

            # For BaseTool instances, we may not have parameter info readily available
            parameters = []
            response_type = "Any"
            language, source_code = _extract_source_code(tool, tool_name)

        else:
            raise ValueError(f"Unknown tool type: {type(tool)}")

        # Create Tool object (common for both function and BaseTool paths)
        tools.append(
            Tool(
                name=tool_name,
                description=tool_description.strip(),
                parameters=parameters,
                response=response_type,
                parameters_json_schema=parameters_json_schema,
                response_json_schema=response_json_schema,
                source=SourceCode(language=language, code=source_code),
            )
        )

    return Agent(
        id=agent_id,
        provider_id="google",
        name=agent_name,
        instruction=instruction,
        description=agent.description,
        tools=tools,
    )
