"""Type definitions for Claude Code hooks."""

from collections.abc import Mapping
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

JsonValue = str | int | float | bool | None | list | dict


class PermissionMode(StrEnum):
    DEFAULT = "default"
    PLAN = "plan"
    ACCEPT_EDITS = "acceptEdits"
    DONT_ASK = "dontAsk"
    BYPASS_PERMISSIONS = "bypassPermissions"


class HookDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class HookControlDecision(StrEnum):
    BLOCK = "block"


class ToolHookEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_id: str
    transcript_path: str = ""
    cwd: str = ""
    permission_mode: PermissionMode = Field(default=PermissionMode.DEFAULT)
    hook_event_name: str = ""
    tool_name: str
    tool_input: Mapping[str, JsonValue]
    tool_use_id: str = ""


class PreToolUseEvent(ToolHookEvent):
    pass


class PostToolUseEvent(ToolHookEvent):
    tool_response: JsonValue


class HookSpecificOutput(BaseModel):
    hook_event_name: str = Field(
        default="PreToolUse", serialization_alias="hookEventName"
    )
    permission_decision: HookDecision = Field(serialization_alias="permissionDecision")
    permission_decision_reason: str | None = Field(
        default=None, serialization_alias="permissionDecisionReason"
    )


class PostToolUseHookSpecificOutput(BaseModel):
    hook_event_name: str = Field(
        default="PostToolUse", serialization_alias="hookEventName"
    )
    additional_context: str | None = Field(
        default=None, serialization_alias="additionalContext"
    )


class HookResponse(BaseModel):
    decision: HookControlDecision | None = None
    reason: str | None = None
    hook_specific_output: HookSpecificOutput | PostToolUseHookSpecificOutput | None = (
        Field(default=None, serialization_alias="hookSpecificOutput")
    )

    @classmethod
    def allow(cls) -> "HookResponse":
        """Return cls(), which gives a HookResponse instance with hookSpecificOutput set to None
        (serializes to {}).

        We omit hookSpecificOutput instead of using HookDecision.ALLOW, because the latter would
        bypass Claude Code's normal permission system -- the user wouldn't be prompted for
        permission, the tool call would just execute because we said ALLOW. By not specifying
        hookSpecificOutput, our hook expresses no opinion and Claude Code falls back to its default
        behavior (e.g., prompting the user in default mode, auto-approving in accept-edits mode).
        """
        return cls()

    @classmethod
    def deny(cls, reason: str) -> "HookResponse":
        return cls(
            hook_specific_output=HookSpecificOutput(
                permission_decision=HookDecision.DENY,
                permission_decision_reason=reason,
            ),
        )

    @classmethod
    def post_tool_use_context(cls, context: str) -> "HookResponse":
        return cls(
            hook_specific_output=PostToolUseHookSpecificOutput(
                additional_context=context
            ),
        )

    @classmethod
    def block(cls, reason: str) -> "HookResponse":
        return cls(decision=HookControlDecision.BLOCK, reason=reason)
