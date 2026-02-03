"""Tests for CedarPolicyHarness with a simple coding agent."""

import pytest

from sondera.harness.cedar.harness import CedarPolicyHarness
from sondera.harness.cedar.schema import agent_to_cedar_schema
from sondera.types import (
    Agent,
    Decision,
    Parameter,
    PolicyMetadata,
    Role,
    Stage,
    Tool,
    ToolRequestContent,
    ToolResponseContent,
)


@pytest.fixture
def coding_agent() -> Agent:
    """Create a simple coding agent with several tools."""
    return Agent(
        id="coding-agent-1",
        provider_id="openai",
        name="CodingAgent",
        description="An AI coding assistant",
        instruction="Help users write and execute code",
        tools=[
            Tool(
                id="read_file",
                name="read_file",
                description="Read contents of a file",
                parameters=[
                    Parameter(
                        name="path", description="File path to read", type="string"
                    )
                ],
                parameters_json_schema='{"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}',
                response_json_schema='{"type": "object", "properties": {"content": {"type": "string"}, "size": {"type": "integer"}}}',
            ),
            Tool(
                id="write_file",
                name="write_file",
                description="Write contents to a file",
                parameters=[
                    Parameter(
                        name="path", description="File path to write", type="string"
                    ),
                    Parameter(
                        name="content", description="Content to write", type="string"
                    ),
                ],
                parameters_json_schema='{"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}',
            ),
            Tool(
                id="execute_command",
                name="execute_command",
                description="Execute a shell command",
                parameters=[
                    Parameter(
                        name="command", description="Command to execute", type="string"
                    ),
                    Parameter(
                        name="timeout", description="Timeout in seconds", type="integer"
                    ),
                ],
                parameters_json_schema='{"type": "object", "properties": {"command": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["command"]}',
            ),
            Tool(
                id="search_code",
                name="search_code",
                description="Search for code patterns",
                parameters=[
                    Parameter(
                        name="pattern", description="Search pattern", type="string"
                    ),
                    Parameter(
                        name="directory",
                        description="Directory to search",
                        type="string",
                    ),
                ],
                parameters_json_schema='{"type": "object", "properties": {"pattern": {"type": "string"}, "directory": {"type": "string"}}, "required": ["pattern"]}',
            ),
        ],
    )


class TestCedarPolicyHarnessInit:
    """Tests for CedarPolicyHarness initialization."""

    def test_requires_schema(self):
        """Test that schema is required."""
        with pytest.raises(ValueError, match="schema is required"):
            CedarPolicyHarness(
                policy_set='@id("allow-all") permit(principal, action, resource);',
                schema=None,
            )

    def test_requires_policy_set(self, coding_agent):
        """Test that policy_set is required."""
        schema = agent_to_cedar_schema(coding_agent)
        with pytest.raises(ValueError, match="policy_set is required"):
            CedarPolicyHarness(policy_set=None, schema=schema)

    def test_requires_id_annotation(self, coding_agent):
        """Test that @id annotation is required on all policies."""
        schema = agent_to_cedar_schema(coding_agent)
        with pytest.raises(ValueError, match="missing required @id annotation"):
            CedarPolicyHarness(
                policy_set="permit(principal, action, resource);",
                schema=schema,
            )

    def test_warns_on_duplicate_id(self, coding_agent, caplog):
        """Test that duplicate @id annotations trigger a warning."""
        import logging

        schema = agent_to_cedar_schema(coding_agent)
        policy = """
        @id("duplicate-id")
        permit(principal, action, resource);

        @id("duplicate-id")
        forbid(principal, action == CodingAgent::Action::"read_file", resource);
        """
        with caplog.at_level(logging.WARNING):
            CedarPolicyHarness(policy_set=policy, schema=schema)

        assert "Duplicate policy @id: 'duplicate-id'" in caplog.text

    def test_accepts_policy_string(self, coding_agent):
        """Test that policy can be provided as a string."""
        schema = agent_to_cedar_schema(coding_agent)
        harness = CedarPolicyHarness(
            policy_set='@id("allow-all") permit(principal, action, resource);',
            schema=schema,
        )
        assert harness._namespace == "CodingAgent"

    def test_extracts_namespace_from_schema(self, coding_agent):
        """Test that namespace is correctly extracted from schema."""
        schema = agent_to_cedar_schema(coding_agent)
        harness = CedarPolicyHarness(
            policy_set='@id("allow-all") permit(principal, action, resource);',
            schema=schema,
        )
        assert harness._namespace == "CodingAgent"


class TestCedarPolicyHarnessLifecycle:
    """Tests for harness lifecycle methods."""

    @pytest.mark.asyncio
    async def test_initialize_sets_agent(self, coding_agent):
        """Test that initialize sets the agent."""
        schema = agent_to_cedar_schema(coding_agent)
        harness = CedarPolicyHarness(
            policy_set='@id("allow-all") permit(principal, action, resource);',
            schema=schema,
        )

        await harness.initialize(agent=coding_agent)

        assert harness._agent == coding_agent
        assert harness._trajectory_id is not None
        assert harness._authorizer is not None

    @pytest.mark.asyncio
    async def test_resume_raises_not_implemented(self, coding_agent):
        """Test that resume raises NotImplementedError."""
        schema = agent_to_cedar_schema(coding_agent)
        harness = CedarPolicyHarness(
            policy_set='@id("allow-all") permit(principal, action, resource);',
            schema=schema,
        )

        with pytest.raises(
            NotImplementedError, match="Resuming trajectories is not supported"
        ):
            await harness.resume("test-trajectory-123", agent=coding_agent)

    @pytest.mark.asyncio
    async def test_finalize_clears_trajectory(self, coding_agent):
        """Test that finalize clears the trajectory."""
        schema = agent_to_cedar_schema(coding_agent)
        harness = CedarPolicyHarness(
            policy_set='@id("allow-all") permit(principal, action, resource);',
            schema=schema,
        )

        await harness.initialize(agent=coding_agent)
        await harness.finalize()

        assert harness._trajectory_id is None

    @pytest.mark.asyncio
    async def test_finalize_raises_without_trajectory(self, coding_agent):
        """Test that finalize raises when no trajectory is active."""
        schema = agent_to_cedar_schema(coding_agent)
        harness = CedarPolicyHarness(
            policy_set='@id("allow-all") permit(principal, action, resource);',
            schema=schema,
        )

        with pytest.raises(ValueError, match="No active trajectory"):
            await harness.finalize()


class TestCedarPolicyHarnessPermitAll:
    """Tests for permit-all policy."""

    @pytest.fixture
    def permit_all_harness(self, coding_agent):
        """Create a harness with permit-all policy."""
        schema = agent_to_cedar_schema(coding_agent)
        return CedarPolicyHarness(
            policy_set='@id("allow-all") permit(principal, action, resource);',
            schema=schema,
        )

    @pytest.mark.asyncio
    async def test_allows_read_file(self, permit_all_harness, coding_agent):
        """Test that read_file is allowed."""
        await permit_all_harness.initialize(agent=coding_agent)

        result = await permit_all_harness.adjudicate(
            Stage.PRE_TOOL,
            Role.MODEL,
            ToolRequestContent(tool_id="read_file", args={"path": "/etc/passwd"}),
        )

        assert result.decision == Decision.ALLOW

    @pytest.mark.asyncio
    async def test_allows_write_file(self, permit_all_harness, coding_agent):
        """Test that write_file is allowed."""
        await permit_all_harness.initialize(agent=coding_agent)

        result = await permit_all_harness.adjudicate(
            Stage.PRE_TOOL,
            Role.MODEL,
            ToolRequestContent(
                tool_id="write_file",
                args={"path": "/tmp/test.txt", "content": "hello world"},
            ),
        )

        assert result.decision == Decision.ALLOW

    @pytest.mark.asyncio
    async def test_allows_execute_command(self, permit_all_harness, coding_agent):
        """Test that execute_command is allowed."""
        await permit_all_harness.initialize(agent=coding_agent)

        result = await permit_all_harness.adjudicate(
            Stage.PRE_TOOL,
            Role.MODEL,
            ToolRequestContent(
                tool_id="execute_command",
                args={"command": "ls -la", "timeout": 30},
            ),
        )

        assert result.decision == Decision.ALLOW

    @pytest.mark.asyncio
    async def test_allows_tool_response(self, permit_all_harness, coding_agent):
        """Test that tool responses are allowed."""
        await permit_all_harness.initialize(agent=coding_agent)

        result = await permit_all_harness.adjudicate(
            Stage.POST_TOOL,
            Role.TOOL,
            ToolResponseContent(
                tool_id="read_file",
                response={"content": "file contents", "size": 100},
            ),
        )

        assert result.decision == Decision.ALLOW


class TestCedarPolicyHarnessDenyAll:
    """Tests for deny-all policy."""

    @pytest.fixture
    def deny_all_harness(self, coding_agent):
        """Create a harness with deny-all policy."""
        schema = agent_to_cedar_schema(coding_agent)
        return CedarPolicyHarness(
            policy_set='@id("deny-all") forbid(principal, action, resource);',
            schema=schema,
        )

    @pytest.mark.asyncio
    async def test_denies_all_tools(self, deny_all_harness, coding_agent):
        """Test that all tools are denied."""
        await deny_all_harness.initialize(agent=coding_agent)

        # Test each tool with appropriate args for its schema
        test_cases = [
            ("read_file", {"path": "/test"}),
            ("write_file", {"path": "/test", "content": "test content"}),
            ("execute_command", {"command": "ls"}),
            ("search_code", {"pattern": "test"}),
        ]

        for tool_id, args in test_cases:
            result = await deny_all_harness.adjudicate(
                Stage.PRE_TOOL,
                Role.MODEL,
                ToolRequestContent(tool_id=tool_id, args=args),
            )
            assert result.decision == Decision.DENY, f"{tool_id} should be denied"


class TestCedarPolicyHarnessTypedParameters:
    """Tests for policies using typed parameters."""

    @pytest.mark.asyncio
    async def test_deny_specific_path(self, coding_agent):
        """Test policy that denies specific file paths."""
        schema = agent_to_cedar_schema(coding_agent)
        policy = """
        @id("allow-all")
        permit(principal, action, resource);

        @id("deny-etc-passwd")
        forbid(principal, action == CodingAgent::Action::"read_file", resource)
        when { context.parameters.path == "/etc/passwd" };
        """
        harness = CedarPolicyHarness(policy_set=policy, schema=schema)
        await harness.initialize(agent=coding_agent)

        # Reading /etc/passwd should be denied
        result = await harness.adjudicate(
            Stage.PRE_TOOL,
            Role.MODEL,
            ToolRequestContent(tool_id="read_file", args={"path": "/etc/passwd"}),
        )
        assert result.decision == Decision.DENY

        # Reading other files should be allowed
        result = await harness.adjudicate(
            Stage.PRE_TOOL,
            Role.MODEL,
            ToolRequestContent(tool_id="read_file", args={"path": "/tmp/safe.txt"}),
        )
        assert result.decision == Decision.ALLOW

    @pytest.mark.asyncio
    async def test_deny_dangerous_commands(self, coding_agent):
        """Test policy that denies dangerous commands using pattern matching."""
        schema = agent_to_cedar_schema(coding_agent)
        policy = """
        @id("allow-all")
        permit(principal, action, resource);

        @id("deny-rm-rf")
        forbid(principal, action == CodingAgent::Action::"execute_command", resource)
        when { context.parameters_json like "*rm -rf*" };

        @id("deny-sudo")
        forbid(principal, action == CodingAgent::Action::"execute_command", resource)
        when { context.parameters_json like "*sudo*" };
        """
        harness = CedarPolicyHarness(policy_set=policy, schema=schema)
        await harness.initialize(agent=coding_agent)

        # rm -rf should be denied
        result = await harness.adjudicate(
            Stage.PRE_TOOL,
            Role.MODEL,
            ToolRequestContent(
                tool_id="execute_command",
                args={"command": "rm -rf /", "timeout": 30},
            ),
        )
        assert result.decision == Decision.DENY

        # sudo should be denied
        result = await harness.adjudicate(
            Stage.PRE_TOOL,
            Role.MODEL,
            ToolRequestContent(
                tool_id="execute_command",
                args={"command": "sudo apt install vim", "timeout": 60},
            ),
        )
        assert result.decision == Decision.DENY

        # Safe commands should be allowed
        result = await harness.adjudicate(
            Stage.PRE_TOOL,
            Role.MODEL,
            ToolRequestContent(
                tool_id="execute_command",
                args={"command": "ls -la", "timeout": 10},
            ),
        )
        assert result.decision == Decision.ALLOW

    @pytest.mark.asyncio
    async def test_allow_only_specific_directory(self, coding_agent):
        """Test policy that only allows operations in specific directory."""
        schema = agent_to_cedar_schema(coding_agent)
        policy = """
        @id("allow-read-workspace")
        permit(principal, action == CodingAgent::Action::"read_file", resource)
        when { context.parameters_json like "*\\"/workspace/*" };

        @id("allow-write-workspace")
        permit(principal, action == CodingAgent::Action::"write_file", resource)
        when { context.parameters_json like "*\\"/workspace/*" };

        @id("allow-search-code")
        permit(principal, action == CodingAgent::Action::"search_code", resource);

        @id("allow-execute-command")
        permit(principal, action == CodingAgent::Action::"execute_command", resource);
        """
        harness = CedarPolicyHarness(policy_set=policy, schema=schema)
        await harness.initialize(agent=coding_agent)

        # Reading from /workspace should be allowed
        result = await harness.adjudicate(
            Stage.PRE_TOOL,
            Role.MODEL,
            ToolRequestContent(
                tool_id="read_file", args={"path": "/workspace/src/main.py"}
            ),
        )
        assert result.decision == Decision.ALLOW

        # Reading from outside /workspace should be denied
        result = await harness.adjudicate(
            Stage.PRE_TOOL,
            Role.MODEL,
            ToolRequestContent(tool_id="read_file", args={"path": "/etc/shadow"}),
        )
        assert result.decision == Decision.DENY


class TestCedarPolicyHarnessResponseFiltering:
    """Tests for policies that filter tool responses."""

    @pytest.mark.asyncio
    async def test_deny_response_with_secrets(self, coding_agent):
        """Test policy that denies responses containing secrets."""
        schema = agent_to_cedar_schema(coding_agent)
        policy = """
        @id("allow-all")
        permit(principal, action, resource);

        @id("deny-password")
        forbid(principal, action, resource)
        when { context.response_json like "*password*" };

        @id("deny-api-key")
        forbid(principal, action, resource)
        when { context.response_json like "*api_key*" };

        @id("deny-secret")
        forbid(principal, action, resource)
        when { context.response_json like "*secret*" };
        """
        harness = CedarPolicyHarness(policy_set=policy, schema=schema)
        await harness.initialize(agent=coding_agent)

        # Response with password should be denied
        result = await harness.adjudicate(
            Stage.POST_TOOL,
            Role.TOOL,
            ToolResponseContent(
                tool_id="read_file",
                response={"content": "DB_PASSWORD=secret123", "size": 20},
            ),
        )
        assert result.decision == Decision.DENY

        # Response with api_key should be denied
        result = await harness.adjudicate(
            Stage.POST_TOOL,
            Role.TOOL,
            ToolResponseContent(
                tool_id="read_file",
                response={"content": "api_key=abc123", "size": 15},
            ),
        )
        assert result.decision == Decision.DENY

        # Safe response should be allowed
        result = await harness.adjudicate(
            Stage.POST_TOOL,
            Role.TOOL,
            ToolResponseContent(
                tool_id="read_file",
                response={"content": "Hello World", "size": 11},
            ),
        )
        assert result.decision == Decision.ALLOW


class TestCedarPolicyHarnessNonToolContent:
    """Tests for prompt content handling."""

    @pytest.mark.asyncio
    async def test_allows_prompt_content_with_permit_policy(self, coding_agent):
        """Test that prompt content is evaluated against policies."""
        schema = agent_to_cedar_schema(coding_agent)
        # Policy that allows all actions
        policy = '@id("allow-all") permit(principal, action, resource);'
        harness = CedarPolicyHarness(
            policy_set=policy,
            schema=schema,
        )
        await harness.initialize(agent=coding_agent)

        # Prompt content should be allowed
        from sondera.types import PromptContent

        result = await harness.adjudicate(
            Stage.PRE_MODEL,
            Role.USER,
            PromptContent(text="Write a Python function"),
        )

        assert result.decision == Decision.ALLOW

    @pytest.mark.asyncio
    async def test_denies_prompt_content_with_forbid_policy(self, coding_agent):
        """Test that prompt content can be denied by policy."""
        schema = agent_to_cedar_schema(coding_agent)
        # Policy that denies Prompt action
        policy = '@id("deny-prompt") forbid(principal, action == CodingAgent::Action::"Prompt", resource);'
        harness = CedarPolicyHarness(
            policy_set=policy,
            schema=schema,
        )
        await harness.initialize(agent=coding_agent)

        # Prompt content should be denied
        from sondera.types import PromptContent

        result = await harness.adjudicate(
            Stage.PRE_MODEL,
            Role.USER,
            PromptContent(text="Write a Python function"),
        )

        assert result.decision == Decision.DENY


class TestCedarPolicyHarnessWithoutAgent:
    """Tests for adjudication without an agent configured."""

    @pytest.mark.asyncio
    async def test_raises_without_initialization(self, coding_agent):
        """Test that adjudicate raises RuntimeError when not initialized."""
        schema = agent_to_cedar_schema(coding_agent)
        harness = CedarPolicyHarness(
            policy_set='@id("deny-all") forbid(principal, action, resource);',
            schema=schema,
        )
        # Don't initialize with an agent

        with pytest.raises(
            RuntimeError,
            match="initialize\\(\\) must be called before adjudicate\\(\\)",
        ):
            await harness.adjudicate(
                Stage.PRE_TOOL,
                Role.MODEL,
                ToolRequestContent(tool_id="read_file", args={"path": "/test"}),
            )


class TestCedarPolicyHarnessInternalErrors:
    """Tests for internal error handling."""

    @pytest.mark.asyncio
    async def test_raises_runtime_error_when_policy_not_found(self, coding_agent):
        """Test that RuntimeError is raised when a determining policy is not found."""
        from unittest.mock import MagicMock

        schema = agent_to_cedar_schema(coding_agent)
        harness = CedarPolicyHarness(
            policy_set='@id("deny-all") forbid(principal, action, resource);',
            schema=schema,
        )
        await harness.initialize(agent=coding_agent)

        # Mock the authorizer to return a deny response with a non-existent policy ID
        mock_response = MagicMock()
        mock_response.decision = "Deny"
        mock_response.reason = ["non_existent_policy_id"]

        mock_authorizer = MagicMock()
        mock_authorizer.is_authorized.return_value = mock_response
        mock_authorizer.upsert_entity = MagicMock()
        harness._authorizer = mock_authorizer

        with pytest.raises(
            RuntimeError,
            match="Policy 'non_existent_policy_id' not found in policy set",
        ):
            await harness.adjudicate(
                Stage.PRE_TOOL,
                Role.MODEL,
                ToolRequestContent(tool_id="read_file", args={"path": "/test"}),
            )


class TestCedarPolicyHarnessEscalate:
    """Tests for @escalate annotation support."""

    def test_escalate_on_permit_raises_error(self, coding_agent):
        """Test that @escalate on permit policy raises ValueError."""
        schema = agent_to_cedar_schema(coding_agent)
        policy = """
        @id("bad-policy")
        @escalate
        permit(principal, action, resource);
        """
        with pytest.raises(
            ValueError,
            match="@escalate is only valid on forbid policies",
        ):
            CedarPolicyHarness(policy_set=policy, schema=schema)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "escalate_annotation,expected_escalate_arg",
        [
            ("@escalate", ""),  # naked
            ('@escalate("security-team")', "security-team"),  # with value
        ],
        ids=["naked", "with-value"],
    )
    async def test_escalate_on_forbid_returns_escalate_decision(
        self, coding_agent, escalate_annotation, expected_escalate_arg
    ):
        """Test that @escalate on forbid policy returns ESCALATE decision."""
        schema = agent_to_cedar_schema(coding_agent)
        policy = f"""
        @id("allow-all")
        permit(principal, action, resource);

        @id("escalate-execute")
        {escalate_annotation}
        @reason("Commands require approval")
        forbid(principal, action == CodingAgent::Action::"execute_command", resource);
        """
        harness = CedarPolicyHarness(policy_set=policy, schema=schema)
        await harness.initialize(agent=coding_agent)

        result = await harness.adjudicate(
            Stage.PRE_TOOL,
            Role.MODEL,
            ToolRequestContent(tool_id="execute_command", args={"command": "ls"}),
        )

        assert result.decision == Decision.ESCALATE
        assert result.policies == [
            PolicyMetadata(
                id="escalate-execute",
                description="Commands require approval",
                escalate=True,
                escalate_arg=expected_escalate_arg,
            )
        ]

    @pytest.mark.asyncio
    async def test_mixed_escalate_and_hard_deny_returns_deny(self, coding_agent):
        """Test that hard deny wins over escalate when both match."""
        schema = agent_to_cedar_schema(coding_agent)
        policy = """
        @id("allow-all")
        permit(principal, action, resource);

        @id("escalate-execute")
        @escalate
        forbid(principal, action == CodingAgent::Action::"execute_command", resource);

        @id("hard-deny-execute")
        forbid(principal, action == CodingAgent::Action::"execute_command", resource);
        """
        harness = CedarPolicyHarness(policy_set=policy, schema=schema)
        await harness.initialize(agent=coding_agent)

        result = await harness.adjudicate(
            Stage.PRE_TOOL,
            Role.MODEL,
            ToolRequestContent(tool_id="execute_command", args={"command": "ls"}),
        )

        assert result.decision == Decision.DENY
        # policies should only contain the hard deny policy, not the escalate one
        policy_ids = [p.id for p in result.policies]
        assert "hard-deny-execute" in policy_ids
        assert "escalate-execute" not in policy_ids

    @pytest.mark.asyncio
    async def test_multiple_escalate_policies_returns_all_annotations(
        self, coding_agent
    ):
        """Test that multiple @escalate policies return all annotations."""
        schema = agent_to_cedar_schema(coding_agent)
        policy = """
        @id("allow-all")
        permit(principal, action, resource);

        @id("escalate-1")
        @escalate("team-a")
        @reason("Reason A")
        forbid(principal, action == CodingAgent::Action::"execute_command", resource);

        @id("escalate-2")
        @escalate("team-b")
        @reason("Reason B")
        forbid(principal, action == CodingAgent::Action::"execute_command", resource);
        """
        harness = CedarPolicyHarness(policy_set=policy, schema=schema)
        await harness.initialize(agent=coding_agent)

        result = await harness.adjudicate(
            Stage.PRE_TOOL,
            Role.MODEL,
            ToolRequestContent(tool_id="execute_command", args={"command": "ls"}),
        )

        assert result.decision == Decision.ESCALATE
        # Sort in case policy evaluation order can vary
        assert sorted(result.policies, key=lambda p: p.id) == [
            PolicyMetadata(
                id="escalate-1",
                description="Reason A",
                escalate=True,
                escalate_arg="team-a",
            ),
            PolicyMetadata(
                id="escalate-2",
                description="Reason B",
                escalate=True,
                escalate_arg="team-b",
            ),
        ]

    @pytest.mark.asyncio
    async def test_escalate_does_not_affect_allow(self, coding_agent):
        """Test that allowed actions are not affected by escalate policies."""
        schema = agent_to_cedar_schema(coding_agent)
        policy = """
        @id("allow-all")
        permit(principal, action, resource);

        @id("escalate-execute")
        @escalate
        forbid(principal, action == CodingAgent::Action::"execute_command", resource);
        """
        harness = CedarPolicyHarness(policy_set=policy, schema=schema)
        await harness.initialize(agent=coding_agent)

        # read_file should still be allowed (not affected by execute_command escalate)
        result = await harness.adjudicate(
            Stage.PRE_TOOL,
            Role.MODEL,
            ToolRequestContent(tool_id="read_file", args={"path": "/tmp/test"}),
        )

        assert result.decision == Decision.ALLOW
