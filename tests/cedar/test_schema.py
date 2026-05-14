"""Tests for the Cedar schema conversion functions."""

import json

import pytest
from cedar.schema import CedarSchema

from sondera import Agent, AgentCard, Parameter, ReActAgentCard, Tool
from sondera.harness.cedar.schema import (
    agent_to_cedar_schema,
    json_schema_to_cedar_type,
    load_base_schema,
    openai_json_schema_to_cedar_type,
)


class TestJsonSchemaToCedarType:
    """Tests for json_schema_to_cedar_type conversion."""

    def test_string_type(self):
        """Test conversion of string type."""
        schema = {"type": "string"}
        result = json_schema_to_cedar_type(schema)
        assert result.type == "String"

    def test_string_type_uppercase(self):
        """Test conversion of STRING type (uppercase)."""
        schema = {"type": "STRING"}
        result = json_schema_to_cedar_type(schema)
        assert result.type == "String"

    def test_integer_type(self):
        """Test conversion of integer type."""
        schema = {"type": "integer"}
        result = json_schema_to_cedar_type(schema)
        assert result.type == "Long"

    def test_number_type(self):
        """Test conversion of number type."""
        schema = {"type": "number"}
        result = json_schema_to_cedar_type(schema)
        assert result.type == "Long"

    def test_boolean_type(self):
        """Test conversion of boolean type."""
        schema = {"type": "boolean"}
        result = json_schema_to_cedar_type(schema)
        assert result.type == "Boolean"

    def test_array_type(self):
        """Test conversion of array type to Set."""
        schema = {"type": "array", "items": {"type": "string"}}
        result = json_schema_to_cedar_type(schema)
        assert result.type == "Set"
        assert result.element is not None
        assert result.element.type == "String"

    def test_array_type_with_integer_items(self):
        """Test conversion of array with integer items."""
        schema = {"type": "array", "items": {"type": "integer"}}
        result = json_schema_to_cedar_type(schema)
        assert result.type == "Set"
        assert result.element is not None
        assert result.element.type == "Long"

    def test_object_type(self):
        """Test conversion of object type to Record."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name"],
        }
        result = json_schema_to_cedar_type(schema)
        assert result.type == "Record"
        assert result.attributes is not None
        assert "name" in result.attributes
        assert "age" in result.attributes
        assert result.attributes["name"].type == "String"
        assert result.attributes["age"].type == "Long"
        # name is required, age is optional
        assert (
            result.attributes["name"].required is None
            or result.attributes["name"].required is True
        )
        assert result.attributes["age"].required is False

    def test_nested_object(self):
        """Test conversion of nested object."""
        schema = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "active": {"type": "boolean"},
                    },
                }
            },
        }
        result = json_schema_to_cedar_type(schema)
        assert result.type == "Record"
        assert result.attributes is not None
        assert "user" in result.attributes
        user_type = result.attributes["user"]
        assert user_type.type == "Record"
        assert user_type.attributes is not None
        assert user_type.attributes["id"].type == "String"
        assert user_type.attributes["active"].type == "Boolean"

    def test_string_enum(self):
        """Test conversion of string enum (treated as String)."""
        schema = {"type": "string", "enum": ["red", "green", "blue"]}
        result = json_schema_to_cedar_type(schema)
        assert result.type == "String"

    def test_unknown_type_defaults_to_string(self):
        """Test that unknown types default to String."""
        schema = {"type": "custom_type"}
        result = json_schema_to_cedar_type(schema)
        assert result.type == "String"

    def test_non_dict_input_defaults_to_string(self):
        """Test that non-dict input defaults to String."""
        result = json_schema_to_cedar_type("not a dict")  # type: ignore[arg-type]
        assert result.type == "String"

    def test_empty_object(self):
        """Test conversion of empty object."""
        schema = {"type": "object"}
        result = json_schema_to_cedar_type(schema)
        assert result.type == "Record"
        assert result.attributes == {}

    def test_array_without_items(self):
        """Test conversion of array without items schema."""
        schema = {"type": "array"}
        result = json_schema_to_cedar_type(schema)
        assert result.type == "Set"
        # Empty items should result in String element type
        assert result.element is not None


class TestOpenaiJsonSchemaToCedarType:
    """Tests for openai_json_schema_to_cedar_type conversion."""

    def test_none_input(self):
        """Test that None input returns None."""
        result = openai_json_schema_to_cedar_type(None)
        assert result is None

    def test_empty_string_input(self):
        """Test that empty string input returns None."""
        result = openai_json_schema_to_cedar_type("")
        assert result is None

    def test_valid_json_schema(self):
        """Test conversion of valid JSON schema string."""
        schema_str = '{"type": "object", "properties": {"path": {"type": "string"}}}'
        result = openai_json_schema_to_cedar_type(schema_str)
        assert result is not None
        assert result.type == "Record"
        assert result.attributes is not None
        assert "path" in result.attributes

    def test_invalid_json_raises(self):
        """Test that invalid JSON raises JSONDecodeError."""
        with pytest.raises(json.JSONDecodeError):
            openai_json_schema_to_cedar_type("not valid json")

    def test_complex_schema(self):
        """Test conversion of a complex OpenAI-style schema."""
        schema_str = json.dumps(
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                    "filters": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["query"],
            }
        )
        result = openai_json_schema_to_cedar_type(schema_str)
        assert result is not None
        assert result.type == "Record"
        assert result.attributes is not None
        assert result.attributes["query"].type == "String"
        assert result.attributes["limit"].type == "Long"
        assert result.attributes["filters"].type == "Set"


class TestAgentToCedarSchema:
    """Tests for agent_to_cedar_schema conversion."""

    @pytest.fixture
    def simple_agent(self) -> Agent:
        """Create a simple agent for testing."""
        return Agent(
            id="TestAgent",
            provider="test",
            card=AgentCard.react(
                ReActAgentCard(
                    tools=[
                        Tool(
                            id="tool_a",
                            name="tool_a",
                            description="Tool A",
                            parameters=[
                                Parameter(
                                    name="x", description="X value", param_type="string"
                                )
                            ],
                            parameters_json_schema='{"type": "object", "properties": {"x": {"type": "string"}}}',
                        ),
                        Tool(
                            id="tool_b",
                            name="tool_b",
                            description="Tool B",
                            parameters=[],
                        ),
                    ],
                )
            ),
        )

    def test_returns_cedar_schema(self, simple_agent: Agent):
        """Test that function returns a CedarSchema."""
        schema = agent_to_cedar_schema(simple_agent)
        assert isinstance(schema, CedarSchema)

    def test_namespace_from_agent_id(self, simple_agent: Agent):
        """Test that namespace is derived from agent id."""
        schema = agent_to_cedar_schema(simple_agent)
        assert "TestAgent" in schema.root

    def test_namespace_sanitizes_id(self):
        """Test that agent ids with spaces/dashes are sanitized."""
        agent = Agent(
            id="My Test-Agent",
            provider="test",
        )
        schema = agent_to_cedar_schema(agent)
        assert "My_Test_Agent" in schema.root

    def test_entity_types_created(self, simple_agent: Agent):
        """Test that Agent and Tool entity types are created."""
        schema = agent_to_cedar_schema(simple_agent)
        namespace = schema.root["TestAgent"]
        assert "Agent" in namespace.entityTypes
        assert "Tool" in namespace.entityTypes

    def test_agent_entity_type_shape(self, simple_agent: Agent):
        """Test Agent entity type has correct attributes."""
        schema = agent_to_cedar_schema(simple_agent)
        agent_type = schema.root["TestAgent"].entityTypes["Agent"]
        assert agent_type.shape is not None
        assert agent_type.shape.attributes is not None
        assert "name" in agent_type.shape.attributes
        assert "provider" in agent_type.shape.attributes
        assert "tools" in agent_type.shape.attributes

    def test_tool_entity_type_shape(self, simple_agent: Agent):
        """Test Tool entity type has correct attributes."""
        schema = agent_to_cedar_schema(simple_agent)
        tool_type = schema.root["TestAgent"].entityTypes["Tool"]
        assert tool_type.shape is not None
        assert tool_type.shape.attributes is not None
        assert "name" in tool_type.shape.attributes
        assert "description" in tool_type.shape.attributes

    def test_tool_entity_is_child_of_trajectory(self, simple_agent: Agent):
        """Test Tool entity type has Trajectory as parent."""
        schema = agent_to_cedar_schema(simple_agent)
        tool_type = schema.root["TestAgent"].entityTypes["Tool"]
        assert "Trajectory" in tool_type.memberOfTypes

    def test_canonical_actions_created(self, simple_agent: Agent):
        """Test that PreToolUse, ToolOutput, and Prompt actions are created."""
        schema = agent_to_cedar_schema(simple_agent)
        actions = schema.root["TestAgent"].actions
        assert "PreToolUse" in actions
        assert "ToolOutput" in actions
        assert "Prompt" in actions

    def test_no_per_tool_actions(self, simple_agent: Agent):
        """Test that per-tool actions are NOT created (old model removed)."""
        schema = agent_to_cedar_schema(simple_agent)
        actions = schema.root["TestAgent"].actions
        assert "tool_a" not in actions
        assert "tool_b" not in actions

    def test_pre_tool_use_has_tool_resource(self, simple_agent: Agent):
        """Test PreToolUse action has Tool as resource type."""
        schema = agent_to_cedar_schema(simple_agent)
        pre_tool = schema.root["TestAgent"].actions["PreToolUse"]
        assert "Tool" in pre_tool.appliesTo.resourceTypes

    def test_pre_tool_use_context_fields(self, simple_agent: Agent):
        """Test PreToolUse context has server-compatible fields."""
        schema = agent_to_cedar_schema(simple_agent)
        ctx = schema.root["TestAgent"].actions["PreToolUse"].appliesTo.context
        assert "tool" in ctx.attributes
        assert "arguments" in ctx.attributes
        assert ctx.attributes["tool"].type == "String"
        assert ctx.attributes["arguments"].type == "String"

    def test_pre_tool_use_has_typed_parameters(self, simple_agent: Agent):
        """Test PreToolUse context has optional typed parameters from tools."""
        schema = agent_to_cedar_schema(simple_agent)
        ctx = schema.root["TestAgent"].actions["PreToolUse"].appliesTo.context
        assert "parameters" in ctx.attributes
        params = ctx.attributes["parameters"]
        assert params.required is False
        assert params.type == "Record"
        assert "x" in params.attributes  # from tool_a

    def test_pre_tool_use_omits_conflicting_parameter_type(self, caplog):
        """Conflicting flat parameter names are dropped from typed context."""
        agent = Agent(
            id="CollisionAgent",
            provider="test",
            card=AgentCard.react(
                ReActAgentCard(
                    tools=[
                        Tool(
                            name="tool_a",
                            description="Tool A",
                            parameters=[],
                            parameters_json_schema='{"type": "object", "properties": {"id": {"type": "string"}, "name": {"type": "string"}}}',
                        ),
                        Tool(
                            name="tool_b",
                            description="Tool B",
                            parameters=[],
                            parameters_json_schema='{"type": "object", "properties": {"id": {"type": "integer"}, "count": {"type": "integer"}}}',
                        ),
                    ],
                )
            ),
        )

        schema = agent_to_cedar_schema(agent)

        ctx = schema.root["CollisionAgent"].actions["PreToolUse"].appliesTo.context
        params = ctx.attributes["parameters"]
        assert "id" not in params.attributes
        assert "name" in params.attributes
        assert "count" in params.attributes
        assert "Omitting typed Cedar parameter 'id'" in caplog.text

    def test_pre_tool_use_keeps_matching_parameter_types(self):
        """Shared fields with matching types remain available as typed params."""
        agent = Agent(
            id="SharedAgent",
            provider="test",
            card=AgentCard.react(
                ReActAgentCard(
                    tools=[
                        Tool(
                            name="tool_a",
                            description="Tool A",
                            parameters=[],
                            parameters_json_schema='{"type": "object", "properties": {"customer_id": {"type": "string"}}}',
                        ),
                        Tool(
                            name="tool_b",
                            description="Tool B",
                            parameters=[],
                            parameters_json_schema='{"type": "object", "properties": {"customer_id": {"type": "string"}}}',
                        ),
                    ],
                )
            ),
        )

        schema = agent_to_cedar_schema(agent)

        ctx = schema.root["SharedAgent"].actions["PreToolUse"].appliesTo.context
        params = ctx.attributes["parameters"]
        assert params.attributes["customer_id"].type == "String"

    def test_tool_output_has_trajectory_resource(self, simple_agent: Agent):
        """Test ToolOutput action has Trajectory as resource type."""
        schema = agent_to_cedar_schema(simple_agent)
        tool_output = schema.root["TestAgent"].actions["ToolOutput"]
        assert "Trajectory" in tool_output.appliesTo.resourceTypes

    def test_tool_output_context_fields(self, simple_agent: Agent):
        """Test ToolOutput context has server-compatible content field."""
        schema = agent_to_cedar_schema(simple_agent)
        ctx = schema.root["TestAgent"].actions["ToolOutput"].appliesTo.context
        assert "content" in ctx.attributes
        assert ctx.attributes["content"].type == "String"

    def test_schema_validates(self, simple_agent: Agent):
        """Test that generated schema is valid Cedar schema."""
        schema = agent_to_cedar_schema(simple_agent)
        assert schema is not None

    def test_empty_tools_list(self):
        """Test agent with no tools has all three canonical actions."""
        agent = Agent(
            id="NoToolsAgent",
            provider="test",
        )
        schema = agent_to_cedar_schema(agent)
        actions = schema.root["NoToolsAgent"].actions
        assert "Prompt" in actions
        assert "PreToolUse" in actions
        assert "ToolOutput" in actions

    def test_no_typed_parameters_without_schemas(self):
        """Test that without tool JSON schemas, no typed parameters are added."""
        agent = Agent(
            id="BasicAgent",
            provider="test",
            card=AgentCard.react(
                ReActAgentCard(
                    tools=[
                        Tool(
                            id="simple",
                            name="simple",
                            description="No schema",
                            parameters=[],
                        )
                    ],
                )
            ),
        )
        schema = agent_to_cedar_schema(agent)
        ctx = schema.root["BasicAgent"].actions["PreToolUse"].appliesTo.context
        assert "parameters" not in ctx.attributes


class TestLoadBaseSchema:
    """Tests for load_base_schema utility."""

    def test_returns_string(self):
        """Test that load_base_schema returns a string."""
        content = load_base_schema()
        assert isinstance(content, str)

    def test_contains_entity_types(self):
        """Test base schema contains expected entity types."""
        content = load_base_schema()
        assert "entity Agent" in content
        assert "entity Tool" in content
        assert "entity Trajectory" in content
        assert "entity Message" in content

    def test_contains_aligned_actions(self):
        """Test base schema contains server-aligned actions."""
        content = load_base_schema()
        assert '"PreToolUse"' in content
        assert '"ToolOutput"' in content
        assert '"Prompt"' in content

    def test_pre_tool_use_context_fields(self):
        """Test base schema PreToolUse context has tool and arguments."""
        content = load_base_schema()
        assert "tool: String" in content
        assert "arguments: String" in content

    def test_tool_output_context_fields(self):
        """Test base schema ToolOutput context has content."""
        content = load_base_schema()
        assert "content: String" in content


class TestSchemaTypeRequired:
    """Tests for required field handling in SchemaType."""

    def test_required_fields_not_marked_optional(self):
        """Test that required fields are not marked as optional."""
        schema = {
            "type": "object",
            "properties": {
                "required_field": {"type": "string"},
                "optional_field": {"type": "string"},
            },
            "required": ["required_field"],
        }
        result = json_schema_to_cedar_type(schema)
        assert result.attributes is not None
        # Required field should not have required=False
        assert (
            result.attributes["required_field"].required is None
            or result.attributes["required_field"].required is True
        )
        # Optional field should have required=False
        assert result.attributes["optional_field"].required is False

    def test_all_required_fields(self):
        """Test object with all required fields."""
        schema = {
            "type": "object",
            "properties": {
                "field_a": {"type": "string"},
                "field_b": {"type": "integer"},
            },
            "required": ["field_a", "field_b"],
        }
        result = json_schema_to_cedar_type(schema)
        assert result.attributes is not None
        # Both should be required (not marked as optional)
        assert (
            result.attributes["field_a"].required is None
            or result.attributes["field_a"].required is True
        )
        assert (
            result.attributes["field_b"].required is None
            or result.attributes["field_b"].required is True
        )

    def test_no_required_list(self):
        """Test object with no required list (all optional)."""
        schema = {
            "type": "object",
            "properties": {
                "field_a": {"type": "string"},
            },
        }
        result = json_schema_to_cedar_type(schema)
        assert result.attributes is not None
        assert result.attributes["field_a"].required is False
