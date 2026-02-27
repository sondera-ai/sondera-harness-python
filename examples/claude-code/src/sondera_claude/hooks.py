"""Claude Code hooks handler using Cedar policies.

This module provides the ClaudeCodeHooks class that processes Claude Code
hook events and evaluates them against Cedar policies for Write and Edit tools.
"""

import logging
from pathlib import Path

from sondera_claude.types import HookResponse, PostToolUseEvent, PreToolUseEvent

from cedar import (
    Authorizer,
    Context,
    Entity,
    EntityUid,
    PolicySet,
    Request,
    Schema,
)

_LOGGER = logging.getLogger(__name__)

_CEDAR_NAMESPACE = "claude_code"

_DEFAULT_SCHEMA_PATH = (
    Path(__file__).parent.parent.parent / "schema" / "claude_code.cedarschema"
)


def _is_plan_file(file_path: str) -> bool:
    # resolve() canonicalizes the path, preventing traversal attacks like
    # "/home/user/.claude/plans/../../etc/passwd" from bypassing the check.
    return bool(file_path) and Path(file_path).resolve().is_relative_to(
        Path.home() / ".claude" / "plans"
    )


class ClaudeCodeHooks:
    """Handler for Claude Code hooks using Cedar policies."""

    def __init__(
        self,
        *,
        policy_path: str | Path | None = None,
        policy_text: str | None = None,
        schema_path: str | Path | None = None,
    ):
        if policy_path is None and policy_text is None:
            raise ValueError("Either policy_path or policy_text must be provided")

        if policy_path:
            policy_path = Path(policy_path)
            if policy_path.is_dir():
                policy_texts = []
                for cedar_file in policy_path.glob("**/*.cedar"):
                    _LOGGER.debug("Loading policy file: %s", cedar_file)
                    policy_texts.append(cedar_file.read_text())
                policy_text = "\n".join(policy_texts)
            else:
                policy_text = policy_path.read_text()

        if not policy_text:
            raise ValueError("No policies loaded")

        self._policy_set = PolicySet(policy_text)

        if schema_path is None:
            schema_path = _DEFAULT_SCHEMA_PATH
        schema_path = Path(schema_path)
        if not schema_path.exists():
            raise ValueError(f"Schema file not found: {schema_path}")
        self._schema = Schema.from_cedarschema(schema_path.read_text())

    def _evaluate(
        self,
        action_name: str,
        session_id: str,
        parameters: dict,
    ) -> HookResponse:
        agent_uid = EntityUid(f"{_CEDAR_NAMESPACE}::Agent", session_id)
        action_uid = EntityUid(f"{_CEDAR_NAMESPACE}::Action", action_name)
        trajectory_uid = EntityUid(f"{_CEDAR_NAMESPACE}::Trajectory", "default")

        request = Request(
            principal=agent_uid,
            action=action_uid,
            resource=trajectory_uid,
            context=Context({"parameters": parameters}),
        )

        authorizer = Authorizer(
            entities=[
                Entity(agent_uid, {"name": "claude_code", "provider_id": "anthropic"}),
                Entity(trajectory_uid, {}),
            ],
            schema=self._schema,
        )

        response = authorizer.is_authorized(request, self._policy_set)

        _LOGGER.debug(
            "Cedar evaluation: action=%s decision=%s reasons=%s",
            action_name,
            response.decision,
            response.reason,
        )

        if response.decision == "Allow":
            return HookResponse.allow()

        reason_parts = [
            policy.annotations().get("id", pid)
            for pid in response.reason
            if (policy := self._policy_set.policy(pid))
        ]
        reason = (
            f"Denied by policies: {', '.join(reason_parts)}"
            if reason_parts
            else "Denied"
        )
        return HookResponse.deny(reason)

    def handle_pre_tool_use(self, event: PreToolUseEvent) -> HookResponse:
        parameters = dict(event.tool_input)
        parameters["permission_mode"] = event.permission_mode.value
        file_path = parameters.get("file_path")
        if isinstance(file_path, str):
            parameters["is_plan_file"] = _is_plan_file(file_path)
        return self._evaluate(event.tool_name, event.session_id, parameters)

    def handle_post_tool_use(self, event: PostToolUseEvent) -> HookResponse:
        """Handle PostToolUse events.

        This example hook does not enforce post-tool decisions by default.
        """
        _LOGGER.debug(
            "PostToolUse event: tool=%s tool_use_id=%s",
            event.tool_name,
            event.tool_use_id,
        )
        return HookResponse.allow()
