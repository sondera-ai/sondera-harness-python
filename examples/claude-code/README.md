# Blocking Write and Edit in Plan Mode with Cedar Policies

This example uses Cedar policies to prevent Claude Code from using the `Write` or `Edit` tools while in plan mode.

More specifically, the `sondera-claude` CLI intercepts Claude Code `PreToolUse` and `PostToolUse` hook events, evaluates `PreToolUse` events against Cedar policies, and returns JSON responses on stdout.

The bundled policies block `Write` and `Edit` in plan mode unless the file being written/edited is a plan file (i.e., it's located in `~/.claude/plans/`).

## Setup

Add the following to your project's `.claude/settings.local.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "uv run --project \"$CLAUDE_PROJECT_DIR\"/examples/claude-code sondera-claude pre-tool-use"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "uv run --project \"$CLAUDE_PROJECT_DIR\"/examples/claude-code sondera-claude post-tool-use"
          }
        ]
      }
    ]
  }
}
```

## Usage

### PreToolUse

```bash
echo '{"session_id": "test", "tool_name": "Write", "tool_input": {"file_path": "/tmp/test.txt"}, "permission_mode": "plan"}' | \
  uv run --project . sondera-claude pre-tool-use
```

Output (deny):
```json
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Denied by policies: forbid-write-in-plan-mode"}}
```

### PostToolUse

```bash
echo '{"session_id":"test","tool_name":"Read","tool_input":{"file_path":"/tmp/test.txt","-n":true},"tool_response":{"content":"line1\nline2"}}' | \
  uv run --project . sondera-claude post-tool-use
```

Output (no-op allow):
```json
{}
```

## Output Contract

The hook command must write strict JSON to stdout:

- Default allow/no opinion: `{}`
- Pre-tool deny: `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"..."}}`
- Optional post-tool context: `{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"..."}}`
- Optional post-tool block: `{"decision":"block","reason":"..."}`

## Files

- `schema/claude_code.cedarschema` - Cedar schema defining entities and actions
- `policies/plan_mode.cedar` - Cedar policies that block Write/Edit in plan mode
- `src/sondera_claude/` - Python package with hooks handler, types, and CLI
