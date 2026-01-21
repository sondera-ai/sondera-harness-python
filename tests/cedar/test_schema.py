"""Tests for the Cedar schema conversion functions."""

import json

import pytest
from cedar.schema import CedarSchema

from sondera.harness.cedar.schema import (
    agent_to_cedar_schema,
    json_schema_to_cedar_type,
    openai_json_schema_to_cedar_type,
    tool_to_action,
)
from sondera.types import Agent, Parameter, Tool


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


class TestToolToAction:
    """Tests for tool_to_action conversion."""

    def test_basic_tool(self):
        """Test conversion of a basic tool."""
        tool = Tool(
            id="test_tool",
            name="test_tool",
            description="A test tool",
            parameters=[
                Parameter(name="input", description="Input value", type="string")
            ],
        )
        action = tool_to_action(tool)

        assert action.appliesTo is not None
        assert action.appliesTo.principalTypes == ["Agent"]
        assert action.appliesTo.resourceTypes == ["Trajectory"]

    def test_tool_with_parameters_schema(self):
        """Test tool with parameters JSON schema."""
        tool = Tool(
            id="read_file",
            name="read_file",
            description="Read a file",
            parameters=[Parameter(name="path", description="File path", type="string")],
            parameters_json_schema='{"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}',
        )
        action = tool_to_action(tool)

        assert action.appliesTo is not None
        assert action.appliesTo.context is not None
        context = action.appliesTo.context
        assert context.attributes is not None
        # Should have both typed parameters and string fallback
        assert "parameters" in context.attributes
        assert "parameters_json" in context.attributes
        assert context.attributes["parameters"].type == "Record"

    def test_tool_with_response_schema(self):
        """Test tool with response JSON schema."""
        tool = Tool(
            id="read_file",
            name="read_file",
            description="Read a file",
            parameters=[],
            response_json_schema='{"type": "object", "properties": {"content": {"type": "string"}, "size": {"type": "integer"}}}',
        )
        action = tool_to_action(tool)

        assert action.appliesTo is not None
        assert action.appliesTo.context is not None
        context = action.appliesTo.context
        assert context.attributes is not None
        # Should have both typed response and string fallback
        assert "response" in context.attributes
        assert "response_json" in context.attributes
        assert context.attributes["response"].type == "Record"

    def test_tool_without_schemas(self):
        """Test tool without JSON schemas still has string fallbacks."""
        tool = Tool(
            id="simple_tool",
            name="simple_tool",
            description="A simple tool",
            parameters=[],
        )
        action = tool_to_action(tool)

        assert action.appliesTo is not None
        assert action.appliesTo.context is not None
        context = action.appliesTo.context
        assert context.attributes is not None
        # Should have string fallbacks even without typed schemas
        assert "parameters_json" in context.attributes
        assert "response_json" in context.attributes
        assert context.attributes["parameters_json"].type == "String"
        assert context.attributes["response_json"].type == "String"

    def test_tool_with_simple_type_response(self):
        """Test tool with a simple (non-object) response type."""
        tool = Tool(
            id="get_count",
            name="get_count",
            description="Get a count",
            parameters=[],
            response_json_schema='{"type": "integer"}',
        )
        action = tool_to_action(tool)

        assert action.appliesTo is not None
        assert action.appliesTo.context is not None
        context = action.appliesTo.context
        assert context.attributes is not None
        # Simple types should be wrapped in a Record
        assert "response" in context.attributes
        assert context.attributes["response"].type == "Record"


class TestAgentToCedarSchema:
    """Tests for agent_to_cedar_schema conversion."""

    @pytest.fixture
    def simple_agent(self) -> Agent:
        """Create a simple agent for testing."""
        return Agent(
            id="test-agent-1",
            provider_id="test",
            name="TestAgent",
            description="A test agent",
            instruction="Do testing",
            tools=[
                Tool(
                    id="tool_a",
                    name="tool_a",
                    description="Tool A",
                    parameters=[
                        Parameter(name="x", description="X value", type="string")
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

    def test_returns_cedar_schema(self, simple_agent: Agent):
        """Test that function returns a CedarSchema."""
        schema = agent_to_cedar_schema(simple_agent)
        assert isinstance(schema, CedarSchema)

    def test_namespace_from_agent_name(self, simple_agent: Agent):
        """Test that namespace is derived from agent name."""
        schema = agent_to_cedar_schema(simple_agent)
        assert "TestAgent" in schema.root

    def test_namespace_sanitizes_name(self):
        """Test that agent names with spaces/dashes are sanitized."""
        agent = Agent(
            id="test-1",
            provider_id="test",
            name="My Test-Agent",
            description="Test",
            instruction="Test",
            tools=[],
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
        assert "provider_id" in agent_type.shape.attributes
        assert "tools" in agent_type.shape.attributes

    def test_tool_entity_type_shape(self, simple_agent: Agent):
        """Test Tool entity type has correct attributes."""
        schema = agent_to_cedar_schema(simple_agent)
        tool_type = schema.root["TestAgent"].entityTypes["Tool"]
        assert tool_type.shape is not None
        assert tool_type.shape.attributes is not None
        assert "name" in tool_type.shape.attributes
        assert "description" in tool_type.shape.attributes

    def test_actions_created_for_tools(self, simple_agent: Agent):
        """Test that actions are created for each tool."""
        schema = agent_to_cedar_schema(simple_agent)
        actions = schema.root["TestAgent"].actions
        assert "tool_a" in actions
        assert "tool_b" in actions

    def test_action_names_sanitized(self):
        """Test that tool names with spaces/dashes are sanitized in actions."""
        agent = Agent(
            id="test-1",
            provider_id="test",
            name="TestAgent",
            description="Test",
            instruction="Test",
            tools=[
                Tool(
                    id="my-tool",
                    name="my-special tool",
                    description="A tool",
                    parameters=[],
                )
            ],
        )
        schema = agent_to_cedar_schema(agent)
        actions = schema.root["TestAgent"].actions
        assert "my_special_tool" in actions

    def test_schema_validates(self, simple_agent: Agent):
        """Test that generated schema is valid Cedar schema."""
        # Should not raise an exception
        schema = agent_to_cedar_schema(simple_agent)
        # If we got here without exception, validation passed
        assert schema is not None

    def test_empty_tools_list(self):
        """Test agent with no tools still has Prompt action."""
        agent = Agent(
            id="test-1",
            provider_id="test",
            name="NoToolsAgent",
            description="Test",
            instruction="Test",
            tools=[],
        )
        schema = agent_to_cedar_schema(agent)
        # Should have Prompt action even with no tools
        assert "Prompt" in schema.root["NoToolsAgent"].actions
        assert len(schema.root["NoToolsAgent"].actions) == 1


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
