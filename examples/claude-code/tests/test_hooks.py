"""Tests for Claude Code hooks integration."""

import json
from pathlib import Path

import pytest
from sondera_claude.hooks import ClaudeCodeHooks, _is_plan_file
from sondera_claude.types import (
    HookDecision,
    HookResponse,
    HookSpecificOutput,
    PermissionMode,
    PostToolUseEvent,
    PreToolUseEvent,
)

TEST_FILE_PATH = "/workspace/test.txt"
TEST_TRANSCRIPT_PATH = "/workspace/transcript.jsonl"
TEST_CWD = "/workspace"


@pytest.fixture
def plan_mode_policy() -> str:
    """Cedar policy that blocks Write and Edit in plan mode."""
    return """
    @id("forbid-write-in-plan-mode")
    forbid(principal, action == claude_code::Action::"Write", resource)
    when {
        context has parameters &&
        context.parameters has permission_mode &&
        context.parameters.permission_mode == "plan"
    };

    @id("forbid-edit-in-plan-mode")
    forbid(principal, action == claude_code::Action::"Edit", resource)
    when {
        context has parameters &&
        context.parameters has permission_mode &&
        context.parameters.permission_mode == "plan"
    };

    @id("permit-all")
    permit(principal, action, resource);
    """


@pytest.fixture
def hooks(plan_mode_policy: str) -> ClaudeCodeHooks:
    """Create hooks handler with plan mode policy."""
    return ClaudeCodeHooks(policy_text=plan_mode_policy)


class TestClaudeCodeHooksInit:
    """Tests for ClaudeCodeHooks initialization."""

    def test_requires_policy(self):
        with pytest.raises(ValueError, match="Either policy_path or policy_text"):
            ClaudeCodeHooks()

    def test_accepts_policy_text(self, plan_mode_policy: str):
        hooks = ClaudeCodeHooks(policy_text=plan_mode_policy)
        assert hooks._policy_set is not None

    def test_accepts_policy_path_file(self, tmp_path: Path, plan_mode_policy: str):
        policy_file = tmp_path / "test.cedar"
        policy_file.write_text(plan_mode_policy)
        hooks = ClaudeCodeHooks(policy_path=policy_file)
        assert hooks._policy_set is not None

    def test_accepts_policy_path_directory(self, tmp_path: Path, plan_mode_policy: str):
        policy_dir = tmp_path / "policies"
        policy_dir.mkdir()
        (policy_dir / "plan_mode.cedar").write_text(plan_mode_policy)
        hooks = ClaudeCodeHooks(policy_path=policy_dir)
        assert hooks._policy_set is not None

    def test_raises_on_missing_schema(self, plan_mode_policy: str, tmp_path: Path):
        with pytest.raises(ValueError, match="Schema file not found"):
            ClaudeCodeHooks(
                policy_text=plan_mode_policy,
                schema_path=tmp_path / "nonexistent.cedarschema",
            )

    def test_raises_on_empty_policy_directory(self, tmp_path: Path):
        policy_dir = tmp_path / "empty_policies"
        policy_dir.mkdir()
        with pytest.raises(ValueError, match="No policies loaded"):
            ClaudeCodeHooks(policy_path=policy_dir)


class TestPreToolUse:
    """Tests for PreToolUse hook handling."""

    @pytest.mark.parametrize(
        "tool_name,tool_input,expected_policy",
        [
            (
                "Write",
                {"file_path": "/path/to/test.txt", "content": "hello"},
                "forbid-write-in-plan-mode",
            ),
            (
                "Edit",
                {
                    "file_path": "/path/to/test.txt",
                    "old_string": "foo",
                    "new_string": "bar",
                },
                "forbid-edit-in-plan-mode",
            ),
        ],
        ids=["Write", "Edit"],
    )
    def test_denies_modifying_tools_in_plan_mode(
        self,
        hooks: ClaudeCodeHooks,
        tool_name: str,
        tool_input: dict,
        expected_policy: str,
    ):
        event = PreToolUseEvent(
            session_id="test-session",
            tool_name=tool_name,
            tool_input=tool_input,
            permission_mode=PermissionMode.PLAN,
        )
        response = hooks.handle_pre_tool_use(event)
        assert response.hook_specific_output is not None
        assert isinstance(response.hook_specific_output, HookSpecificOutput)
        assert response.hook_specific_output.permission_decision == HookDecision.DENY
        assert response.hook_specific_output.permission_decision_reason is not None
        assert (
            expected_policy in response.hook_specific_output.permission_decision_reason
        )

    @pytest.mark.parametrize(
        "tool_name,tool_input",
        [
            ("Read", {"file_path": "/path/to/test.txt"}),
            ("Bash", {"command": "ls -la"}),
        ],
        ids=["Read", "Bash"],
    )
    def test_allows_other_tools(
        self, hooks: ClaudeCodeHooks, tool_name: str, tool_input: dict
    ):
        event = PreToolUseEvent(
            session_id="test-session",
            tool_name=tool_name,
            tool_input=tool_input,
            permission_mode=PermissionMode.PLAN,
        )
        response = hooks.handle_pre_tool_use(event)
        assert response.hook_specific_output is None

    def test_allows_write_in_default_mode(self, hooks: ClaudeCodeHooks):
        event = PreToolUseEvent(
            session_id="test-session",
            tool_name="Write",
            tool_input={"file_path": "/path/to/test.txt", "content": "hello"},
            permission_mode=PermissionMode.DEFAULT,
        )
        response = hooks.handle_pre_tool_use(event)
        assert response.hook_specific_output is None


class TestToolEventSchemas:
    """Tests for PreToolUse/PostToolUse event schema compatibility."""

    def test_pre_tool_use_event_accepts_common_hook_fields(self):
        event = PreToolUseEvent.model_validate(
            {
                "session_id": "test-session",
                "transcript_path": TEST_TRANSCRIPT_PATH,
                "cwd": TEST_CWD,
                "permission_mode": "plan",
                "hook_event_name": "PreToolUse",
                "tool_name": "Read",
                "tool_input": {"file_path": TEST_FILE_PATH},
                "tool_use_id": "toolu_123",
            }
        )
        assert event.transcript_path == TEST_TRANSCRIPT_PATH
        assert event.cwd == TEST_CWD
        assert event.hook_event_name == "PreToolUse"
        assert event.tool_use_id == "toolu_123"
        assert event.permission_mode == PermissionMode.PLAN

    def test_post_tool_use_event_accepts_tool_response_and_dash_keys(self):
        event = PostToolUseEvent.model_validate(
            {
                "session_id": "test-session",
                "transcript_path": TEST_TRANSCRIPT_PATH,
                "cwd": TEST_CWD,
                "permission_mode": "default",
                "hook_event_name": "PostToolUse",
                "tool_name": "Grep",
                "tool_input": {"pattern": "TODO", "-n": True, "-A": 5},
                "tool_response": {"stdout": "foo\nbar", "exit_code": 0},
                "tool_use_id": "toolu_123",
            }
        )
        assert event.tool_input["-n"] is True
        assert event.tool_input["-A"] == 5
        assert isinstance(event.tool_response, dict)
        assert event.tool_response["exit_code"] == 0


class TestPostToolUse:
    """Tests for PostToolUse hook handling."""

    def test_post_tool_use_defaults_to_allow(self, hooks: ClaudeCodeHooks):
        event = PostToolUseEvent(
            session_id="test-session",
            tool_name="Read",
            tool_input={"file_path": TEST_FILE_PATH},
            tool_response={"content": "test"},
            permission_mode=PermissionMode.DEFAULT,
        )
        response = hooks.handle_post_tool_use(event)
        assert response.hook_specific_output is None
        assert response.decision is None


class TestHookResponseSerialization:
    """Tests for HookResponse JSON serialization."""

    def test_allow_response_serialization(self, hooks: ClaudeCodeHooks):
        event = PreToolUseEvent(
            session_id="test-session",
            tool_name="Write",
            tool_input={"file_path": "/path/to/test.txt", "content": "hello"},
            permission_mode=PermissionMode.DEFAULT,
        )
        response = hooks.handle_pre_tool_use(event)
        json_str = response.model_dump_json(by_alias=True, exclude_none=True)

        # Allow returns empty JSON — no opinion, normal permission system handles it
        assert json_str == "{}"

    def test_deny_response_serialization(self, hooks: ClaudeCodeHooks):
        event = PreToolUseEvent(
            session_id="test-session",
            tool_name="Write",
            tool_input={"file_path": "/path/to/test.txt", "content": "hello"},
            permission_mode=PermissionMode.PLAN,
        )
        response = hooks.handle_pre_tool_use(event)
        json_str = response.model_dump_json(by_alias=True, exclude_none=True)

        assert json_str == (
            '{"hookSpecificOutput":{"hookEventName":"PreToolUse",'
            '"permissionDecision":"deny",'
            '"permissionDecisionReason":"Denied by policies: forbid-write-in-plan-mode"}}'
        )

    def test_post_tool_use_context_serialization(self):
        response = HookResponse.post_tool_use_context("Tool completed successfully")
        json_str = response.model_dump_json(by_alias=True, exclude_none=True)
        assert json.loads(json_str) == {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": "Tool completed successfully",
            }
        }

    def test_block_response_serialization(self):
        response = HookResponse.block("Policy violation")
        json_str = response.model_dump_json(by_alias=True, exclude_none=True)
        assert json.loads(json_str) == {
            "decision": "block",
            "reason": "Policy violation",
        }


class TestToolInputPassthrough:
    """Tests for tool input being passed to Cedar context."""

    @pytest.fixture
    def passwd_policy_hooks(self) -> ClaudeCodeHooks:
        policy = """
        @id("deny-etc-passwd")
        forbid(principal, action == claude_code::Action::"Write", resource)
        when {
            context has parameters &&
            context.parameters has file_path &&
            context.parameters.file_path == "/etc/passwd"
        };

        @id("permit-all")
        permit(principal, action, resource);
        """
        return ClaudeCodeHooks(policy_text=policy)

    def test_denies_write_to_etc_passwd(self, passwd_policy_hooks: ClaudeCodeHooks):
        event = PreToolUseEvent(
            session_id="test-session",
            tool_name="Write",
            tool_input={"file_path": "/etc/passwd", "content": "hello"},
        )
        response = passwd_policy_hooks.handle_pre_tool_use(event)
        assert response.hook_specific_output is not None
        assert isinstance(response.hook_specific_output, HookSpecificOutput)
        assert response.hook_specific_output.permission_decision == HookDecision.DENY

    def test_allows_write_to_other_path(self, passwd_policy_hooks: ClaudeCodeHooks):
        event = PreToolUseEvent(
            session_id="test-session",
            tool_name="Write",
            tool_input={"file_path": "/path/to/safe.txt", "content": "hello"},
        )
        response = passwd_policy_hooks.handle_pre_tool_use(event)
        assert response.hook_specific_output is None


class TestIsPlanFile:
    """Tests for _is_plan_file helper function."""

    @pytest.mark.parametrize(
        "file_path,expected",
        [
            (str(Path.home() / ".claude" / "plans" / "my-plan.md"), True),
            (str(Path.home() / ".claude" / "plans" / "subdir" / "nested.md"), True),
            ("/path/to/test.txt", False),
            (
                "/path/to/fake/.claude/plans/evil.txt",
                False,
            ),  # similar path outside home
            (str(Path.home() / ".claude" / "settings.json"), False),  # parent dir
            ("", False),
        ],
        ids=[
            "plan-file",
            "nested-plan-file",
            "tmp-file",
            "fake-path",
            "parent-dir",
            "empty",
        ],
    )
    def test_is_plan_file(self, file_path: str, expected: bool):
        assert _is_plan_file(file_path) is expected


class TestPlanFileException:
    """Tests for plan file exception in plan mode policies."""

    @pytest.fixture
    def plan_mode_with_exception_policy(self) -> str:
        """Cedar policy that blocks Write/Edit in plan mode except for plan files."""
        return """
        @id("forbid-write-in-plan-mode")
        forbid(principal, action == claude_code::Action::"Write", resource)
        when {
            context has parameters &&
            context.parameters has permission_mode &&
            context.parameters.permission_mode == "plan"
        }
        unless {
            context.parameters has is_plan_file &&
            context.parameters.is_plan_file == true
        };

        @id("forbid-edit-in-plan-mode")
        forbid(principal, action == claude_code::Action::"Edit", resource)
        when {
            context has parameters &&
            context.parameters has permission_mode &&
            context.parameters.permission_mode == "plan"
        }
        unless {
            context.parameters has is_plan_file &&
            context.parameters.is_plan_file == true
        };

        @id("permit-all")
        permit(principal, action, resource);
        """

    @pytest.fixture
    def hooks_with_exception(
        self, plan_mode_with_exception_policy: str
    ) -> ClaudeCodeHooks:
        """Create hooks handler with plan mode policy that allows plan files."""
        return ClaudeCodeHooks(policy_text=plan_mode_with_exception_policy)

    @pytest.mark.parametrize(
        "tool_name",
        ["Write", "Edit"],
    )
    def test_allows_plan_files_in_plan_mode(
        self, hooks_with_exception: ClaudeCodeHooks, tool_name: str
    ):
        file_path = str(Path.home() / ".claude" / "plans" / "test.md")
        tool_input = {"file_path": file_path, "content": "test"}
        if tool_name == "Edit":
            tool_input = {
                "file_path": file_path,
                "old_string": "old",
                "new_string": "new",
            }

        event = PreToolUseEvent(
            session_id="test-session",
            tool_name=tool_name,
            tool_input=tool_input,
            permission_mode=PermissionMode.PLAN,
        )
        response = hooks_with_exception.handle_pre_tool_use(event)
        assert response.hook_specific_output is None

    @pytest.mark.parametrize(
        "tool_name",
        ["Write", "Edit"],
    )
    def test_denies_other_files_in_plan_mode(
        self, hooks_with_exception: ClaudeCodeHooks, tool_name: str
    ):
        file_path = "/path/to/test.txt"
        tool_input = {"file_path": file_path, "content": "test"}
        if tool_name == "Edit":
            tool_input = {
                "file_path": file_path,
                "old_string": "old",
                "new_string": "new",
            }

        event = PreToolUseEvent(
            session_id="test-session",
            tool_name=tool_name,
            tool_input=tool_input,
            permission_mode=PermissionMode.PLAN,
        )
        response = hooks_with_exception.handle_pre_tool_use(event)
        assert response.hook_specific_output is not None
        assert isinstance(response.hook_specific_output, HookSpecificOutput)
        assert response.hook_specific_output.permission_decision == HookDecision.DENY
