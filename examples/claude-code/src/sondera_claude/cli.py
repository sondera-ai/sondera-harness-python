"""CLI for Claude Code hooks integration."""

import json
import sys
from pathlib import Path

import click
from sondera_claude.hooks import ClaudeCodeHooks
from sondera_claude.types import PostToolUseEvent, PreToolUseEvent

_DEFAULT_POLICY_PATH = Path(__file__).parent.parent.parent / "policies"


@click.group()
@click.option(
    "--policy-path",
    type=click.Path(exists=True),
    default=str(_DEFAULT_POLICY_PATH),
    help="Path to Cedar policy file or directory",
)
@click.pass_context
def cli(ctx: click.Context, policy_path: str) -> None:
    """Claude Code hooks using Cedar policies."""
    ctx.ensure_object(dict)
    ctx.obj["policy_path"] = policy_path


@cli.command("pre-tool-use")
@click.pass_context
def pre_tool_use(ctx: click.Context) -> None:
    """Handle PreToolUse hook event."""
    hooks = ClaudeCodeHooks(policy_path=ctx.obj["policy_path"])
    event = PreToolUseEvent.model_validate(json.loads(sys.stdin.read()))
    response = hooks.handle_pre_tool_use(event)
    print(response.model_dump_json(by_alias=True, exclude_none=True))


@cli.command("post-tool-use")
@click.pass_context
def post_tool_use(ctx: click.Context) -> None:
    """Handle PostToolUse hook event."""
    hooks = ClaudeCodeHooks(policy_path=ctx.obj["policy_path"])
    event = PostToolUseEvent.model_validate(json.loads(sys.stdin.read()))
    response = hooks.handle_post_tool_use(event)
    print(response.model_dump_json(by_alias=True, exclude_none=True))


if __name__ == "__main__":
    cli()
