"""Tests for Claude Code CLI commands."""

import json
from pathlib import Path

from click.testing import CliRunner
from sondera_claude.cli import cli

TEST_FILE_PATH = "/workspace/test.txt"

ALLOW_ALL_POLICY = """
@id("permit-all")
permit(principal, action, resource);
"""

PLAN_MODE_POLICY = """
@id("forbid-write-in-plan-mode")
forbid(principal, action == claude_code::Action::"Write", resource)
when {
    context has parameters &&
    context.parameters has permission_mode &&
    context.parameters.permission_mode == "plan"
};

@id("permit-all")
permit(principal, action, resource);
"""


def _write_policy(tmp_path: Path, policy_text: str) -> Path:
    policy_file = tmp_path / "policy.cedar"
    policy_file.write_text(policy_text)
    return policy_file


def test_pre_tool_use_cli_allow_outputs_strict_json(tmp_path: Path):
    policy_file = _write_policy(tmp_path, ALLOW_ALL_POLICY)
    payload = {
        "session_id": "test-session",
        "tool_name": "Read",
        "tool_input": {"file_path": TEST_FILE_PATH},
        "permission_mode": "default",
    }

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--policy-path", str(policy_file), "pre-tool-use"],
        input=json.dumps(payload),
    )

    assert result.exit_code == 0
    assert result.output == "{}\n"
    assert json.loads(result.output) == {}


def test_pre_tool_use_cli_deny_outputs_strict_json(tmp_path: Path):
    policy_file = _write_policy(tmp_path, PLAN_MODE_POLICY)
    payload = {
        "session_id": "test-session",
        "tool_name": "Write",
        "tool_input": {"file_path": TEST_FILE_PATH, "content": "hello"},
        "permission_mode": "plan",
    }

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--policy-path", str(policy_file), "pre-tool-use"],
        input=json.dumps(payload),
    )

    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "Denied by policies: forbid-write-in-plan-mode",
        }
    }
    assert len(result.output.strip().splitlines()) == 1


def test_post_tool_use_cli_allow_outputs_strict_json(tmp_path: Path):
    policy_file = _write_policy(tmp_path, ALLOW_ALL_POLICY)
    payload = {
        "session_id": "test-session",
        "tool_name": "Read",
        "tool_input": {"file_path": TEST_FILE_PATH, "-n": True},
        "tool_response": {"content": "line1\nline2"},
        "permission_mode": "default",
    }

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--policy-path", str(policy_file), "post-tool-use"],
        input=json.dumps(payload),
    )

    assert result.exit_code == 0
    assert result.output == "{}\n"
    assert json.loads(result.output) == {}
