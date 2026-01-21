"""Unit tests for automatic agent generation functionality in LangGraph SDK."""

import json

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from sondera.langgraph.analyze import (
    _analyze_langchain_tool,
    _build_json_schema_from_function,
    _build_response_schema_from_function,
    _extract_json_schema_from_pydantic,
    _extract_tool_json_schemas,
    _python_type_to_json_schema_type,
    analyze_langchain_tools,
    create_agent_from_langchain_tools,
)
from sondera.types import Agent, Tool


class TestAnalyzeLangChainTool:
    """Test the _analyze_langchain_tool function."""

    def test_analyze_tool_decorated_function(self):
        """Test analyzing a @tool decorated function."""

        @tool
        def sample_tool(location: str, units: str = "celsius") -> str:
            """Get weather for a location.

            Args:
                location: The city or location to get weather for
                units: Temperature units (celsius or fahrenheit)
            """
            return f"Weather in {location}: sunny, {units}"

        result = _analyze_langchain_tool(sample_tool)

        assert isinstance(result, Tool)
        assert result.name == "sample_tool"
        assert "Get weather for a location." in result.description
        assert len(result.parameters) == 2

        # Check location parameter
        location_param = next(p for p in result.parameters if p.name == "location")
        assert location_param.type == "str"
        assert "location" in location_param.description.lower()

        # Check units parameter
        units_param = next(p for p in result.parameters if p.name == "units")
        assert units_param.type == "str"
        assert "units" in units_param.description.lower()

    def test_analyze_tool_with_complex_types(self):
        """Test analyzing a tool with complex type hints."""

        @tool
        def search_restaurants(
            location: str, cuisine: str, max_results: int = 10
        ) -> list[dict]:
            """Search for restaurants in a location.

            Args:
                location: City or area to search in
                cuisine: Type of cuisine (italian, chinese, mexican, etc.)
                max_results: Maximum number of results to return
            """
            return [{"name": "Restaurant 1", "rating": 4.5}]

        result = _analyze_langchain_tool(search_restaurants)

        assert isinstance(result, Tool)
        assert result.name == "search_restaurants"
        # Accept both old-style (typing.List) and new-style (list) type syntax
        assert result.response in ("typing.List[dict]", "list[dict]")
        assert len(result.parameters) == 3

        # Check max_results parameter with int type
        max_results_param = next(
            p for p in result.parameters if p.name == "max_results"
        )
        assert max_results_param.type == "int"

    def test_analyze_tool_without_docstring(self):
        """Test analyzing a tool without docstring."""

        @tool("simple_tool", description="Simple tool for testing")
        def simple_tool(param: str) -> str:
            return f"Result: {param}"

        result = _analyze_langchain_tool(simple_tool)

        assert isinstance(result, Tool)
        assert result.name == "simple_tool"
        assert result.description == "Simple tool for testing"
        assert len(result.parameters) == 1

        param = result.parameters[0]
        assert param.name == "param"
        assert param.type == "str"

    def test_analyze_tool_with_optional_types(self):
        """Test analyzing a tool with Optional type hints."""

        @tool
        def optional_tool(
            required_param: str, optional_param: str | None = None
        ) -> str:
            """Tool with optional parameter.

            Args:
                required_param: Required parameter
                optional_param: Optional parameter
            """
            return f"Result: {required_param}, {optional_param}"

        result = _analyze_langchain_tool(optional_tool)

        assert len(result.parameters) == 2

        required_param = next(
            p for p in result.parameters if p.name == "required_param"
        )
        assert required_param.type == "str"

        optional_param = next(
            p for p in result.parameters if p.name == "optional_param"
        )
        # Accept both old-style (Union/Optional) and new-style (X | None) type syntax
        assert (
            "Union" in optional_param.type
            or "Optional" in optional_param.type
            or "|" in optional_param.type
        )


class TestAnalyzeLangChainTools:
    """Test the analyze_langchain_tools function."""

    def test_analyze_multiple_tools(self):
        """Test analyzing multiple LangChain tools."""

        @tool
        def tool1(param1: str) -> str:
            """First tool."""
            return param1

        @tool
        def tool2(param2: int) -> int:
            """Second tool."""
            return param2

        tools = [tool1, tool2]
        result = analyze_langchain_tools(
            tools=tools,
            agent_id="test-agent",
            agent_name="Test Agent",
            agent_description="Test agent",
            provider_id="langchain",
        )

        assert isinstance(result, Agent)
        assert len(result.tools) == 2
        assert result.tools[0].name == "tool1"
        assert result.tools[1].name == "tool2"

    def test_analyze_empty_tools_list(self):
        """Test analyzing empty tools list."""
        result = analyze_langchain_tools(
            tools=[],
            agent_id="empty-agent",
            agent_name="Empty Agent",
            agent_description="Empty agent",
            provider_id="langchain",
        )
        assert isinstance(result, Agent)
        assert len(result.tools) == 0


class TestCreateAgentFromLangChainTools:
    """Test the create_agent_from_langchain_tools function."""

    def test_create_agent_basic(self):
        """Test basic agent creation from LangChain tools."""

        @tool
        def test_tool(param: str) -> str:
            """Test tool."""
            return param

        agent = create_agent_from_langchain_tools(
            tools=[test_tool],
            agent_id="test-agent",
            agent_name="Test Agent",
            agent_description="Test agent description",
            provider_id="langchain",
        )

        assert isinstance(agent, Agent)
        assert agent.id == "test-agent"
        assert agent.name == "Test Agent"
        assert agent.description == "Test agent description"
        assert agent.provider_id == "langchain"
        assert (
            agent.instruction
            == "Use the available tools to assist users effectively and safely."
        )
        assert len(agent.tools) == 1
        assert agent.tools[0].name == "test_tool"

    def test_create_agent_with_manual_instruction(self):
        """Test agent creation with manual instruction."""

        @tool
        def test_tool(param: str) -> str:
            """Test tool."""
            return param

        manual_instruction = "Custom instruction for the agent"
        agent = create_agent_from_langchain_tools(
            tools=[test_tool],
            agent_id="test-agent",
            agent_name="Test Agent",
            agent_description="Test agent description",
            agent_instruction=manual_instruction,
            provider_id="langchain",
        )

        assert agent.instruction == manual_instruction

    def test_create_agent_with_system_prompt_func(self):
        """Test agent creation with system prompt function."""

        @tool
        def test_tool(param: str) -> str:
            """Test tool."""
            return param

        def make_system_prompt() -> str:
            return "You are a helpful test assistant. Use the available tools to help users."

        agent = create_agent_from_langchain_tools(
            tools=[test_tool],
            agent_id="test-agent",
            agent_name="Test Agent",
            agent_description="Test agent description",
            provider_id="langchain",
            system_prompt_func=make_system_prompt,
        )

        assert (
            agent.instruction
            == "You are a helpful test assistant. Use the available tools to help users."
        )

    def test_create_agent_manual_instruction_overrides_system_prompt(self):
        """Test that manual instruction overrides system prompt function."""

        @tool
        def test_tool(param: str) -> str:
            """Test tool."""
            return param

        def make_system_prompt() -> str:
            return "System prompt instruction"

        manual_instruction = "Manual instruction"
        agent = create_agent_from_langchain_tools(
            tools=[test_tool],
            agent_id="test-agent",
            agent_name="Test Agent",
            agent_description="Test agent description",
            agent_instruction=manual_instruction,
            provider_id="langchain",
            system_prompt_func=make_system_prompt,
        )

        # Manual instruction should take precedence
        assert agent.instruction == manual_instruction

    def test_create_agent_with_system_prompt_func_exception(self):
        """Test agent creation when system prompt function raises exception."""

        @tool
        def test_tool(param: str) -> str:
            """Test tool."""
            return param

        def failing_system_prompt() -> str:
            raise ValueError("System prompt function failed")

        agent = create_agent_from_langchain_tools(
            tools=[test_tool],
            agent_id="test-agent",
            agent_name="Test Agent",
            agent_description="Test agent description",
            provider_id="langchain",
            system_prompt_func=failing_system_prompt,
        )

        # Should fall back to default instruction
        assert (
            agent.instruction
            == "Use the available tools to assist users effectively and safely."
        )

    def test_create_agent_with_multiple_tools(self):
        """Test agent creation with multiple tools."""

        @tool
        def tool1(param1: str) -> str:
            """First tool."""
            return param1

        @tool
        def tool2(param2: int) -> int:
            """Second tool."""
            return param2

        @tool
        def tool3(param3: float, optional: str = "default") -> float:
            """Third tool with optional parameter."""
            return param3

        agent = create_agent_from_langchain_tools(
            tools=[tool1, tool2, tool3],
            agent_id="multi-tool-agent",
            agent_name="Multi Tool Agent",
            agent_description="Agent with multiple tools",
            provider_id="langchain",
        )

        assert len(agent.tools) == 3
        assert agent.tools[0].name == "tool1"
        assert agent.tools[1].name == "tool2"
        assert agent.tools[2].name == "tool3"

        # Check that tool3 has the optional parameter
        tool3_params = agent.tools[2].parameters
        assert len(tool3_params) == 2
        optional_param = next(p for p in tool3_params if p.name == "optional")
        assert optional_param.type == "str"

    def test_create_agent_with_empty_tools_list(self):
        """Test agent creation with empty tools list."""
        agent = create_agent_from_langchain_tools(
            tools=[],
            agent_id="empty-agent",
            agent_name="Empty Agent",
            agent_description="Agent with no tools",
            provider_id="langchain",
        )

        assert len(agent.tools) == 0
        assert (
            agent.instruction
            == "Use the available tools to assist users effectively and safely."
        )

    def test_create_agent_preserves_source_code(self):
        """Test that agent creation preserves source code for observability."""
        from langchain_core.tools import tool as langchain_tool

        @langchain_tool
        def documented_tool(location: str, units: str = "celsius") -> str:
            """Get weather information for a location.

            Args:
                location: The city or location to get weather for
                units: Temperature units (celsius or fahrenheit)
            """
            # This is the implementation
            weather_data = f"Weather in {location}: sunny, {units}"
            return weather_data

        agent = create_agent_from_langchain_tools(
            tools=[documented_tool],
            agent_id="weather-agent",
            agent_name="Weather Agent",
            agent_description="Weather information agent",
            provider_id="langchain",
        )

        analyzed_tool = agent.tools[0]
        assert analyzed_tool.source is not None
        assert len(analyzed_tool.source.code) > 0
        assert "weather_data" in analyzed_tool.source.code
        assert analyzed_tool.source.language == "python"

    def test_system_prompt_func_type_validation(self):
        """Test that system_prompt_func must be callable."""
        from langchain_core.tools import tool as langchain_tool

        @langchain_tool
        def test_tool(param: str) -> str:
            """Test tool."""
            return param

        # This should work fine - the function will handle non-callable gracefully
        agent = create_agent_from_langchain_tools(
            tools=[test_tool],
            agent_id="test-agent",
            agent_name="Test Agent",
            agent_description="Test agent description",
            provider_id="langchain",
            system_prompt_func="not a function",  # type: ignore
        )

        # Should fall back to default instruction
        assert (
            agent.instruction
            == "Use the available tools to assist users effectively and safely."
        )


class TestJsonSchemaExtraction:
    """Test JSON schema extraction functionality."""

    def test_python_type_to_json_schema_type(self):
        """Test Python type to JSON schema type conversion."""
        assert _python_type_to_json_schema_type("str") == "string"
        assert _python_type_to_json_schema_type("int") == "integer"
        assert _python_type_to_json_schema_type("float") == "number"
        assert _python_type_to_json_schema_type("bool") == "boolean"
        assert _python_type_to_json_schema_type("list") == "array"
        assert _python_type_to_json_schema_type("dict") == "object"
        assert _python_type_to_json_schema_type("None") == "null"
        assert _python_type_to_json_schema_type("NoneType") == "null"
        # Unknown types default to string
        assert _python_type_to_json_schema_type("UnknownType") == "string"

    def test_extract_json_schema_from_pydantic_model(self):
        """Test extracting JSON schema from a Pydantic model."""

        class TestModel(BaseModel):
            name: str = Field(description="The name field")
            count: int = Field(description="The count field")
            active: bool = Field(default=True, description="Active status")

        schema_json = _extract_json_schema_from_pydantic(TestModel)
        assert schema_json is not None

        schema = json.loads(schema_json)
        assert schema["type"] == "object"
        assert "name" in schema["properties"]
        assert "count" in schema["properties"]
        assert "active" in schema["properties"]
        assert schema["properties"]["name"]["type"] == "string"
        assert schema["properties"]["count"]["type"] == "integer"
        assert schema["properties"]["active"]["type"] == "boolean"

    def test_build_json_schema_from_function(self):
        """Test building JSON schema from function signature."""

        def sample_func(name: str, count: int, active: bool = True) -> str:
            """Sample function.

            name: The name parameter
            count: The count parameter
            """
            return "result"

        schema_json = _build_json_schema_from_function(sample_func)
        assert schema_json is not None

        schema = json.loads(schema_json)
        assert schema["type"] == "object"
        assert "name" in schema["properties"]
        assert "count" in schema["properties"]
        assert "active" in schema["properties"]
        assert schema["properties"]["name"]["type"] == "string"
        assert schema["properties"]["count"]["type"] == "integer"
        assert schema["properties"]["active"]["type"] == "boolean"
        # name and count are required (no default), active is optional
        assert "name" in schema["required"]
        assert "count" in schema["required"]
        assert "active" not in schema["required"]

    def test_build_response_schema_from_function(self):
        """Test building response schema from function return type."""

        def string_return() -> str:
            return "result"

        def int_return() -> int:
            return 42

        def dict_return() -> dict:
            return {}

        str_schema = _build_response_schema_from_function(string_return)
        assert str_schema is not None
        str_data = json.loads(str_schema)
        assert str_data["type"] == "string"

        int_schema = _build_response_schema_from_function(int_return)
        assert int_schema is not None
        int_data = json.loads(int_schema)
        assert int_data["type"] == "integer"

        dict_schema = _build_response_schema_from_function(dict_return)
        assert dict_schema is not None
        dict_data = json.loads(dict_schema)
        assert dict_data["type"] == "object"

    def test_build_response_schema_returns_none_for_any(self):
        """Test that response schema returns None for Any return type."""
        from typing import Any

        def any_return() -> Any:
            return None

        schema = _build_response_schema_from_function(any_return)
        assert schema is None

    def test_tool_decorated_function_has_json_schema(self):
        """Test that @tool decorated functions include JSON schemas."""

        @tool
        def search(query: str, max_results: int = 10) -> str:
            """Search the web.

            query: The search query
            max_results: Maximum results to return
            """
            return f"Results for: {query}"

        result = _analyze_langchain_tool(search)

        assert result.parameters_json_schema is not None
        assert result.response_json_schema is not None

        # Verify parameters schema structure
        params_schema = json.loads(result.parameters_json_schema)
        assert "properties" in params_schema
        assert "query" in params_schema["properties"]

        # Verify response schema structure
        response_schema = json.loads(result.response_json_schema)
        assert response_schema["type"] == "string"

    def test_basetool_with_args_schema_has_json_schema(self):
        """Test that BaseTool with args_schema includes JSON schema."""

        class CalculatorInput(BaseModel):
            operation: str = Field(description="The operation to perform")
            a: float = Field(description="First number")
            b: float = Field(description="Second number")

        class CalculatorTool(BaseTool):
            name: str = "calculator"
            description: str = "Perform calculations"
            args_schema: type[BaseModel] = CalculatorInput

            def _run(self, operation: str, a: float, b: float) -> str:
                return f"{a} {operation} {b}"

        calc_tool = CalculatorTool()
        result = _analyze_langchain_tool(calc_tool)

        assert result.parameters_json_schema is not None

        params_schema = json.loads(result.parameters_json_schema)
        assert params_schema["type"] == "object"
        assert "operation" in params_schema["properties"]
        assert "a" in params_schema["properties"]
        assert "b" in params_schema["properties"]
        assert params_schema["properties"]["a"]["type"] == "number"
        assert params_schema["properties"]["b"]["type"] == "number"

    def test_agent_tools_have_json_schemas(self):
        """Test that agent tools include JSON schemas when analyzed."""

        @tool
        def tool1(param: str) -> str:
            """First tool."""
            return param

        @tool
        def tool2(count: int, enabled: bool = True) -> int:
            """Second tool."""
            return count

        agent = analyze_langchain_tools(
            tools=[tool1, tool2],
            agent_id="test-agent",
            agent_name="Test Agent",
            agent_description="Test agent",
            provider_id="langchain",
        )

        # Both tools should have JSON schemas
        for tool_obj in agent.tools:
            assert tool_obj.parameters_json_schema is not None
            # Verify it's valid JSON
            params_schema = json.loads(tool_obj.parameters_json_schema)
            assert "properties" in params_schema

    def test_extract_tool_json_schemas_handles_none_gracefully(self):
        """Test that schema extraction handles None/missing attributes gracefully."""
        params_schema, response_schema = _extract_tool_json_schemas(None)
        assert params_schema is None
        assert response_schema is None
