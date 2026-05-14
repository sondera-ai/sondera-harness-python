import importlib.resources
import json
import logging
from typing import Any

from cedar.schema import (
    Action,
    AppliesTo,
    CedarSchema,
    EntityType,
    NamespaceDefinition,
    SchemaType,
    validate,
)

from sondera.types import Agent, Tool

_LOGGER = logging.getLogger(__name__)


def openai_json_schema_to_cedar_type(json_schema_str: str | None) -> SchemaType | None:
    """Convert an OpenAI JSON schema string to Cedar SchemaType.

    Args:
        json_schema_str: JSON schema string in OpenAI format

    Returns:
        Cedar SchemaType or None if input is None/empty
    """
    if not json_schema_str:
        return None
    try:
        schema = json.loads(json_schema_str)
    except json.JSONDecodeError as e:
        raise e
    return json_schema_to_cedar_type(schema)


def json_schema_to_cedar_type(schema: dict[str, Any]) -> SchemaType:
    """Convert a JSON schema object to Cedar SchemaType.

    Maps JSON Schema types to Cedar types:
    - object/OBJECT -> Record with attributes
    - array/ARRAY -> Set with element type
    - string/STRING -> String
    - number/integer/NUMBER/INTEGER -> Long
    - boolean/BOOLEAN -> Boolean
    """
    if not isinstance(schema, dict):
        return SchemaType(type="String")  # Default fallback

    # Handle both lowercase and uppercase type names
    json_type = schema.get("type", "object").lower()

    if json_type == "object":
        properties = schema.get("properties", {})
        required_fields = set(schema.get("required", []))

        attributes = {}
        for prop_name, prop_schema in properties.items():
            cedar_type = json_schema_to_cedar_type(prop_schema)
            # Only set required=False if the field is optional
            # Cedar defaults to required=true, so we don't need to set it explicitly
            if prop_name not in required_fields:
                cedar_type.required = False
            attributes[prop_name] = cedar_type

        return SchemaType(type="Record", attributes=attributes)

    elif json_type == "array":
        items = schema.get("items", {})
        element_type = json_schema_to_cedar_type(items)
        return SchemaType(type="Set", element=element_type)

    elif json_type == "string":
        return SchemaType(type="String")

    elif json_type in ["number", "integer"]:
        return SchemaType(type="Long")

    elif json_type == "boolean":
        return SchemaType(type="Boolean")

    else:
        # Default to String for unknown types
        return SchemaType(type="String")


def _agent_tools(agent: Agent) -> list[Tool]:
    """Extract tools from an Agent's card."""
    if agent.card and agent.card.react_card:
        return agent.card.react_card.tools
    return []


def _schema_type_signature(schema_type: SchemaType) -> dict[str, Any]:
    """Return the type shape without required/optional metadata."""
    signature: dict[str, Any] = {
        "type": schema_type.type,
        "name": schema_type.name,
    }
    if schema_type.element is not None:
        signature["element"] = _schema_type_signature(schema_type.element)
    if schema_type.attributes:
        signature["attributes"] = {
            name: _schema_type_signature(attr)
            for name, attr in sorted(schema_type.attributes.items())
        }
    return signature


def _build_pre_tool_use_context(tools: list[Tool]) -> SchemaType:
    """Build the PreToolUse action context type.

    Always includes server-compatible fields:
    - tool: String (tool name)
    - arguments: String (JSON-serialized arguments)

    Optionally includes a typed 'parameters' record merging all tools'
    parameter schemas (local-only extension for typed policy checks).
    """
    context_attributes: dict[str, SchemaType] = {
        "tool": SchemaType(type="String"),
        "arguments": SchemaType(type="String"),
    }

    # Merge typed parameter schemas from all tools as optional extension.
    # Conflicting flat field names are omitted so later tool calls do not
    # fail Cedar schema validation against a first-seen type.
    merged_params: dict[str, SchemaType] = {}
    merged_param_sources: dict[str, str] = {}
    conflicted_params: set[str] = set()
    for tool in tools:
        if tool.parameters_json_schema:
            params_type = openai_json_schema_to_cedar_type(tool.parameters_json_schema)
            if params_type and params_type.type == "Record" and params_type.attributes:
                for attr_name, attr_type in params_type.attributes.items():
                    if attr_name in conflicted_params:
                        continue

                    if attr_name not in merged_params:
                        # Mark all merged fields as optional since they come
                        # from different tools
                        attr_type.required = False
                        merged_params[attr_name] = attr_type
                        merged_param_sources[attr_name] = tool.name
                        continue

                    if _schema_type_signature(
                        merged_params[attr_name]
                    ) != _schema_type_signature(attr_type):
                        previous_tool = merged_param_sources[attr_name]
                        _LOGGER.warning(
                            "Omitting typed Cedar parameter '%s' because tools "
                            "'%s' and '%s' define incompatible types; use "
                            "context.arguments for that field.",
                            attr_name,
                            previous_tool,
                            tool.name,
                        )
                        del merged_params[attr_name]
                        del merged_param_sources[attr_name]
                        conflicted_params.add(attr_name)

    if merged_params:
        context_attributes["parameters"] = SchemaType(
            type="Record", attributes=merged_params, required=False
        )

    return SchemaType(type="Record", attributes=context_attributes)


def _build_tool_output_context(tools: list[Tool]) -> SchemaType:
    """Build the ToolOutput action context type.

    Always includes server-compatible fields:
    - content: String (serialized tool output)

    Optionally includes a typed 'response' record merging all tools'
    response schemas (local-only extension for typed policy checks).
    """
    context_attributes: dict[str, SchemaType] = {
        "content": SchemaType(type="String"),
    }

    # Merge typed response schemas from all tools as optional extension
    merged_response: dict[str, SchemaType] = {}
    for tool in tools:
        if tool.response_json_schema:
            response_type = openai_json_schema_to_cedar_type(tool.response_json_schema)
            if (
                response_type
                and response_type.type == "Record"
                and response_type.attributes
            ):
                for attr_name, attr_type in response_type.attributes.items():
                    if attr_name not in merged_response:
                        attr_type.required = False
                        merged_response[attr_name] = attr_type

    if merged_response:
        context_attributes["response"] = SchemaType(
            type="Record", attributes=merged_response, required=False
        )

    return SchemaType(type="Record", attributes=context_attributes)


def agent_to_cedar_schema(agent: Agent) -> CedarSchema:
    """Convert an Agent to a Cedar Schema aligned with the server model.

    Creates a namespace named after the agent containing:
    - Entity types: Agent, Tool (in Trajectory), Role, Message, Trajectory
    - Actions: PreToolUse (resource: Tool), ToolOutput (resource: Trajectory),
      Prompt (resource: Message)

    The action model matches the server harness so policies are portable
    between local evaluation and remote deployment.
    """

    # Create entity types
    entity_types: dict[str, EntityType] = {
        "Agent": EntityType(
            shape=SchemaType(
                type="Record",
                attributes={
                    "name": SchemaType(type="String"),
                    "provider": SchemaType(type="String"),
                    "tools": SchemaType(
                        type="Set", element=SchemaType(name="Tool", type="Entity")
                    ),
                },
            )
        ),
        "Tool": EntityType(
            shape=SchemaType(
                type="Record",
                attributes={
                    "name": SchemaType(type="String"),
                    "description": SchemaType(type="String"),
                },
            ),
            memberOfTypes=["Trajectory"],
        ),
        "Role": EntityType(enum=["user", "model", "system", "tool"]),
        "Message": EntityType(
            shape=SchemaType(
                type="Record",
                attributes={
                    "content": SchemaType(type="String"),
                    "role": SchemaType(name="Role", type="Entity"),
                },
            ),
            memberOfTypes=["Trajectory"],
        ),
        "Trajectory": EntityType(
            shape=SchemaType(
                type="Record",
                attributes={
                    "step_count": SchemaType(type="Long"),
                },
            )
        ),
    }

    tools = _agent_tools(agent)

    # Create canonical actions aligned with server model
    actions: dict[str, Action] = {
        "PreToolUse": Action(
            appliesTo=AppliesTo(
                principalTypes=["Agent"],
                resourceTypes=["Tool"],
                context=_build_pre_tool_use_context(tools),
            )
        ),
        "ToolOutput": Action(
            appliesTo=AppliesTo(
                principalTypes=["Agent"],
                resourceTypes=["Trajectory"],
                context=_build_tool_output_context(tools),
            )
        ),
        "Prompt": Action(
            appliesTo=AppliesTo(
                principalTypes=["Agent"],
                resourceTypes=["Message"],
            )
        ),
    }

    # Create namespace definition
    namespace_name = agent.id.replace(" ", "_").replace("-", "_")
    namespace_def = NamespaceDefinition(entityTypes=entity_types, actions=actions)

    # Create the schema with the namespace
    schema = CedarSchema(root={namespace_name: namespace_def})

    validate(schema)

    return schema


def load_base_schema() -> str:
    """Load the static sondera.cedarschema from the package.

    Returns:
        The cedarschema file contents as a string.
    """
    return (
        importlib.resources.files("sondera.harness.cedar")
        .joinpath("sondera.cedarschema")
        .read_text(encoding="utf-8")
    )
