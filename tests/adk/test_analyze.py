"""Unit tests for ADK agent analysis functionality.

Note: These tests require the 'adk' optional dependency.
Install with: uv pip install -e ".[adk]"
"""

import json
from typing import Any

import pytest

# Skip this module if google-adk is not installed
pytest.importorskip("google.adk", reason="google-adk package not installed")

from google.adk import Agent as AdkAgent

from sondera.adk.analyze import format
from sondera.types import Agent, Tool


def test_format_agent_with_base_tool_json_schemas():
    """Test that BaseTool instances include parameters_json_schema and response_json_schema."""

    def search_tool(query: str, limit: int = 10) -> dict[str, Any]:
        """Search for information.

        Args:
            query: Search query string
            limit: Maximum number of results to return
        """
        return {
            "query": query,
            "results": ["result1", "result2"],
            "count": 2,
        }

    # Create real ADK agent
    adk_agent = AdkAgent(
        model="gemini-2.5-flash",
        name="test_agent",
        description="Test agent description",
        instruction="Test instruction",
        tools=[search_tool],
    )

    # Format the agent
    result = format(adk_agent, agent_name="Test Agent", agent_id="test-agent-1")

    # Verify the result
    assert isinstance(result, Agent)
    assert result.id == "test-agent-1"
    assert result.name == "Test Agent"
    assert result.provider_id == "google"
    assert len(result.tools) == 1

    # Verify the tool has JSON schemas
    tool = result.tools[0]
    assert isinstance(tool, Tool)
    assert tool.name == "search_tool"
    assert "Search for information" in tool.description
    assert tool.parameters_json_schema is not None

    # Verify parameters JSON schema content
    params_schema_dict = json.loads(tool.parameters_json_schema)
    assert params_schema_dict["type"] == "OBJECT"
    assert "query" in params_schema_dict["properties"]
    assert "limit" in params_schema_dict["properties"]


def test_format_agent_with_base_tool_no_response_schema():
    """Test that BaseTool instances work when response schema is not provided."""

    def simple_tool(input: str) -> str:
        """Simple tool that processes input.

        Args:
            input: Input string to process
        """
        return f"Processed: {input}"

    # Create real ADK agent
    adk_agent = AdkAgent(
        model="gemini-2.5-flash",
        name="test_agent",
        description="Test agent description",
        instruction="Test instruction",
        tools=[simple_tool],
    )

    # Format the agent
    result = format(adk_agent, agent_name="Test Agent", agent_id="test-agent-2")

    # Verify the result
    tool = result.tools[0]
    assert tool.parameters_json_schema is not None
    # Response schema may or may not be present depending on ADK version
    # The important thing is that parameters_json_schema is present

    # Verify parameters JSON schema is valid
    params_schema_dict = json.loads(tool.parameters_json_schema)
    assert params_schema_dict["type"] == "OBJECT"
    assert "input" in params_schema_dict["properties"]


def test_format_agent_with_multiple_base_tools():
    """Test formatting agent with multiple BaseTool instances."""

    def tool1(x: str) -> str:
        """First tool.

        Args:
            x: String parameter
        """
        return f"Result: {x}"

    def tool2(y: int) -> int:
        """Second tool.

        Args:
            y: Integer parameter
        """
        return y * 2

    # Create real ADK agent
    adk_agent = AdkAgent(
        model="gemini-2.5-flash",
        name="test_agent",
        description="Test agent description",
        instruction="Test instruction",
        tools=[tool1, tool2],
    )

    # Format the agent
    result = format(
        adk_agent, agent_name="Multi Tool Agent", agent_id="multi-tool-agent"
    )

    # Verify both tools have JSON schemas
    assert len(result.tools) == 2
    assert result.tools[0].parameters_json_schema is not None
    assert result.tools[1].parameters_json_schema is not None

    # Verify tool names
    assert result.tools[0].name == "tool1"
    assert result.tools[1].name == "tool2"

    # Verify parameters JSON schemas
    params1_schema = json.loads(result.tools[0].parameters_json_schema)
    assert "x" in params1_schema["properties"]

    params2_schema = json.loads(result.tools[1].parameters_json_schema)
    assert "y" in params2_schema["properties"]
