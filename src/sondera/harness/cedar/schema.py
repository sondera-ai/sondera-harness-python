import json
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
        # Check for enum values which could be treated as specific strings
        if "enum" in schema:
            # For now, just treat as String
            return SchemaType(type="String")
        return SchemaType(type="String")

    elif json_type in ["number", "integer"]:
        return SchemaType(type="Long")

    elif json_type == "boolean":
        return SchemaType(type="Boolean")

    else:
        # Default to String for unknown types
        return SchemaType(type="String")


def tool_to_action(tool: Tool) -> Action:
    """Convert a Tool to a Cedar Action.

    Creates an Action with context containing both parameters and response.
    Both are always included and marked as optional since they may not be
    present in all requests (parameters for PRE_TOOL, response for POST_TOOL).

    If a typed schema is available, it's used. Otherwise, a JSON string fallback
    is provided for flexibility (parameters_json/response_json).
    """
    context_attributes: dict[str, SchemaType] = {}

    # Add parameters to context - use typed schema if available
    if tool.parameters_json_schema:
        params_type = openai_json_schema_to_cedar_type(tool.parameters_json_schema)
        if params_type and params_type.type == "Record" and params_type.attributes:
            # Use the parameters directly as a Record type, mark as optional
            params_type.required = False
            context_attributes["parameters"] = params_type
        elif params_type:
            # Wrap non-record parameters
            wrapped_type = SchemaType(
                type="Record", attributes={"value": params_type}, required=False
            )
            context_attributes["parameters"] = wrapped_type

    # Always add parameters_json as a string fallback
    context_attributes["parameters_json"] = SchemaType(type="String", required=False)

    # Add response to context - use typed schema if available
    if tool.response_json_schema:
        response_type = openai_json_schema_to_cedar_type(tool.response_json_schema)
        if (
            response_type
            and response_type.type == "Record"
            and response_type.attributes
        ):
            # Use the response directly as a Record type, mark as optional
            response_type.required = False
            context_attributes["response"] = response_type
        elif response_type:
            # For simple types, wrap in a Record
            wrapped_type = SchemaType(
                type="Record", attributes={"value": response_type}, required=False
            )
            context_attributes["response"] = wrapped_type

    # Always add response_json as a string fallback
    context_attributes["response_json"] = SchemaType(type="String", required=False)

    # Create context with both typed and string representations
    context = SchemaType(type="Record", attributes=context_attributes)

    # Create the action with appliesTo configuration
    # Default to Agent as principal and Tool as resource
    action = Action(
        appliesTo=AppliesTo(
            principalTypes=["Agent"], resourceTypes=["Trajectory"], context=context
        )
    )

    return action


def agent_to_cedar_schema(agent: Agent) -> CedarSchema:
    """Convert an Agent to a Cedar Schema.

    Creates a namespace named after the agent containing:
    - Default entity types (Agent, Tool)
    - Actions for each tool with parameters/response in context
    """

    # Create entity types
    entity_types: dict[str, EntityType] = {
        "Agent": EntityType(
            shape=SchemaType(
                type="Record",
                attributes={
                    "name": SchemaType(type="String"),
                    "provider_id": SchemaType(type="String"),
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
            )
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

    # Create actions from lean
    actions: dict[str, Action] = {}
    for tool in agent.tools:
        # Use tool name as action name, sanitized for Cedar
        action_name = tool.name.replace(" ", "_").replace("-", "_")
        actions[action_name] = tool_to_action(tool)

    actions["Prompt"] = Action(
        appliesTo=AppliesTo(principalTypes=["Agent"], resourceTypes=["Message"])
    )

    # Create namespace definition
    namespace_name = agent.name.replace(" ", "_").replace("-", "_")
    namespace_def = NamespaceDefinition(entityTypes=entity_types, actions=actions)

    # Create the schema with the namespace
    schema = CedarSchema(root={namespace_name: namespace_def})

    validate(schema)

    return schema
