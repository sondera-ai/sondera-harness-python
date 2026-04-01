"""Tests for CedarPolicyHarness with a simple coding agent."""

import json

import pytest

from sondera import (
    Agent,
    AgentCard,
    Decision,
    Event,
    Parameter,
    Prompt,
    PromptRole,
    ReActAgentCard,
    Tool,
    ToolCall,
    ToolOutput,
)
from sondera.harness.cedar.harness import CedarPolicyHarness
from sondera.harness.cedar.schema import agent_to_cedar_schema


@pytest.fixture
def coding_agent() -> Agent:
    """Create a simple coding agent with several tools."""
    return Agent(
        id="CodingAgent",
        provider="openai",
        card=AgentCard.react(
            ReActAgentCard(
                system_instruction="Help users write and execute code",
                tools=[
                    Tool(
                        name="read_file",
                        description="Read contents of a file",
                        parameters=[
                            Parameter(
                                name="path",
                                description="File path to read",
                                param_type="string",
                            )
                        ],
                        parameters_json_schema='{"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}',
                        response_json_schema='{"type": "object", "properties": {"content": {"type": "string"}, "size": {"type": "integer"}}}',
                    ),
                    Tool(
                        name="write_file",
                        description="Write contents to a file",
                        parameters=[
                            Parameter(
                                name="path",
                                description="File path to write",
                                param_type="string",
                            ),
                            Parameter(
                                name="content",
                                description="Content to write",
                                param_type="string",
                            ),
                        ],
                        parameters_json_schema='{"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}',
                    ),
                    Tool(
                        name="execute_command",
                        description="Execute a shell command",
                        parameters=[
                            Parameter(
                                name="command",
                                description="Command to execute",
                                param_type="string",
                            ),
                            Parameter(
                                name="timeout",
                                description="Timeout in seconds",
                                param_type="integer",
                            ),
                        ],
                        parameters_json_schema='{"type": "object", "properties": {"command": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["command"]}',
                    ),
                    Tool(
                        name="search_code",
                        description="Search for code patterns",
                        parameters=[
                            Parameter(
                                name="pattern",
                                description="Search pattern",
                                param_type="string",
                            ),
                            Parameter(
                                name="directory",
                                description="Directory to search",
                                param_type="string",
                            ),
                        ],
                        parameters_json_schema='{"type": "object", "properties": {"pattern": {"type": "string"}, "directory": {"type": "string"}}, "required": ["pattern"]}',
                    ),
                ],
            )
        ),
    )


def _tool_call_event(harness, tool_name: str, arguments: dict) -> Event:
    """Helper to build a ToolCall event."""
    return Event(
        agent=harness.agent,
        trajectory_id=harness.trajectory_id,
        event=ToolCall(tool=tool_name, arguments=arguments),
    )


def _tool_output_event(harness, tool_name: str, response: dict | str) -> Event:
    """Helper to build a ToolOutput event."""
    output = response if isinstance(response, str) else json.dumps(response)
    return Event(
        agent=harness.agent,
        trajectory_id=harness.trajectory_id,
        event=ToolOutput.from_success(tool_name, output),
    )


def _prompt_event(harness, role: PromptRole, text: str) -> Event:
    """Helper to build a Prompt event."""
    return Event(
        agent=harness.agent,
        trajectory_id=harness.trajectory_id,
        event=Prompt(role=role, content=text),
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
    async def test_resume_restores_trajectory(self, coding_agent):
        """Test that resume restores an existing trajectory from storage."""
        schema = agent_to_cedar_schema(coding_agent)
        harness = CedarPolicyHarness(
            policy_set='@id("allow-all") permit(principal, action, resource);',
            schema=schema,
        )

        # Initialize and adjudicate to create a trajectory with steps
        await harness.initialize(agent=coding_agent)
        tid = harness.trajectory_id
        assert tid is not None
        await harness.adjudicate(
            _tool_call_event(harness, "read_file", {"path": "/tmp/test.txt"})
        )
        await harness.finalize()

        # Resume should restore trajectory and step count
        await harness.resume(tid, agent=coding_agent)
        assert harness.trajectory_id == tid
        assert harness._trajectory_step_count == 1

    @pytest.mark.asyncio
    async def test_resume_unknown_trajectory_raises(self, coding_agent):
        """Test that resume raises ValueError for unknown trajectory."""
        schema = agent_to_cedar_schema(coding_agent)
        harness = CedarPolicyHarness(
            policy_set='@id("allow-all") permit(principal, action, resource);',
            schema=schema,
        )

        with pytest.raises(ValueError, match="not found in storage"):
            await harness.resume("nonexistent-id", agent=coding_agent)

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

    @pytest.mark.asyncio
    async def test_fail_marks_trajectory_failed_and_clears(self, coding_agent):
        """fail() should write a Failed status and clear the active trajectory."""
        from unittest.mock import MagicMock

        from sondera.harness.trajectory.abc import TrajectoryStorage
        from sondera.types import TrajectoryStatus

        mock_storage = MagicMock(spec=TrajectoryStorage)
        schema = agent_to_cedar_schema(coding_agent)
        harness = CedarPolicyHarness(
            policy_set='@id("allow-all") permit(principal, action, resource);',
            schema=schema,
            storage=mock_storage,
        )

        await harness.initialize(agent=coding_agent)
        tid = harness._trajectory_id
        assert tid is not None

        await harness.fail(reason="test failure")

        assert harness._trajectory_id is None
        assert harness._trajectory_step_count == 0
        mock_storage.finalize_trajectory.assert_called_once_with(
            coding_agent.id,
            tid,
            status=TrajectoryStatus.Failed,
        )

    @pytest.mark.asyncio
    async def test_fail_raises_without_active_trajectory(self, coding_agent):
        """fail() without an active trajectory should raise ValueError."""
        schema = agent_to_cedar_schema(coding_agent)
        harness = CedarPolicyHarness(
            policy_set='@id("allow-all") permit(principal, action, resource);',
            schema=schema,
        )

        with pytest.raises(ValueError, match="No active trajectory"):
            await harness.fail(reason="crash")

    @pytest.mark.asyncio
    async def test_fail_clears_trajectory_even_if_storage_raises(self, coding_agent):
        """trajectory_id must be cleared even when storage.finalize_trajectory raises."""
        from unittest.mock import MagicMock

        from sondera.harness.trajectory.abc import TrajectoryStorage

        mock_storage = MagicMock(spec=TrajectoryStorage)
        mock_storage.finalize_trajectory.side_effect = OSError("disk full")
        schema = agent_to_cedar_schema(coding_agent)
        harness = CedarPolicyHarness(
            policy_set='@id("allow-all") permit(principal, action, resource);',
            schema=schema,
            storage=mock_storage,
        )

        await harness.initialize(agent=coding_agent)

        with pytest.raises(OSError, match="disk full"):
            await harness.fail(reason="crash")

        # trajectory_id must be cleared despite the storage error
        assert harness._trajectory_id is None
        assert harness._trajectory_step_count == 0


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
            _tool_call_event(permit_all_harness, "read_file", {"path": "/etc/passwd"})
        )

        assert result.decision == Decision.Allow

    @pytest.mark.asyncio
    async def test_allows_write_file(self, permit_all_harness, coding_agent):
        """Test that write_file is allowed."""
        await permit_all_harness.initialize(agent=coding_agent)

        result = await permit_all_harness.adjudicate(
            _tool_call_event(
                permit_all_harness,
                "write_file",
                {"path": "/tmp/test.txt", "content": "hello world"},
            )
        )

        assert result.decision == Decision.Allow

    @pytest.mark.asyncio
    async def test_allows_execute_command(self, permit_all_harness, coding_agent):
        """Test that execute_command is allowed."""
        await permit_all_harness.initialize(agent=coding_agent)

        result = await permit_all_harness.adjudicate(
            _tool_call_event(
                permit_all_harness,
                "execute_command",
                {"command": "ls -la", "timeout": 30},
            )
        )

        assert result.decision == Decision.Allow

    @pytest.mark.asyncio
    async def test_allows_tool_response(self, permit_all_harness, coding_agent):
        """Test that tool responses are allowed."""
        await permit_all_harness.initialize(agent=coding_agent)

        result = await permit_all_harness.adjudicate(
            _tool_output_event(
                permit_all_harness,
                "read_file",
                {"content": "file contents", "size": 100},
            )
        )

        assert result.decision == Decision.Allow


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

        for tool_name, args in test_cases:
            result = await deny_all_harness.adjudicate(
                _tool_call_event(deny_all_harness, tool_name, args)
            )
            assert result.decision == Decision.Deny, f"{tool_name} should be denied"


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
            _tool_call_event(harness, "read_file", {"path": "/etc/passwd"})
        )
        assert result.decision == Decision.Deny

        # Reading other files should be allowed
        result = await harness.adjudicate(
            _tool_call_event(harness, "read_file", {"path": "/tmp/safe.txt"})
        )
        assert result.decision == Decision.Allow

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
            _tool_call_event(
                harness,
                "execute_command",
                {"command": "rm -rf /", "timeout": 30},
            )
        )
        assert result.decision == Decision.Deny

        # sudo should be denied
        result = await harness.adjudicate(
            _tool_call_event(
                harness,
                "execute_command",
                {"command": "sudo apt install vim", "timeout": 60},
            )
        )
        assert result.decision == Decision.Deny

        # Safe commands should be allowed
        result = await harness.adjudicate(
            _tool_call_event(
                harness,
                "execute_command",
                {"command": "ls -la", "timeout": 10},
            )
        )
        assert result.decision == Decision.Allow

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
            _tool_call_event(harness, "read_file", {"path": "/workspace/src/main.py"})
        )
        assert result.decision == Decision.Allow

        # Reading from outside /workspace should be denied
        result = await harness.adjudicate(
            _tool_call_event(harness, "read_file", {"path": "/etc/shadow"})
        )
        assert result.decision == Decision.Deny


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
            _tool_output_event(
                harness,
                "read_file",
                {"content": "DB_PASSWORD=secret123", "size": 20},
            )
        )
        assert result.decision == Decision.Deny

        # Response with api_key should be denied
        result = await harness.adjudicate(
            _tool_output_event(
                harness,
                "read_file",
                {"content": "api_key=abc123", "size": 15},
            )
        )
        assert result.decision == Decision.Deny

        # Safe response should be allowed
        result = await harness.adjudicate(
            _tool_output_event(
                harness,
                "read_file",
                {"content": "Hello World", "size": 11},
            )
        )
        assert result.decision == Decision.Allow


class TestCedarPolicyHarnessNonToolContent:
    """Tests for prompt content handling."""

    @pytest.mark.asyncio
    async def test_allows_prompt_content_with_permit_policy(self, coding_agent):
        """Test that prompt content is evaluated against policies."""
        schema = agent_to_cedar_schema(coding_agent)
        policy = '@id("allow-all") permit(principal, action, resource);'
        harness = CedarPolicyHarness(policy_set=policy, schema=schema)
        await harness.initialize(agent=coding_agent)

        result = await harness.adjudicate(
            _prompt_event(harness, PromptRole.User, "Write a Python function")
        )

        assert result.decision == Decision.Allow

    @pytest.mark.asyncio
    async def test_denies_prompt_content_with_forbid_policy(self, coding_agent):
        """Test that prompt content can be denied by policy."""
        schema = agent_to_cedar_schema(coding_agent)
        policy = '@id("deny-prompt") forbid(principal, action == CodingAgent::Action::"Prompt", resource);'
        harness = CedarPolicyHarness(policy_set=policy, schema=schema)
        await harness.initialize(agent=coding_agent)

        result = await harness.adjudicate(
            _prompt_event(harness, PromptRole.User, "Write a Python function")
        )

        assert result.decision == Decision.Deny


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

        with pytest.raises(
            RuntimeError,
            match="initialize\\(\\) must be called before adjudicate\\(\\)",
        ):
            await harness.adjudicate(
                Event(
                    agent=coding_agent,
                    trajectory_id="fake",
                    event=ToolCall(tool="read_file", arguments={"path": "/test"}),
                )
            )


class TestCedarPolicyHarnessInternalErrors:
    """Tests for internal error handling."""

    @pytest.mark.asyncio
    async def test_unknown_policy_id_returns_deny(self, coding_agent):
        """Test that unknown determining policy IDs result in a default deny."""
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

        result = await harness.adjudicate(
            _tool_call_event(harness, "read_file", {"path": "/test"})
        )
        # Unknown policy IDs are skipped; falls through to default deny
        assert result.decision == Decision.Deny


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
        @description("Commands require approval")
        forbid(principal, action == CodingAgent::Action::"execute_command", resource);
        """
        harness = CedarPolicyHarness(policy_set=policy, schema=schema)
        await harness.initialize(agent=coding_agent)

        result = await harness.adjudicate(
            _tool_call_event(harness, "execute_command", {"command": "ls"})
        )

        assert result.decision == Decision.Escalate
        assert len(result.metadata) == 1
        pm = result.metadata[0]
        assert pm.policy_id == "escalate-execute"
        assert pm.description == "Commands require approval"
        assert pm.escalate is True
        assert pm.escalate_arg == (expected_escalate_arg or None)

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
            _tool_call_event(harness, "execute_command", {"command": "ls"})
        )

        assert result.decision == Decision.Deny
        # metadata should only contain the hard deny policy, not the escalate one
        policy_ids = [p.policy_id for p in result.metadata]
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
        @description("Reason A")
        forbid(principal, action == CodingAgent::Action::"execute_command", resource);

        @id("escalate-2")
        @escalate("team-b")
        @description("Reason B")
        forbid(principal, action == CodingAgent::Action::"execute_command", resource);
        """
        harness = CedarPolicyHarness(policy_set=policy, schema=schema)
        await harness.initialize(agent=coding_agent)

        result = await harness.adjudicate(
            _tool_call_event(harness, "execute_command", {"command": "ls"})
        )

        assert result.decision == Decision.Escalate
        sorted_metadata = sorted(result.metadata, key=lambda p: p.policy_id)
        assert len(sorted_metadata) == 2
        assert sorted_metadata[0].policy_id == "escalate-1"
        assert sorted_metadata[0].description == "Reason A"
        assert sorted_metadata[0].escalate is True
        assert sorted_metadata[0].escalate_arg == "team-a"
        assert sorted_metadata[1].policy_id == "escalate-2"
        assert sorted_metadata[1].description == "Reason B"
        assert sorted_metadata[1].escalate is True
        assert sorted_metadata[1].escalate_arg == "team-b"

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
            _tool_call_event(harness, "read_file", {"path": "/tmp/test"})
        )

        assert result.decision == Decision.Allow
