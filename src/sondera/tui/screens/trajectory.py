from __future__ import annotations

import contextlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from pygments.lexer import Lexer
from pygments.lexers import (
    BashLexer,
    JsonLexer,
    PythonLexer,
    get_lexer_for_filename,
)
from pygments.token import Token
from pygments.util import ClassNotFound
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer
from textual.events import Click
from textual.reactive import reactive
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import (
    Footer,
    Header,
    Input,
    Static,
)

from sondera.tui.ai.panel import AskInput, AskPanel
from sondera.tui.colors import ThemeColors, get_theme_colors
from sondera.tui.events import EventStep, correlate_events
from sondera.tui.mixins import SectionNavMixin
from sondera.types import (
    Decision,
    Event,
    GuardrailResults,
    Mode,
    Steering,
    Trajectory,
    TrajectoryEventStream,
)
from sondera.types import PolicyMetadata as HarnessPolicyMetadata

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_INTERNAL_ARGS = frozenset({"tool_name", "tool_use_id", "cwd", "name", "type", "id"})

# Emoji support detection: try to measure emoji width, fall back to ASCII
try:
    import unicodedata

    _HAS_EMOJI = unicodedata.east_asian_width("\U0001f464") in ("W", "F", "N")
except Exception:
    _HAS_EMOJI = False

_MCP_PREFIX_RE = re.compile(r"^mcp__(?:plugin_)?(\w+?)_(\w+?)__(\w+)$")

# Platform-appended suffixes on tool_response tool_ids
_TOOL_ID_SUFFIXES = ("_failure", "_permission", "_error")


def _base_tool_id(tool_id: str) -> str:
    """Strip platform suffixes from a tool_id for matching purposes."""
    for suffix in _TOOL_ID_SUFFIXES:
        if tool_id.endswith(suffix):
            return tool_id[: -len(suffix)]
    return tool_id


def _clean_tool_name(tool_id: str) -> str:
    """Shorten MCP tool IDs to readable form.

    mcp__plugin_linear_linear__create_issue  → linear: create_issue
    mcp__plugin_playwright_playwright__browser_click → playwright: browser_click
    """
    m = _MCP_PREFIX_RE.match(tool_id)
    if m:
        plugin, _server, action = m.group(1), m.group(2), m.group(3)
        return f"{plugin}: {action}"
    return tool_id


_STATUS_ICON_CHARS: dict[str, str] = {
    "completed": "\u2713",
    "running": "\u25cf",
    "pending": "\u25cf",
    "failed": "\u2717",
    "suspended": "\u25cb",
    "unknown": "?",
}


def _status_icon(status: str, c: ThemeColors) -> tuple[str, str]:
    """Return (icon, color) for a trajectory status."""
    icon = _STATUS_ICON_CHARS.get(status, "?")
    color_map = {
        "completed": c.success,
        "running": c.primary,
        "pending": c.primary,
        "failed": c.error,
        "suspended": c.warning,
        "unknown": c.fg_dim,
    }
    return icon, color_map.get(status, c.fg_dim)


def _decision_bright(decision: Decision, c: ThemeColors) -> str:
    """Return the bright color for a decision."""
    if decision == Decision.Deny:
        return c.error
    if decision == Decision.Escalate:
        return c.warning
    return c.primary


def _decision_dim(decision: Decision, c: ThemeColors) -> str:
    """Return the dim background color for a decision."""
    if decision == Decision.Deny:
        return c.dim_deny
    if decision == Decision.Escalate:
        return c.dim_escalate
    return c.dim_allow


_ROLE_LABELS: dict[str, str] = (
    {
        "user": "\U0001f464 USER",
        "model": "\U0001f916 MODEL",
        "tool": "\U0001f6e0 TOOL",
        "system": "\U0001f4bb SYSTEM",
    }
    if _HAS_EMOJI
    else {
        "user": "U USER",
        "model": "M MODEL",
        "tool": "T TOOL",
        "system": "S SYSTEM",
    }
)

_ROLE_ICONS: dict[str, str] = (
    {
        "user": "\U0001f464",
        "model": "\U0001f916",
        "tool": "\U0001f6e0",
        "system": "\U0001f4bb",
    }
    if _HAS_EMOJI
    else {
        "user": "U",
        "model": "M",
        "tool": "T",
        "system": "S",
    }
)


_FILE_PATH_KEYS = frozenset(
    {
        "file_path",
        "filePath",
        "path",
        "notebook_path",
        "old_file_path",
        "new_file_path",
    }
)


# ---------------------------------------------------------------------------
# Pygments-based syntax highlighting
# ---------------------------------------------------------------------------

# Reusable lexer singletons (avoid re-creation per call)
_BASH_LEXER = BashLexer()
_JSON_LEXER = JsonLexer()
_PYTHON_LEXER = PythonLexer()


def _token_style(tok_type: Any, c: ThemeColors) -> str:
    """Map a Pygments token type to a ThemeColors style string.

    Walks up the token hierarchy (e.g. Token.Keyword.Constant -> Token.Keyword)
    until a match is found, falling back to ``c.fg``.
    """
    t = tok_type
    while t is not Token:
        if t in _TOKEN_MAP:
            return _TOKEN_MAP[t](c)
        t = t.parent
    return c.fg


# Maps Pygments token types to ThemeColors attribute getters.
# Using lambdas so the mapping works with any ThemeColors instance.
_TOKEN_MAP: dict[Any, Any] = {
    Token.Keyword: lambda c: f"bold {c.kw}",
    Token.Keyword.Constant: lambda c: f"bold {c.kw}",
    Token.Keyword.Namespace: lambda c: f"bold {c.kw}",
    Token.Keyword.Type: lambda c: c.builtin,
    Token.Name.Builtin: lambda c: c.builtin,
    Token.Name.Builtin.Pseudo: lambda c: c.fg_muted,  # self, cls
    Token.Name.Decorator: lambda c: c.decorator,
    Token.Name.Function: lambda c: c.primary,
    Token.Name.Function.Magic: lambda c: c.primary,
    Token.Name.Class: lambda c: c.primary,
    Token.Name.Tag: lambda c: c.prompt_blue,  # JSON keys, HTML/XML tags
    Token.Name.Attribute: lambda c: c.prompt_blue,  # HTML/XML attributes
    Token.Name.Exception: lambda c: c.error,
    Token.Literal.String: lambda c: c.string,
    Token.Literal.String.Doc: lambda c: c.string,
    Token.Literal.String.Interpol: lambda c: c.string,
    Token.Literal.String.Escape: lambda c: c.decorator,
    Token.Literal.Number: lambda c: c.warning,
    Token.Comment: lambda c: c.comment,
    Token.Operator: lambda c: c.fg_muted,
    Token.Operator.Word: lambda c: f"bold {c.kw}",  # and, or, not, in
    Token.Punctuation: lambda c: c.fg_dim,
    Token.Name.Variable: lambda c: c.fg,
    Token.Generic.Deleted: lambda c: f"{c.error} on {c.diff_remove_bg}",
    Token.Generic.Inserted: lambda c: f"{c.success} on {c.diff_add_bg}",
    Token.Generic.Heading: lambda c: f"bold {c.prompt_blue}",
    Token.Generic.Subheading: lambda c: c.prompt_blue,
}


def _pygments_highlight(code: str, lexer: Lexer, text: Text, c: ThemeColors) -> None:
    """Append syntax-highlighted code to a Text object using Pygments tokens."""
    for tok_type, tok_val in lexer.get_tokens(code):
        if tok_val:
            style = _token_style(tok_type, c)
            text.append(tok_val, style=style)


def _detect_lexer(
    content: str,
    file_path: str | None = None,
    tool_id: str | None = None,
) -> Lexer | None:
    """Determine the best Pygments lexer from available context.

    Returns None when no confident match can be made.
    """
    # 1. File extension (most reliable)
    if file_path:
        try:
            return get_lexer_for_filename(file_path, stripnl=False)
        except ClassNotFound:
            pass

    # 2. Tool name hints
    if tool_id:
        tool_lower = tool_id.lower()
        if tool_lower in ("bash", "shell_execution", "shell"):
            return _BASH_LEXER

    # 3. Content heuristics
    if not content:
        return None

    stripped = content.strip()

    # JSON detection
    if stripped and stripped[0] in ("{", "["):
        try:
            json.loads(stripped[:5000])  # quick validation
            return _JSON_LEXER
        except (json.JSONDecodeError, ValueError):
            pass

    # Sample first 30 lines for pattern matching
    lines = content.split("\n", 30)[:30]

    # Line-numbered content (cat -n style: "   1\t...")
    if lines and re.match(r"^\s+\d+\t", lines[0]):
        return _PYTHON_LEXER

    # Python signals
    py_signals = 0
    for line in lines:
        s = line.strip()
        if s.startswith(("def ", "class ", "import ", "from ", "@")):
            py_signals += 2
        elif s.startswith(("#",)) and not s.startswith("#!"):
            py_signals += 1
    if py_signals >= 3:
        return _PYTHON_LEXER

    # Shell signals
    sh_signals = 0
    for line in lines:
        s = line.strip()
        if s.startswith(("$ ", "#!")):
            sh_signals += 3
        elif "&&" in s or "||" in s or s.startswith("export "):
            sh_signals += 2
        elif "|" in s and not s.startswith("|"):
            sh_signals += 1
    if sh_signals >= 3:
        return _BASH_LEXER

    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Defensive accessor: works with both Pydantic models and dicts."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _enum_str(val: Any) -> str:
    """Extract string value from an Enum or return str(val)."""
    if hasattr(val, "value"):
        return str(val.value)
    return str(val)


def _format_duration(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m {secs}s" if secs else f"{minutes}m"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m" if mins else f"{hours}h"


def _format_ms(ms: float) -> str:
    """Format milliseconds as human-readable."""
    if ms < 1000:
        return f"{ms:.0f}ms"
    secs = ms / 1000
    if secs < 60:
        return f"{secs:.0f}s"
    return _format_duration(secs)


def _worst_decision(*decisions: Decision) -> Decision:
    """Return the most severe decision (DENY > ESCALATE > ALLOW)."""
    if Decision.Deny in decisions:
        return Decision.Deny
    if Decision.Escalate in decisions:
        return Decision.Escalate
    return Decision.Allow


def _content_line_count(text: str) -> int:
    """Count lines in a string."""
    if not text:
        return 0
    return text.count("\n") + 1


def _get_tool_use_id(content: object) -> str | None:
    """Extract tool_use_id from tool request args or tool response dict.

    Returns None when the field is absent (non-Claude-Code trajectories).
    """
    args = _get(content, "args", None)
    if isinstance(args, dict):
        val = args.get("tool_use_id")
        if val and isinstance(val, str):
            return val
    response = _get(content, "response", None)
    if isinstance(response, dict):
        val = response.get("tool_use_id")
        if val and isinstance(val, str):
            return val
    return None


def _get_tool_use_id_from_step(step: EventStep) -> str | None:
    """Extract tool_use_id from an EventStep's args or response."""
    from sondera.types import ToolCall, ToolOutput

    p = step.payload
    if isinstance(p, ToolCall) and p.call_id:
        return p.call_id
    if isinstance(p, ToolOutput) and p.call_id:
        return p.call_id
    # Fallback to generic extraction from args/response dicts
    args = step.args
    if isinstance(args, dict):
        val = args.get("tool_use_id")
        if val and isinstance(val, str):
            return val
    resp = step.response
    if isinstance(resp, dict):
        val = resp.get("tool_use_id")
        if val and isinstance(val, str):
            return val
    return None


# ---------------------------------------------------------------------------
# Step grouping dataclass
# ---------------------------------------------------------------------------


@dataclass
class StepGroup:
    """A logical group of related steps."""

    label: str
    icon: str
    step_indices: list[int] = field(default_factory=list)
    primary_index: int = 0
    decision: Decision = field(default_factory=lambda: Decision.Allow)
    duration_ms: float | None = None
    tool_id: str | None = None
    tool_use_id: str | None = None

    # Metadata computed in second pass
    display_index: int = 0
    gap_ms: float | None = None
    file_path: str | None = None
    tool_call_number: int = 0
    tool_call_total: int = 0
    is_repeated: bool = False
    deny_reason: str | None = None
    deny_stage: str | None = None  # "pre_tool" or "post_tool"
    deny_policies: list[HarnessPolicyMetadata] = field(default_factory=list)
    is_prompt: bool = False
    prompt_text: str = ""
    role: str = "user"
    is_tool_request: bool = False
    is_tool_response: bool = False
    preview: str | None = None  # Short context for step list (e.g. Bash description)
    scan_description: str | None = (
        None  # Scanned: human-readable description of the event
    )
    scan_intent: str | None = (
        None  # Scanned: agent intent label (investigate, implement, etc.)
    )
    mode: Mode | None = None  # Adjudicated: policy engine evaluation mode
    steering: Steering | None = (
        None  # Adjudicated: steering instructions (Steer mode only)
    )
    guardrails: GuardrailResults | None = None  # Adjudicated: YARA guardrail results


def _build_step_groups(steps: list[EventStep]) -> list[StepGroup]:
    """Group raw adjudication steps into agent-loop actions.

    The platform may emit duplicate steps for the same action (e.g. two
    pre_tool tool_request steps for one tool call). This function:
    1. Skips consecutive duplicates (same content_type + tool_id/text)
    2. Merges tool_request + tool_response into a single group
    3. Deduplicates consecutive identical prompts
    """
    groups: list[StepGroup] = []
    seen: set[int] = set()  # raw indices already consumed
    i = 0
    while i < len(steps):
        if i in seen:
            i += 1
            continue

        step = steps[i]
        role = step.role
        content_type = step.content_type

        if content_type == "prompt":
            text = step.text
            preview = text[:30].replace("\n", " ")
            if len(text) > 30:
                preview += "\u2026"

            # Absorb consecutive duplicate prompts (same text)
            indices = [i]
            j = i + 1
            while j < len(steps):
                jct = steps[j].content_type
                if jct == "prompt" and steps[j].text == text:
                    indices.append(j)
                    seen.add(j)
                    j += 1
                else:
                    break

            groups.append(
                StepGroup(
                    label=preview or "(empty)",
                    icon=_ROLE_ICONS.get(role, "?"),
                    step_indices=indices,
                    primary_index=indices[0],
                    decision=step.decision,
                    is_prompt=True,
                    prompt_text=text,
                    role=role,
                    scan_description=step.scan_description,
                    scan_intent=step.scan_intent,
                    mode=step.mode,
                    steering=step.steering,
                    guardrails=step.guardrails,
                )
            )

        elif content_type == "tool_request":
            tool_id = step.tool_id
            use_id = _get_tool_use_id_from_step(step)
            req_args = step.args
            indices = [i]
            worst = step.decision
            has_response = False
            parallel_found = False

            # Scan forward: absorb genuine duplicate requests (same
            # tool_use_id or same args), then find the matching response.
            j = i + 1
            while j < len(steps):
                if j in seen:
                    j += 1
                    continue
                jct = steps[j].content_type
                jtid = steps[j].tool_id

                if jct == "tool_request" and jtid == tool_id:
                    j_use_id = _get_tool_use_id_from_step(steps[j])
                    is_duplicate = False
                    if use_id and j_use_id:
                        is_duplicate = j_use_id == use_id
                    elif not use_id and not j_use_id:
                        j_args = steps[j].args
                        is_duplicate = (
                            isinstance(req_args, dict)
                            and isinstance(j_args, dict)
                            and req_args == j_args
                        )
                    if is_duplicate:
                        indices.append(j)
                        worst = _worst_decision(worst, steps[j].decision)
                        seen.add(j)
                    else:
                        parallel_found = True
                    j += 1
                elif jct == "tool_response" and (
                    jtid == tool_id or _base_tool_id(jtid) == tool_id
                ):
                    j_use_id = _get_tool_use_id_from_step(steps[j])
                    if use_id and j_use_id and j_use_id != use_id:
                        j += 1
                        continue
                    indices.append(j)
                    worst = _worst_decision(worst, steps[j].decision)
                    seen.add(j)
                    has_response = True
                    k = j + 1
                    while k < len(steps):
                        kct = steps[k].content_type
                        ktid = steps[k].tool_id
                        if kct == "tool_response" and (
                            ktid == tool_id or _base_tool_id(ktid) == tool_id
                        ):
                            k_use_id = _get_tool_use_id_from_step(steps[k])
                            if use_id and k_use_id and k_use_id != use_id:
                                break
                            indices.append(k)
                            seen.add(k)
                            k += 1
                            if parallel_found:
                                break
                        else:
                            break
                    break
                else:
                    j += 1

            groups.append(
                StepGroup(
                    label=tool_id,
                    icon="\U0001f6e0",
                    step_indices=indices,
                    primary_index=indices[0],
                    decision=worst,
                    tool_id=tool_id,
                    tool_use_id=use_id,
                    is_tool_request=True,
                    is_tool_response=has_response,
                    scan_description=step.scan_description,
                    scan_intent=step.scan_intent,
                    mode=step.mode,
                    steering=step.steering,
                    guardrails=step.guardrails,
                )
            )

        elif content_type == "tool_response":
            # Orphan response (no preceding request)
            tool_id = step.tool_id
            use_id = _get_tool_use_id_from_step(step)
            indices = [i]
            # Absorb genuine duplicates (same tool_use_id)
            j = i + 1
            while j < len(steps):
                jct = steps[j].content_type
                jtid = steps[j].tool_id
                if jct == "tool_response" and (
                    jtid == tool_id or _base_tool_id(jtid) == _base_tool_id(tool_id)
                ):
                    j_use_id = _get_tool_use_id_from_step(steps[j])
                    if use_id and j_use_id and j_use_id != use_id:
                        break  # Different response, stop absorbing
                    indices.append(j)
                    seen.add(j)
                    j += 1
                else:
                    break
            groups.append(
                StepGroup(
                    label=tool_id,
                    icon="\U0001f6e0",
                    step_indices=indices,
                    primary_index=indices[0],
                    decision=step.decision,
                    tool_id=tool_id,
                    tool_use_id=use_id,
                    is_tool_response=True,
                    scan_description=step.scan_description,
                    scan_intent=step.scan_intent,
                    mode=step.mode,
                    steering=step.steering,
                    guardrails=step.guardrails,
                )
            )
        else:
            groups.append(
                StepGroup(
                    label=role or "unknown",
                    icon=_ROLE_ICONS.get(role, "?"),
                    step_indices=[i],
                    primary_index=i,
                    decision=step.decision,
                    role=role,
                    scan_description=step.scan_description,
                    scan_intent=step.scan_intent,
                    mode=step.mode,
                    steering=step.steering,
                    guardrails=step.guardrails,
                )
            )
        i += 1

    return groups


def _enrich_step_groups(groups: list[StepGroup], steps: list[EventStep]) -> None:
    """Second pass: compute display indices, gap times, tool counts, etc."""
    tool_totals: Counter[str] = Counter()
    for g in groups:
        if g.tool_id and g.is_tool_request:
            tool_totals[g.tool_id] += 1

    tool_running: Counter[str] = Counter()
    prev_tool_id: str | None = None
    prev_file_path: str | None = None

    for i, g in enumerate(groups):
        g.display_index = i

        if g.tool_id:
            g.tool_call_total = tool_totals[g.tool_id]
            if g.is_tool_request:
                tool_running[g.tool_id] += 1
                g.tool_call_number = tool_running[g.tool_id]

        # Extract duration from the first response step in the group
        if g.is_tool_response:
            for si in g.step_indices:
                if steps[si].content_type == "tool_response":
                    resp = steps[si].response
                    if isinstance(resp, dict):
                        for key in ("duration", "durationMs", "duration_ms"):
                            resp_dur = resp.get(key)
                            if resp_dur is not None and float(resp_dur) > 0:
                                g.duration_ms = float(resp_dur)
                                break
                    break

        # Extract file path from any step in the group (request or response)
        for si in g.step_indices:
            s = steps[si]
            # Try args first
            args = s.args
            if isinstance(args, dict):
                for key in ("file_path", "filePath", "path", "notebook_path"):
                    val = args.get(key)
                    if val and isinstance(val, str) and "/" in val:
                        g.file_path = val
                        break
            if g.file_path:
                break
            # Then response
            resp = s.response
            if isinstance(resp, dict):
                for key in ("file_path", "filePath", "path"):
                    val = resp.get(key)
                    if val and isinstance(val, str) and "/" in val:
                        g.file_path = val
                        break
            if g.file_path:
                break

        # Extract preview text for tools without a file path.
        # Prefer the actual action (command, query, pattern) over description
        # so the step list shows what was done, not what the AI said it would do.
        if g.tool_id and not g.file_path and g.step_indices:
            for si in g.step_indices:
                if g.preview:
                    break
                args = steps[si].args
                if isinstance(args, dict):
                    # Prefer the actual action
                    for key in (
                        "command",
                        "cmd",
                        "query",
                        "pattern",
                        "skill",
                        "subject",
                        "title",
                        "url",
                    ):
                        val = args.get(key)
                        if val and isinstance(val, str):
                            val = val.strip().split("\n")[0]
                            if len(val) > 40:
                                val = val[:37] + "\u2026"
                            g.preview = val
                            break
                    if g.preview:
                        break
                    # TaskUpdate/TaskCreate: show status + taskId
                    status = args.get("status")
                    task_id = args.get("taskId")
                    if status and isinstance(status, str):
                        label = status
                        if task_id:
                            label += f" #{task_id}"
                        g.preview = label
                        break
                    # Fall back to description if no action arg found
                    desc = args.get("description")
                    if desc and isinstance(desc, str):
                        g.preview = desc[:40]
                        break

        # Use Scanned description as a fallback preview when no other context was found
        if g.tool_id and not g.file_path and not g.preview and g.scan_description:
            desc = g.scan_description
            g.preview = desc[:37] + "\u2026" if len(desc) > 40 else desc

        # For response-only groups, extract preview from the response content
        if g.tool_id and not g.file_path and not g.preview and g.is_tool_response:
            for si in g.step_indices:
                resp = steps[si].response
                if resp is None:
                    continue
                if isinstance(resp, dict):
                    error = resp.get("error")
                    if error and isinstance(error, str):
                        g.preview = f"error: {error[:30]}"
                        break
                    mcp_text = resp.get("text")
                    if isinstance(mcp_text, str) and mcp_text.strip():
                        line = mcp_text.strip().split("\n")[0]
                        if len(line) > 40:
                            line = line[:37] + "\u2026"
                        g.preview = line
                        break
                elif isinstance(resp, str) and resp.strip():
                    line = resp.strip().split("\n")[0]
                    if len(line) > 40:
                        line = line[:37] + "\u2026"
                    g.preview = line
                    break

        # Repeated call detection (same tool + same file as previous)
        if (
            g.tool_id
            and g.tool_id == prev_tool_id
            and g.file_path
            and g.file_path == prev_file_path
        ):
            g.is_repeated = True
        prev_tool_id = g.tool_id
        prev_file_path = g.file_path

        # Deny reason, stage, and policies from first denied step in group
        if g.decision in (Decision.Deny, Decision.Escalate):
            for si in g.step_indices:
                s = steps[si]
                if s.decision in (Decision.Deny, Decision.Escalate):
                    g.deny_reason = s.reason or s.deny_message
                    g.deny_policies = s.policies
                    stage = s.stage
                    if stage:
                        g.deny_stage = stage
                    break

        # Prompt metadata
        first_step = steps[g.step_indices[0]]
        if first_step.content_type == "prompt":
            g.is_prompt = True
            g.prompt_text = first_step.text

        # Gap time since previous group ended (end-to-start)
        if i > 0:
            prev_g = groups[i - 1]
            prev_ts = steps[prev_g.step_indices[-1]].timestamp
            cur_ts = steps[g.step_indices[0]].timestamp
            gap = (cur_ts - prev_ts).total_seconds() * 1000
            if gap > 0:
                g.gap_ms = gap


# ---------------------------------------------------------------------------
# Content highlighting helpers (Pygments-powered)
# ---------------------------------------------------------------------------

_CODE_EXTENSIONS = frozenset(
    {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".java",
        ".go",
        ".rs",
        ".rb",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".cs",
        ".swift",
        ".kt",
        ".scala",
        ".sh",
        ".bash",
        ".zsh",
        ".toml",
        ".yaml",
        ".yml",
        ".json",
        ".css",
        ".tcss",
        ".scss",
        ".html",
        ".xml",
        ".md",
        ".sql",
        ".lua",
        ".r",
        ".m",
        ".pl",
        ".ex",
        ".exs",
        ".zig",
        ".nim",
        ".tf",
        ".hcl",
        ".cedar",
        ".proto",
        ".graphql",
    }
)


def _looks_like_code(content: str, file_path: str | None = None) -> bool:
    """Heuristic: does this content look like source code?"""
    if not content:
        return False
    if file_path:
        ext = file_path.rsplit(".", 1)[-1] if "." in file_path else ""
        if f".{ext}" in _CODE_EXTENSIONS:
            return True
    lines = content.split("\n", 30)[:30]
    if lines and re.match(r"^\s+\d+\t", lines[0]):
        return True
    code_signals = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("def ", "class ", "import ", "from ", "@")):
            code_signals += 2
        elif (
            stripped.startswith(("#", "//", "/*", "<!--", "---"))
            or "=" in stripped
            or stripped.endswith(":")
            or stripped.endswith("{")
            or stripped.endswith(";")
        ):
            code_signals += 1
    return code_signals >= 2


def _append_highlighted_content(
    text: Text,
    content: str,
    c: ThemeColors,
    file_path: str | None = None,
    is_code: bool = False,
) -> None:
    """Append content with syntax highlighting via Pygments when applicable."""
    lexer = None
    if is_code or _looks_like_code(content, file_path):
        lexer = _detect_lexer(content, file_path=file_path)
    if lexer:
        _pygments_highlight(content, lexer, text, c)
    else:
        text.append(content, style=c.fg)


def _append_json_highlighted(text: Text, content: str, c: ThemeColors) -> None:
    """Append pretty-printed JSON with Pygments syntax coloring."""
    _pygments_highlight(content, _JSON_LEXER, text, c)


def _render_structured_patch(
    text: Text,
    patch: dict[str, Any],
    c: ThemeColors,
    file_path: str | None = None,
) -> None:
    """Render a structuredPatch response as a colored diff."""
    lines = patch.get("lines", [])
    if not lines:
        return
    old_start = int(patch.get("oldStart", 1))
    new_start = int(patch.get("newStart", 1))
    text.append(
        f"@@ -{old_start} +{new_start} @@\n",
        style=c.prompt_blue,
    )
    for line in lines:
        s = str(line)
        if s.startswith("+"):
            text.append(s, style=f"{c.success} on {c.diff_add_bg}")
        elif s.startswith("-"):
            text.append(s, style=f"{c.error} on {c.diff_remove_bg}")
        else:
            text.append(s, style=c.fg_dim)
        text.append("\n")


# ---------------------------------------------------------------------------
# Semantic content rendering
# ---------------------------------------------------------------------------


def _truncate_json_strings(obj: Any, max_str: int = 120) -> Any:
    """Recursively truncate long string values in parsed JSON for display."""
    if isinstance(obj, str):
        if len(obj) > max_str:
            return obj[:max_str] + "\u2026"
        return obj
    if isinstance(obj, dict):
        return {k: _truncate_json_strings(v, max_str) for k, v in obj.items()}
    if isinstance(obj, list):
        # Show first 10 items, summarize the rest
        items = [_truncate_json_strings(v, max_str) for v in obj[:10]]
        if len(obj) > 10:
            items.append(f"... +{len(obj) - 10} more")
        return items
    return obj


def _try_parse_json(value: str) -> str | None:
    """If value looks like JSON, return pretty-printed version. Otherwise None."""
    stripped = value.strip()
    if not stripped or stripped[0] not in ("{", "["):
        return None
    try:
        parsed = json.loads(stripped)
        truncated = _truncate_json_strings(parsed)
        return json.dumps(truncated, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, ValueError):
        return None


def _format_value(value: Any, indent: int = 0, max_len: int = 200) -> str:
    """Format a value for display: unwrap dicts/lists into readable lines."""
    prefix = "  " * indent
    if isinstance(value, dict):
        if not value:
            return "{}"
        parts: list[str] = []
        for k, v in value.items():
            formatted = _format_value(v, indent + 1, max_len)
            if "\n" in formatted:
                parts.append(f"{prefix}  {k}:\n{formatted}")
            else:
                parts.append(f"{prefix}  {k}: {formatted}")
        return "\n".join(parts)
    if isinstance(value, list):
        if not value:
            return "[]"
        if len(value) <= 3 and all(
            isinstance(v, str) and len(str(v)) < 50 for v in value
        ):
            return ", ".join(str(v) for v in value)
        parts = []
        for v in value:
            parts.append(f"{prefix}  - {_format_value(v, indent + 1, max_len)}")
        return "\n".join(parts)
    val_str = str(value)
    if len(val_str) > max_len:
        val_str = val_str[:max_len] + "\u2026"
    return val_str


class _EventStepContent:
    """Adapter that exposes EventStep data as the dict-like object
    expected by ``_render_tool_request`` and ``_render_tool_response``.

    These renderers use ``_get(content, "tool_id", ...)``, ``_get(content, "args", ...)``,
    etc. so we just need matching attributes.
    """

    def __init__(self, step: EventStep) -> None:
        self.tool_id = step.tool_id
        self.args = step.args
        self.response = step.response
        self.content_type = step.content_type
        self.text = step.text


def _event_step_as_content(step: EventStep) -> _EventStepContent:
    """Convert an EventStep to the content-like object used by render helpers."""
    return _EventStepContent(step)


def _render_tool_request(
    content: object, c: ThemeColors, decision: Decision = Decision.Allow
) -> Text:
    """Render a ToolRequestContent as formatted Rich Text."""
    tool_id = str(_get(content, "tool_id", "unknown"))
    display_name = _clean_tool_name(tool_id)
    args = _get(content, "args", {})
    if not isinstance(args, dict):
        args = {}

    text = Text()
    if decision == Decision.Deny:
        text.append(display_name, style=f"bold {c.error} on {c.error_bg}")
        text.append(" request", style=c.error)
    else:
        text.append(display_name, style=f"bold {c.fg}")
        text.append(" request", style=c.fg_muted)

    # Filter and render args
    filtered = {k: v for k, v in args.items() if k not in _INTERNAL_ARGS}

    if not filtered:
        return text

    # Special rendering for Edit tool: show diff view
    has_old = "old_string" in filtered or "oldString" in filtered
    if tool_id == "Edit" and has_old:
        text.append("\n")
        # File path
        fp = (
            filtered.get("file_path")
            or filtered.get("filePath")
            or filtered.get("file_path", "")
        )
        if fp:
            text.append(fp, style=c.prompt_blue)
            text.append("\n")
        # Replace all flag
        ra = filtered.get("replace_all") or filtered.get("replaceAll")
        if ra:
            text.append("replace_all: ", style=c.fg_muted)
            text.append(str(ra), style=c.warning)
            text.append("\n")
        # Diff view: removed lines then added lines
        old = str(filtered.get("old_string") or filtered.get("oldString") or "")
        new = str(filtered.get("new_string") or filtered.get("newString") or "")
        for line in old.splitlines():
            text.append(f"- {line}", style=f"{c.error} on {c.diff_remove_bg}")
            text.append("\n")
        for line in new.splitlines():
            text.append(f"+ {line}", style=f"{c.success} on {c.diff_add_bg}")
            text.append("\n")
        return text

    all_lines: list[tuple[str, str]] = []
    for key, value in filtered.items():
        val_str = _format_value(value, max_len=2000)
        all_lines.append((key, val_str))

    # Keys whose values are code/content (should get syntax highlighting)
    _CODE_ARG_KEYS = {
        "new_string",
        "newString",
        "old_string",
        "oldString",
        "content",
        "new_source",
        "newSource",
        "code",
        "source",
        "script",
        "body",
    }

    def _append_arg(t: Text, key: str, val_str: str) -> None:
        if key in ("command", "cmd"):
            t.append("$ ", style=c.fg_muted)
            _pygments_highlight(val_str, _BASH_LEXER, t, c)
        elif key in _FILE_PATH_KEYS:
            t.append(f"{key}: ", style=c.fg_muted)
            t.append(val_str, style=c.prompt_blue)
        elif isinstance(val_str, str) and val_str.replace(".", "", 1).isdigit():
            t.append(f"{key}: ", style=c.fg_muted)
            t.append(val_str, style=c.warning)
        elif key in _CODE_ARG_KEYS:
            # Code content: detect language from file_path context or content
            t.append(f"{key}: ", style=c.fg_muted)
            fp = filtered.get("file_path") or filtered.get("filePath")
            _append_highlighted_content(t, val_str, c, file_path=fp, is_code=True)
        else:
            t.append(f"{key}: ", style=c.fg_muted)
            # Try JSON highlighting for structured values
            pretty = _try_parse_json(val_str) if len(val_str) > 10 else None
            if pretty:
                t.append("\n")
                _append_json_highlighted(t, pretty, c)
            else:
                t.append(val_str, style=c.fg)

    text.append("\n")
    for key, val_str in all_lines:
        _append_arg(text, key, val_str)
        text.append("\n")

    return text


def _render_tool_response(
    content: object,
    c: ThemeColors,
    decision: Decision = Decision.Allow,
    file_path: str | None = None,
) -> Text:
    """Render a ToolResponseContent as formatted Rich Text."""
    tool_id = str(_get(content, "tool_id", "unknown"))
    display_name = _clean_tool_name(tool_id)
    response = _get(content, "response", None)

    text = Text()
    if decision == Decision.Deny:
        text.append(display_name, style=f"bold {c.error} on {c.error_bg}")
        text.append(" response", style=c.error)
    else:
        text.append(display_name, style=f"bold {c.fg}")
        text.append(" response", style=c.prompt_blue)

    if response is None:
        text.append("\n(no response)", style=c.fg_muted)
        return text

    max_val = 2000

    if isinstance(response, dict):
        # Show key metrics on header line
        metrics = []
        if response.get("truncated"):
            metrics.append("truncated")
        duration = response.get("durationMs") or response.get("duration_ms")
        if duration is not None:
            metrics.append(f"{_format_ms(float(duration))}")
        num_files = response.get("numFiles") or response.get("num_files")
        if num_files is not None:
            metrics.append(f"{int(num_files)} files")
        if metrics:
            text.append("  ")
            text.append(" \u00b7 ".join(metrics), style=c.warning)

        # Check for errors
        error = response.get("error")
        if error:
            text.append("\n")
            text.append(f"Error: {error}", style=f"bold {c.error} on {c.error_bg}")
            return text

        # MCP-style response: {'text': '<json or text>', 'type': 'text'}
        # Extract the text payload directly instead of showing as key-value pairs
        mcp_text = response.get("text")
        if isinstance(mcp_text, str) and response.get("type") in ("text", None):
            text.append("\n")
            pretty = _try_parse_json(mcp_text)
            if pretty:
                _append_json_highlighted(text, pretty, c)
            else:
                text.append(mcp_text[:max_val], style=c.fg)
                if len(mcp_text) > max_val:
                    text.append("\u2026", style=c.fg_muted)
            text.append("\n")
            return text

        # Structured patch (Edit tool response): render as colored diff
        patch = response.get("structuredPatch")
        if isinstance(patch, dict) and patch.get("lines"):
            text.append("\n")
            _render_structured_patch(text, patch, c, file_path)
            return text

        # Special handling: if there's a 'content' key with file content, show it
        # as readable text instead of raw dict
        file_content = response.get("content")
        if file_content is None:
            file_val = response.get("file")
            if isinstance(file_val, dict):
                file_content = file_val.get("content")

        _META_KEYS = {
            "truncated",
            "durationMs",
            "duration_ms",
            "numFiles",
            "num_files",
            "error",
            "content",
            "file",
            "structuredPatch",
        }

        # Show non-content metadata first
        meta_lines: list[tuple[str, str]] = []
        for key, value in response.items():
            if key in _META_KEYS:
                continue
            val_str = _format_value(value, max_len=max_val)
            meta_lines.append((key, val_str))

        _OUTPUT_KEYS = {"stdout", "stderr", "output", "result"}

        text.append("\n")
        for key, val_str in meta_lines:
            text.append(f"{key}: ", style=c.fg_muted)
            if key in _OUTPUT_KEYS:
                # Multi-line output: always try detection (skip _looks_like_code gate)
                _append_highlighted_content(
                    text, val_str, c, file_path=file_path, is_code=True
                )
            elif key in _FILE_PATH_KEYS:
                text.append(val_str, style=c.prompt_blue)
            elif val_str.replace(".", "", 1).isdigit():
                text.append(val_str, style=c.warning)
            else:
                # Try to pretty-print JSON string values or nested dicts/lists
                raw_value = response.get(key)
                if isinstance(raw_value, str):
                    pretty = _try_parse_json(raw_value)
                    if pretty:
                        text.append("\n")
                        _append_json_highlighted(text, pretty, c)
                        continue
                elif isinstance(raw_value, (dict, list)):
                    try:
                        truncated = _truncate_json_strings(raw_value)
                        pretty = json.dumps(truncated, indent=2, ensure_ascii=False)
                        text.append("\n")
                        _append_json_highlighted(text, pretty, c)
                        continue
                    except (TypeError, ValueError):
                        pass
                text.append(val_str, style=c.fg)
            text.append("\n")

        # Render file content with syntax highlighting if it looks like code
        if isinstance(file_content, str) and file_content:
            _append_highlighted_content(
                text, file_content, c, file_path=file_path, is_code=True
            )
        elif meta_lines:
            pass  # Already rendered above
        else:
            # Fallback: show all remaining keys
            remaining_lines: list[tuple[str, str]] = []
            for key, value in response.items():
                if key in {
                    "truncated",
                    "durationMs",
                    "duration_ms",
                    "numFiles",
                    "num_files",
                    "error",
                }:
                    continue
                val_str = _format_value(value, max_len=max_val)
                remaining_lines.append((key, val_str))
            for key, val_str in remaining_lines:
                text.append(f"{key}: ", style=c.fg_muted)
                text.append(val_str, style=c.fg)
                text.append("\n")

        return text

    if isinstance(response, list):
        # MCP-style content list: [{'text': '...', 'type': 'text'}, ...]
        mcp_items = [it for it in response if isinstance(it, dict) and "text" in it]
        if mcp_items:
            text.append(f"  {len(response)} items", style=c.warning)
            text.append("\n")
            for item in mcp_items:
                payload = str(item["text"])
                pretty = _try_parse_json(payload)
                if pretty:
                    _append_json_highlighted(text, pretty, c)
                else:
                    text.append(payload[:max_val], style=c.fg)
                    if len(payload) > max_val:
                        text.append("\u2026", style=c.fg_muted)
                    text.append("\n")
            return text

        # Generic list
        text.append(f"  {len(response)} items", style=c.warning)
        text.append("\n")
        for item in response:
            text.append(f"{item}\n", style=c.fg)
        return text

    # String response: try JSON pretty-print first, then syntax highlighting
    val_str = str(response)
    text.append("\n")
    pretty = _try_parse_json(val_str) if len(val_str) > 2 else None
    if pretty:
        _append_json_highlighted(text, pretty, c)
    else:
        _append_highlighted_content(text, val_str, c, file_path=file_path)

    return text


def _render_step_content(step: EventStep, step_index: int, c: ThemeColors) -> Static:
    """Render step content as a formatted Static widget (for standalone steps)."""
    content_type = step.content_type
    decision = step.decision

    if content_type == "tool_request":
        rich_text = _render_tool_request(_event_step_as_content(step), c, decision)
    elif content_type == "tool_response":
        rich_text = _render_tool_response(_event_step_as_content(step), c, decision)
    else:
        rich_text = Text(step.text or str(step.payload))

    if decision == Decision.Deny:
        css_class = "step-deny"
    elif decision == Decision.Escalate:
        css_class = "step-escalate"
    else:
        css_class = "step-allow"

    return Static(rich_text, classes=css_class)


# ---------------------------------------------------------------------------
# Merged and prompt card rendering
# ---------------------------------------------------------------------------


def _render_merged_tool_card(
    steps: list[EventStep],
    group: StepGroup,
    c: ThemeColors,
) -> Static:
    """Render paired pre_tool + post_tool as a single merged card."""
    text = Text()

    # Inline deny/escalate reason and policy info
    if group.decision in (Decision.Deny, Decision.Escalate):
        accent = c.error if group.decision == Decision.Deny else c.warning
        label = "DENIED" if group.decision == Decision.Deny else "ESCALATED"
        if group.deny_stage:
            stage_label = {"pre_tool": "PRE_TOOL", "post_tool": "POST_TOOL"}.get(
                group.deny_stage, group.deny_stage.upper()
            )
            tool_name = _clean_tool_name(group.tool_id or "")
            text.append(
                f" {label} {stage_label} {tool_name} ", style=f"bold {c.fg} on {accent}"
            )
        else:
            text.append(f" {label} ", style=f"bold {c.fg} on {accent}")
        text.append(" ", style="")
        # Show policy IDs inline on the badge line
        if group.deny_policies:
            text.append(
                "; ".join(p.policy_id for p in group.deny_policies if p.policy_id),
                style=accent,
            )
        elif group.deny_reason:
            text.append(group.deny_reason, style=accent)
        text.append("\n")
        # Show descriptions (if any) as indented lines below
        for p in group.deny_policies:
            if p.description:
                text.append(f"  {p.policy_id}: ", style=f"bold {accent}")
                text.append(p.description, style=c.fg_secondary)
                text.append("\n")
        # Show steering instructions (Steer mode only)
        if (steering := group.steering) and steering.instructions:
            text.append("  Steering: ", style=f"bold {accent}")
            text.append(steering.explanation or "", style=c.fg_secondary)
            text.append("\n")
            for instruction in steering.instructions:
                text.append(f"    • {instruction}\n", style=c.fg_secondary)
        # Show triggered YARA guardrail matches
        if group.guardrails and group.guardrails.signature:
            sig = group.guardrails.signature
            if sig.triggered:
                text.append("  Guardrails: ", style=f"bold {accent}")
                text.append(f"severity={sig.severity}", style=c.fg_secondary)
                if sig.categories:
                    text.append(f"  [{', '.join(sig.categories)}]", style=c.fg_muted)
                text.append("\n")
                for match in sig.matches:
                    text.append(f"    • {match.rule}", style=c.fg_secondary)
                    if match.namespace:
                        text.append(f" ({match.namespace})", style=c.fg_muted)
                    text.append("\n")

    # Show Scanned context (description + intent) when available and step allowed
    if group.decision == Decision.Allow and (
        group.scan_description or group.scan_intent
    ):
        scan_parts: list[str] = []
        if group.scan_intent:
            scan_parts.append(f"[{group.scan_intent}]")
        if group.scan_description:
            scan_parts.append(group.scan_description)
        text.append(" ".join(scan_parts), style=c.fg_muted)
        text.append("\n")

    # Find first request and first response among the (possibly duplicated) steps
    request_step = None
    response_step = None
    for s in steps:
        ct = s.content_type
        if ct == "tool_request" and request_step is None:
            request_step = s
        elif ct == "tool_response" and response_step is None:
            response_step = s

    # Request section
    if request_step is not None:
        request_text = _render_tool_request(
            _event_step_as_content(request_step), c, request_step.decision
        )
        text.append_text(request_text)

    # Divider (only when both request and response exist)
    if request_step is not None and response_step is not None:
        divider_color = c.fg_dim
        text.append("\n")
        text.append("\u2500" * 40, style=divider_color)
        text.append("\n")

    # Response section
    if response_step is not None:
        response_text = _render_tool_response(
            _event_step_as_content(response_step),
            c,
            response_step.decision,
            file_path=group.file_path,
        )
        text.append_text(response_text)

    # CSS class based on worst decision
    if group.decision == Decision.Deny:
        css_class = "step-deny"
    elif group.decision == Decision.Escalate:
        css_class = "step-escalate"
    else:
        css_class = "step-allow"

    return Static(text, classes=css_class)


# Markdown patterns for lightweight prompt rendering
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_MD_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_MD_BULLET_RE = re.compile(r"^(\s*)[-*]\s+(.+)$")
_MD_NUMBERED_RE = re.compile(r"^(\s*)(\d+)\.\s+(.+)$")


def _render_markdown_text(raw: str, c: ThemeColors) -> Text:
    """Convert common markdown patterns to Rich Text styling.

    Handles bold, inline code, headings, bullet lists, and numbered lists.
    Returns a Text object (preserves search highlighting compatibility).
    """
    text = Text()
    for line in raw.split("\n"):
        # Heading: ### Title
        m = _MD_HEADING_RE.match(line)
        if m:
            text.append(m.group(2), style=f"bold {c.fg}")
            text.append("\n")
            continue

        # Bullet list: - item or * item
        m = _MD_BULLET_RE.match(line)
        if m:
            indent = m.group(1)
            text.append(f"{indent}  ", style="")
            text.append("\u2022 ", style=c.primary)
            _append_inline_md(text, m.group(2), c)
            text.append("\n")
            continue

        # Numbered list: 1. item
        m = _MD_NUMBERED_RE.match(line)
        if m:
            indent, num = m.group(1), m.group(2)
            text.append(f"{indent}  ", style="")
            text.append(f"{num}. ", style=c.fg_muted)
            _append_inline_md(text, m.group(3), c)
            text.append("\n")
            continue

        # Regular line: process inline markdown
        _append_inline_md(text, line, c)
        text.append("\n")

    return text


def _append_inline_md(text: Text, line: str, c: ThemeColors) -> None:
    """Append a single line with inline markdown (bold, code) resolved."""
    # Merge bold and code patterns into a unified token stream
    tokens: list[tuple[int, int, str, str]] = []  # (start, end, kind, content)
    for m in _MD_BOLD_RE.finditer(line):
        content = m.group(1) or m.group(2)
        tokens.append((m.start(), m.end(), "bold", content))
    for m in _MD_INLINE_CODE_RE.finditer(line):
        tokens.append((m.start(), m.end(), "code", m.group(1)))

    if not tokens:
        text.append(line, style=c.fg)
        return

    # Sort by position and emit non-overlapping tokens
    tokens.sort(key=lambda t: t[0])
    pos = 0
    for start, end, kind, content in tokens:
        if start < pos:
            continue  # skip overlapping
        if start > pos:
            text.append(line[pos:start], style=c.fg)
        if kind == "bold":
            text.append(content, style=f"bold {c.fg}")
        elif kind == "code":
            text.append(content, style=f"{c.kw}")
        pos = end
    if pos < len(line):
        text.append(line[pos:], style=c.fg)


def _render_prompt_card(group: StepGroup, c: ThemeColors) -> Static:
    """Render a user prompt card with lightweight markdown formatting."""
    header = Text()
    # Show adjudication badge for denied/escalated prompts
    if group.decision in (Decision.Deny, Decision.Escalate):
        accent = c.error if group.decision == Decision.Deny else c.warning
        label = "DENIED" if group.decision == Decision.Deny else "ESCALATED"
        header.append(f" {label} ", style=f"bold {c.fg} on {accent}")
        header.append(" ", style="")
        if group.deny_policies:
            header.append(
                "; ".join(p.policy_id for p in group.deny_policies if p.policy_id),
                style=accent,
            )
        elif group.deny_reason:
            header.append(group.deny_reason, style=accent)
        header.append("\n\n")

    body = _render_markdown_text(group.prompt_text, c)
    if header.plain:
        header.append_text(body)
        text = header
    else:
        text = body
    css_class = "step-prompt-model" if group.role == "model" else "step-prompt"
    return Static(text, classes=css_class)


# ---------------------------------------------------------------------------
# Border title / subtitle builders (Features 2, 3, 7, 8)
# ---------------------------------------------------------------------------


def _build_group_border_title(group: StepGroup) -> str:
    """Build a clean border title with step number.

    Format: #4  Read  agents_feed.py  342ms
    Bash:   #8  Bash  Re-run VHS demo
    """
    parts: list[str] = [f"#{group.display_index + 1}"]

    if group.tool_id:
        parts.append(group.tool_id)
        if group.file_path:
            filename = group.file_path.rsplit("/", 1)[-1]
            parts.append(filename)
        elif group.preview:
            parts.append(group.preview)
    elif group.is_prompt:
        role_label = "Agent" if group.role == "model" else "User"
        parts.append(f"{group.icon} {role_label}")
    else:
        parts.append(group.label)

    if group.duration_ms is not None:
        parts.append(_format_ms(group.duration_ms))

    return "  ".join(parts)


def _build_group_border_subtitle(group: StepGroup, steps: list[EventStep]) -> str:
    """Build border subtitle: start-end time, gap since previous ended, duration."""
    first_step = steps[group.step_indices[0]]
    last_step = steps[group.step_indices[-1]]
    start_ts = first_step.timestamp
    end_ts = last_step.timestamp

    ts_str = ""

    # Idle time before this step (model inference / thinking)
    if group.gap_ms is not None and group.gap_ms > 100:
        ts_str += f"idle {_format_ms(group.gap_ms)}  "

    # Timestamp range + duration
    local_start = start_ts.astimezone()
    tz_name = local_start.strftime("%Z") or local_start.strftime("%z")
    ts_str += local_start.strftime("%H:%M:%S")

    # Show end time if different from start (multi-step group)
    if len(group.step_indices) > 1:
        local_end = end_ts.astimezone()
        if local_end.strftime("%H:%M:%S") != local_start.strftime("%H:%M:%S"):
            ts_str += f"\u2013{local_end.strftime('%H:%M:%S')}"

    ts_str += f" {tz_name}"

    # Duration: time from first to last step in the group (request to response)
    if len(group.step_indices) > 1:
        dur_ms = (end_ts - start_ts).total_seconds() * 1000
        if dur_ms > 100:
            ts_str += f" (took {_format_ms(dur_ms)})"

    return ts_str


# ---------------------------------------------------------------------------
# Step row rendering (one-line summary for master list)
# ---------------------------------------------------------------------------


def _render_step_row(group: StepGroup, selected: bool, c: ThemeColors) -> Text:
    """Render a one-line summary for the step list."""
    text = Text()
    text.append("\u25b8 " if selected else "  ", style=c.primary if selected else "")
    text.append(f"#{group.display_index + 1:<4} ", style=c.fg_dim)

    if group.is_prompt:
        # Show deny/escalate indicator for blocked prompts
        if group.decision == Decision.Deny:
            text.append("\u2717 ", style=c.error)
        elif group.decision == Decision.Escalate:
            text.append("\u26a0 ", style=c.warning)
        icon_style = c.fg_secondary if group.role == "model" else c.prompt_blue
        if group.decision == Decision.Deny:
            icon_style = c.error
        elif group.decision == Decision.Escalate:
            icon_style = c.warning
        text.append(f"{group.icon} ", style=icon_style)
        preview = group.prompt_text[:30].replace("\n", " ")
        if len(group.prompt_text) > 30:
            preview += "\u2026"
        text.append(f"\u201c{preview}\u201d", style=icon_style)
    else:
        # Decision icon + tool name
        display_name = _clean_tool_name(group.tool_id or group.label)
        if group.decision == Decision.Deny:
            text.append("\u2717 ", style=c.error)
            text.append(display_name, style=c.error)
        elif group.decision == Decision.Escalate:
            text.append("\u26a0 ", style=c.warning)
            text.append(display_name, style=c.warning)
        else:
            text.append(display_name, style=c.fg)

        # File name or preview context
        if group.file_path:
            fn = group.file_path.rsplit("/", 1)[-1]
            if len(fn) > 18:
                fn = fn[:15] + "\u2026"
            text.append(f"  {fn}", style=c.fg_dim)
        elif group.preview:
            preview = group.preview
            if len(preview) > 24:
                preview = preview[:21] + "\u2026"
            text.append(f"  {preview}", style=c.fg_dim)

        # Scan intent badge (e.g. "investigate", "implement") when available
        if group.scan_intent and group.decision == Decision.Allow:
            text.append(f"  [{group.scan_intent}]", style=c.fg_muted)

        # Mode badge for non-default modes (Monitor shows observed-only, Steer shows steering)
        if (mode := group.mode) is not None and mode != Mode.Govern:
            text.append(f"  {str(mode).upper()}", style=c.fg_muted)

        # Duration
        if group.duration_ms is not None:
            text.append(f"  {_format_ms(group.duration_ms)}", style=c.fg_dim)

    return text


# ---------------------------------------------------------------------------
# Decision minimap widget
# ---------------------------------------------------------------------------


class DecisionMinimap(Widget):
    """Single-row strip showing all grouped step decisions as colored blocks."""

    current_index: reactive[int] = reactive(0)

    def __init__(self, groups: list[StepGroup], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._groups = groups

    def render(self) -> Text:
        c = get_theme_colors(self.app)
        text = Text()
        text.append("Steps: ", style=c.fg_muted)

        total = len(self._groups)
        if not total:
            text.append("(none)", style=c.fg_dim)
            return text

        # Build suffix: [N/total  M denied]
        denied = sum(1 for g in self._groups if g.decision == Decision.Deny)
        counter = f"[{self.current_index + 1}/{total}"
        if denied > 0:
            counter += f"  {denied} denied"
        counter += "]"

        # Legend: ■ allow ■ deny ■ current
        legend_len = 27  # "  ■ allow ■ deny ■ current"
        suffix_len = len(counter) + 2 + legend_len  # "  " + counter + legend
        available = self.size.width - 7 - suffix_len  # 7 = len("Steps: ")

        if total <= available:
            for i, group in enumerate(self._groups):
                if i == self.current_index:
                    color = _decision_bright(group.decision, c)
                    text.append("\u2588", style=f"bold {color} on {c.border}")
                else:
                    color = _decision_dim(group.decision, c)
                    text.append("\u2588", style=color)
        else:
            bucket_count = max(1, available)
            pos_worst: list[Decision] = [Decision.Allow] * bucket_count
            for i, group in enumerate(self._groups):
                pos = i * bucket_count // total
                pos_worst[pos] = _worst_decision(pos_worst[pos], group.decision)
            cursor_pos = self.current_index * bucket_count // total
            current_decision = self._groups[self.current_index].decision
            for b in range(bucket_count):
                if b == cursor_pos:
                    color = _decision_bright(current_decision, c)
                    text.append("\u2588", style=f"bold {color} on {c.border}")
                else:
                    color = _decision_dim(pos_worst[b], c)
                    text.append("\u2588", style=color)

        # Counter with optional denied count
        text.append(f"  {counter}", style=c.fg_muted)

        # Legend
        text.append("  ")
        text.append("\u2588", style=c.dim_allow)
        text.append(" allow ", style=c.fg_dim)
        text.append("\u2588", style=c.dim_deny)
        text.append(" deny ", style=c.fg_dim)
        text.append("\u2588", style=f"bold {c.primary} on {c.border}")
        text.append(" current", style=c.fg_dim)

        return text

    def watch_current_index(self) -> None:
        self.refresh()


# ---------------------------------------------------------------------------
# TrajectoryScreen
# ---------------------------------------------------------------------------


class TrajectoryScreen(SectionNavMixin, Screen):
    """A screen for displaying a trajectory with semantic formatting."""

    app: "sondera.tui.app.SonderaApp"  # type: ignore[name-defined]  # noqa: UP037, F821

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("tab", "next_section", "Panel", key_display="tab"),
        Binding("shift+tab", "prev_section", show=False),
        Binding("j", "vim_down", show=False),
        Binding("k", "vim_up", show=False),
        Binding("h", "vim_left", show=False),
        Binding("l", "vim_right", show=False),
        Binding("down", "cursor_down", "Navigate", key_display="\u2191/\u2193"),
        Binding("up", "cursor_up", show=False),
        Binding("left", "cursor_left", "\u2190/\u2192 Panel", show=False),
        Binding("right", "cursor_right", show=False),
        Binding("[", "prev_step", show=False),
        Binding("]", "next_step", show=False),
        Binding("d", "next_violation", "Next Deny"),
        Binding("D", "prev_violation", show=False),
        Binding("slash", "search", "Search", key_display="/"),
        Binding("n", "search_next", show=False),
        Binding("N", "search_prev", show=False),
        Binding("y", "yank", "Copy"),
        Binding("ctrl+grave_accent", "ask", "AI", key_display="ctrl+`"),
        Binding("enter", "noop", show=False),
    ]

    # ----- Live streaming ----------------------------------------------------

    @work(exclusive=True, group="trajectory-live-stream")
    async def _stream_live_events(self) -> None:
        """Subscribe to live events for this trajectory and append new steps.

        Opens a :class:`TrajectoryEventStream` filtered to this trajectory's
        resource name.  Each arriving :class:`TrajectoryEventNotification` is
        processed by :meth:`_apply_live_event` which re-correlates the event
        list and mounts any new step widgets into ``#step-list``.

        Streaming stops automatically once the trajectory reaches a terminal
        state (completed, failed, or terminated).
        """
        from textual.worker import get_current_worker

        worker = get_current_worker()
        filter_expr = f'trajectory = "{self.trajectory.name}"'
        try:
            stream: TrajectoryEventStream = await self.app.harness.stream_trajectories(
                filter=filter_expr
            )
        except Exception:
            return

        async for notification in stream:
            if worker.is_cancelled:
                break

            event = notification.event  # type: ignore[union-attr]
            if event is not None:
                await self._apply_live_event(event)

            # Stop once the trajectory has finished
            if self._live_status in {"completed", "failed", "terminated"}:
                break

    async def _apply_live_event(self, event: Event) -> None:
        """Process one incoming live :class:`Event` and update the step view.

        Appends *event* to the local event list, re-correlates the full stream
        to produce updated :class:`EventStep` and :class:`StepGroup` sequences,
        then mounts widgets for any newly visible groups.  Summary and minimap
        are refreshed on every call regardless of whether new groups appear.
        """
        event_type = (event.event_type or "").lower()

        # Track terminal lifecycle events so the summary bar shows the right status
        if event_type in {"completed", "failed", "suspended", "terminated"}:
            self._live_status = event_type

        # Append the event; correlate_events skips lifecycle entries automatically
        self._live_events.append(event)
        old_group_count = len(self._step_groups)

        new_steps = correlate_events(self._live_events)
        new_groups = _build_step_groups(new_steps)
        _enrich_step_groups(new_groups, new_steps)

        added_groups = new_groups[old_group_count:]

        # Always refresh summary (step count, timing, and status may have changed)
        with contextlib.suppress(Exception):
            self.query_one("#trajectory-summary", Static).update(self._render_summary())

        if not added_groups:
            return

        # Mutate lists in-place so the DecisionMinimap reference stays valid
        self._steps = new_steps
        self._step_groups.extend(added_groups)

        # Extend index mappings for the new groups
        for g in added_groups:
            for si in g.step_indices:
                self._step_to_display[si] = g.display_index

        # Rebuild violation navigation index
        self._violation_indices = [
            g.display_index
            for g in self._step_groups
            if g.decision in (Decision.Deny, Decision.Escalate)
        ]

        # Extend searchable text used by the '/' search feature
        for g in added_groups:
            parts: list[str] = []
            for si in g.step_indices:
                step = self._steps[si]
                ct = step.content_type
                if ct == "prompt":
                    parts.append(step.text)
                elif ct == "tool_request":
                    parts.append(step.tool_id)
                    args = step.args
                    if isinstance(args, dict):
                        for v in args.values():
                            parts.append(str(v)[:500])
                elif ct == "tool_response":
                    parts.append(step.tool_id)
                    resp = step.response
                    if isinstance(resp, dict):
                        for v in resp.values():
                            parts.append(str(v)[:500])
                    elif resp is not None:
                        parts.append(str(resp)[:500])
            self._group_text.append("\n".join(parts).lower())

        # Mount new row widgets at the bottom of the step list
        c = get_theme_colors(self.app)
        with contextlib.suppress(Exception):
            step_list = self.query_one("#step-list", ScrollableContainer)
            for group in added_groups:
                await step_list.mount(
                    Static(
                        _render_step_row(group, False, c),
                        classes="step-row",
                    )
                )

        # Refresh the minimap; its _groups reference is the same list object
        with contextlib.suppress(Exception):
            self.query_one("#decision-minimap", DecisionMinimap).refresh()

    def action_back(self) -> None:
        """Cancel AI stream > dismiss search > pop screen."""
        if self.app._ask_state.stream.is_streaming:  # type: ignore[attr-defined]
            with contextlib.suppress(Exception):
                self.query_one("#ask-panel", AskPanel).cancel_stream()
            return
        try:
            search = self.query_one("#search-input", Input)
            if search.display:
                self._dismiss_search()
                return
        except Exception:
            pass
        self.app.pop_screen()

    def _section_cycle(self) -> list:
        """Ordered focusable sections for tab cycling."""
        sections: list = []
        with contextlib.suppress(Exception):
            sections.append(self.query_one("#step-list", ScrollableContainer))
        with contextlib.suppress(Exception):
            sections.append(self.query_one("#step-detail", ScrollableContainer))
        with contextlib.suppress(Exception):
            sections.append(self.query_one("#ask-panel", AskPanel))
        return sections

    def action_ask(self) -> None:
        """Toggle the AI ask panel open/closed."""
        try:
            panel = self.query_one("#ask-panel", AskPanel)
            panel.toggle_response()
        except Exception:
            pass

    def on_ask_panel_dismissed(self, _msg: AskPanel.Dismissed) -> None:
        """Restore focus when ask panel closes."""
        with contextlib.suppress(Exception):
            self.query_one("#step-list", ScrollableContainer).focus()

    def on_screen_resume(self) -> None:
        """Sync AskPanel state when returning to this screen."""
        with contextlib.suppress(Exception):
            self.query_one("#ask-panel", AskPanel)._sync_from_state()

    def action_noop(self) -> None:
        """Consume Enter so it doesn't bubble to the app."""
        pass

    def action_yank(self) -> None:
        """Copy the current step detail panel content to clipboard."""
        try:
            detail = self.query_one("#step-detail", ScrollableContainer)
            parts: list[str] = []
            for child in detail.children:
                if isinstance(child, Static):
                    content = child.render()
                    if isinstance(content, Text):
                        parts.append(content.plain)
                    else:
                        parts.append(str(content))
            if parts:
                self.app.copy_to_clipboard("\n".join(parts))
                self.notify("Copied to clipboard", severity="information")
            else:
                self.notify("Nothing to copy", severity="warning")
        except Exception:
            self.notify("Copy failed", severity="error")

    def __init__(
        self,
        trajectory: Trajectory,
        initial_step: int | None = None,
    ):
        super().__init__()
        self.trajectory = trajectory
        self.initial_step = initial_step
        self._selected_index: int = 0

        # Mutable local copy of trajectory events for live streaming.
        # New events appended via the stream are added here and re-correlated.
        self._live_events: list[Event] = list(trajectory.events or [])
        # Status derived from terminal lifecycle events received via the stream;
        # overrides trajectory.status in the summary bar when set.
        self._live_status: str | None = None

        # Correlate events into EventSteps
        self._steps: list[EventStep] = correlate_events(trajectory.events or [])

        # Build groups and enrich with metadata
        self._step_groups = _build_step_groups(self._steps)
        _enrich_step_groups(self._step_groups, self._steps)

        # Index mappings: step index <-> display index
        self._step_to_display: dict[int, int] = {}
        for g in self._step_groups:
            for si in g.step_indices:
                self._step_to_display[si] = g.display_index

        # Violation indices for d/D navigation
        self._violation_indices: list[int] = [
            g.display_index
            for g in self._step_groups
            if g.decision in (Decision.Deny, Decision.Escalate)
        ]

        # Search state
        self._search_query: str = ""
        self._search_matches: list[int] = []  # display indices of matches
        self._search_match_idx: int = 0

        # Pre-build searchable text per group for fast matching
        self._group_text: list[str] = []
        for g in self._step_groups:
            parts: list[str] = []
            for si in g.step_indices:
                step = self._steps[si]
                ct = step.content_type
                if ct == "prompt":
                    parts.append(step.text)
                elif ct == "tool_request":
                    parts.append(step.tool_id)
                    args = step.args
                    if isinstance(args, dict):
                        for v in args.values():
                            parts.append(str(v)[:500])
                elif ct == "tool_response":
                    parts.append(step.tool_id)
                    resp = step.response
                    if isinstance(resp, dict):
                        for v in resp.values():
                            parts.append(str(v)[:500])
                    elif resp is not None:
                        parts.append(str(resp)[:500])
            self._group_text.append("\n".join(parts).lower())

    # ----- Summary rendering -------------------------------------------------

    def _render_summary(self) -> Text:
        """Render a clean 2-line trajectory summary."""
        c = get_theme_colors(self.app)
        traj = self.trajectory
        steps = self._steps
        text = Text()

        # Line 1: agent + short ID + status + steps + timing
        agent_id = traj.agent
        text.append(agent_id[:30], style=f"bold {c.fg}")
        # Show short trajectory ID for identification
        tid = traj.name
        short_id = tid.split("-")[0] if "-" in tid else tid[:8]
        text.append(f"  {short_id}", style=c.fg_dim)
        text.append("  ")
        # Use live status from the stream when available, otherwise fall back to
        # the trajectory's own status field.
        effective = self._live_status or str(traj.status or "unknown").lower()
        if effective in {"running", "pending"} and steps:
            first_ts = steps[0].timestamp
            last_ts = steps[-1].timestamp
            if first_ts != last_ts:
                effective = "completed"
        icon, color = _status_icon(effective, c)
        text.append(f"{icon} {effective}", style=f"bold {color}")
        text.append("  ")
        text.append(f"{len(self._step_groups)} steps", style=c.fg_muted)

        # Time range: first step to last step
        first_ts = steps[0].timestamp if steps else None
        last_ts = steps[-1].timestamp if steps else None

        if first_ts is not None:
            local_start = first_ts.astimezone()
            tz_name = local_start.strftime("%Z") or local_start.strftime("%z")
            date_str = local_start.strftime("%b %-d %Y ")
            text.append("  ")
            text.append(date_str, style=c.fg_dim)
            text.append(local_start.strftime("%H:%M:%S"), style=c.fg_muted)
            if last_ts is not None and last_ts != first_ts:
                local_end = last_ts.astimezone()
                text.append("\u2013", style=c.fg_dim)
                text.append(local_end.strftime("%H:%M:%S"), style=c.fg_muted)
            text.append(f" {tz_name}", style=c.fg_dim)

        # Duration derived from the displayed time range
        if first_ts is not None and last_ts is not None:
            duration = (last_ts - first_ts).total_seconds()
            if duration > 0:
                text.append(
                    f"  (took {_format_duration(duration)})", style=c.fg_secondary
                )

        # Line 2: violations or clean status (count from grouped steps, not raw)
        denied = sum(1 for g in self._step_groups if g.decision == Decision.Deny)
        escalated = sum(1 for g in self._step_groups if g.decision == Decision.Escalate)

        if denied > 0 or escalated > 0:
            text.append("\n")
            if denied > 0:
                text.append(
                    f"{denied} step{'s' if denied != 1 else ''} blocked by policy",
                    style=f"bold {c.error}",
                )
            if denied > 0 and escalated > 0:
                text.append("  ", style="")
            if escalated > 0:
                text.append(
                    f"{escalated} awaiting review",
                    style=f"bold {c.warning}",
                )

        return text

    # ----- Compose -----------------------------------------------------------

    def _render_group_widget(self, group: StepGroup) -> Static:
        """Render the appropriate widget for a group."""
        c = get_theme_colors(self.app)
        if group.is_prompt:
            card = _render_prompt_card(group, c)
        elif group.is_tool_request or group.is_tool_response:
            group_steps = [self._steps[si] for si in group.step_indices]
            card = _render_merged_tool_card(group_steps, group, c)
        else:
            step = self._steps[group.primary_index]
            card = _render_step_content(step, group.primary_index, c)

        # Highlight search matches in the detail card text
        if self._search_query:
            content = card.content
            if isinstance(content, Text):
                content.highlight_words(
                    [self._search_query],
                    style=f"bold {c.fg} on {c.dim_allow}",
                    case_sensitive=False,
                )
        return card

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="trajectory-summary")
        yield DecisionMinimap(self._step_groups, id="decision-minimap")
        yield Static("\u2500" * 200, classes="dashboard-sep")
        c = get_theme_colors(self.app)
        with Horizontal(id="trajectory-content"):
            with ScrollableContainer(id="step-list"):
                for group in self._step_groups:
                    # Gap indicator for significant pauses (>60s)
                    if (
                        group.gap_ms is not None
                        and group.gap_ms > 60_000
                        and group.display_index > 0
                    ):
                        gap_text = Text()
                        gap_text.append(
                            f"        \u22ee {_format_ms(group.gap_ms)}",
                            style=c.fg_dim,
                        )
                        yield Static(gap_text, classes="step-gap")
                    selected = group.display_index == 0
                    row_classes = "step-row"
                    if selected:
                        row_classes += " step-row--selected"
                    if group.decision == Decision.Deny:
                        row_classes += " step-row--denied"
                    yield Static(
                        _render_step_row(group, selected, c),
                        classes=row_classes,
                    )
            with ScrollableContainer(id="step-detail"):
                pass  # Populated in on_mount via _update_detail
        search_status = Static(id="search-status")
        search_status.display = False
        yield search_status
        search = Input(placeholder="Search...", id="search-input")
        search.display = False
        yield search
        yield Static("\u2500" * 200, classes="dashboard-sep")
        yield AskPanel(id="ask-panel")
        yield Footer()

    # ----- Mount & detail panel -----------------------------------------------

    def on_mount(self) -> None:
        summary = self.query_one("#trajectory-summary", Static)
        summary.update(self._render_summary())

        step_list = self.query_one("#step-list", ScrollableContainer)
        step_list.can_focus = True
        step_list.focus()

        # Deep-link to initial step (convert step index -> display index)
        initial = 0
        if self.initial_step is not None and 0 <= self.initial_step < len(self._steps):
            initial = self._step_to_display.get(self.initial_step, 0)
        if initial != self._selected_index:
            # Navigate immediately (updates selection + detail panel),
            # then re-scroll after layout is fully computed:
            # call_after_refresh waits for the next repaint, then a short
            # timer gives the layout engine time to finalize all row regions.
            self._navigate_to(initial)
            self.call_after_refresh(
                lambda: self.set_timer(0.15, self._scroll_to_selected)
            )
        else:
            self.call_later(self._update_detail)

        # Generate contextual suggestion for trajectory detail
        from sondera.tui.ai.panel import AskPanel

        with contextlib.suppress(Exception):
            self.query_one("#ask-panel", AskPanel).refresh_suggestion()

        # Start live event streaming for active (running/pending) trajectories
        status = str(self.trajectory.status or "unknown").lower()
        if status in {"running", "pending"}:
            self._stream_live_events()

    def _update_minimap(self, display_index: int) -> None:
        """Update the decision minimap to highlight the given group."""
        try:
            minimap = self.query_one("#decision-minimap", DecisionMinimap)
            minimap.current_index = display_index
        except Exception:
            pass

    async def _update_detail(self) -> None:
        """Replace the detail panel with the selected step's card."""
        detail = self.query_one("#step-detail", ScrollableContainer)
        for child in list(detail.children):
            await child.remove()

        idx = self._selected_index
        if idx < 0 or idx >= len(self._step_groups):
            return

        group = self._step_groups[idx]
        time_str = _build_group_border_subtitle(group, self._steps)
        title_str = _build_group_border_title(group)
        card = self._render_group_widget(group)
        # Combine step info (left) and time (right) in the border title
        if time_str:
            card.border_title = f"{title_str}  \u2502  {time_str}"
        else:
            card.border_title = title_str
        card.border_subtitle = ""

        await detail.mount(card)
        detail.scroll_home(animate=False)

    def _recolor(self) -> None:
        """Re-render all Rich Text content with current theme colors."""
        import contextlib

        c = get_theme_colors(self.app)
        # Summary
        with contextlib.suppress(Exception):
            self.query_one("#trajectory-summary", Static).update(self._render_summary())
        # Step list rows
        rows = list(self.query(".step-row").results(Static))
        for i, row in enumerate(rows):
            if i < len(self._step_groups):
                selected = i == self._selected_index
                row.update(_render_step_row(self._step_groups[i], selected, c))
        # Detail panel
        self.call_later(self._update_detail)
        # AskPanel
        with contextlib.suppress(Exception):
            self.query_one("#ask-panel", AskPanel)._recolor()

    def _scroll_to_selected(self) -> None:
        """Scroll the step list to make the selected row visible.

        Uses the container's scroll_to_widget for reliability during initial
        mount when child widgets may not have finalized regions yet.
        """
        try:
            rows = list(self.query(".step-row").results(Static))
            if 0 <= self._selected_index < len(rows):
                step_list = self.query_one("#step-list", ScrollableContainer)
                step_list.scroll_to_widget(rows[self._selected_index], animate=False)
        except Exception:
            pass

    # ----- Navigation --------------------------------------------------------

    def _navigate_to(self, display_index: int) -> None:
        """Navigate to a step: update list selection + detail panel."""
        if display_index < 0 or display_index >= len(self._step_groups):
            return
        old = self._selected_index
        self._selected_index = display_index
        c = get_theme_colors(self.app)

        # Update row styles
        rows = list(self.query(".step-row").results(Static))
        if 0 <= old < len(rows):
            rows[old].update(_render_step_row(self._step_groups[old], False, c))
            rows[old].remove_class("step-row--selected")
        if 0 <= display_index < len(rows):
            rows[display_index].update(
                _render_step_row(self._step_groups[display_index], True, c)
            )
            rows[display_index].add_class("step-row--selected")
            rows[display_index].scroll_visible(animate=False)

        # Update minimap
        self._update_minimap(display_index)

        # Update detail panel
        self.call_later(self._update_detail)

    def _current_display_index(self) -> int:
        """Return the current selected display index."""
        return self._selected_index

    def _detail_has_focus(self) -> bool:
        """Check if the detail panel currently has focus."""
        try:
            detail = self.query_one("#step-detail", ScrollableContainer)
            return self.focused is detail or (
                self.focused is not None and self.focused.parent is detail
            )
        except Exception:
            return False

    def action_cursor_down(self) -> None:
        if self._detail_has_focus():
            self.query_one("#step-detail", ScrollableContainer).scroll_down()
        else:
            self._navigate_to(self._selected_index + 1)

    def action_cursor_up(self) -> None:
        if self._detail_has_focus():
            self.query_one("#step-detail", ScrollableContainer).scroll_up()
        else:
            self._navigate_to(self._selected_index - 1)

    def action_next_step(self) -> None:
        self._navigate_to(self._selected_index + 1)

    def action_prev_step(self) -> None:
        self._navigate_to(self._selected_index - 1)

    def action_cursor_right(self) -> None:
        self.query_one("#step-detail", ScrollableContainer).focus()

    def action_cursor_left(self) -> None:
        self.query_one("#step-list", ScrollableContainer).focus()

    def action_vim_left(self) -> None:
        self.action_cursor_left()

    def action_vim_right(self) -> None:
        self.action_cursor_right()

    def action_focus_next(self) -> None:
        """Cycle focus between step list and detail panel."""
        step_list = self.query_one("#step-list", ScrollableContainer)
        detail = self.query_one("#step-detail", ScrollableContainer)
        if self.focused is step_list or (
            self.focused and self.focused.parent is step_list
        ):
            detail.focus()
        else:
            step_list.focus()

    def action_focus_previous(self) -> None:
        self.action_focus_next()

    def on_click(self, event: Click) -> None:
        """Handle clicks on step rows."""
        rows = list(self.query(".step-row"))
        for i, row in enumerate(rows):
            if event.widget is row:
                self._navigate_to(i)
                break

    # ----- Search / jump -----------------------------------------------------

    def action_search(self) -> None:
        """Open the search input (type '/' if ask input is focused)."""
        try:
            ask_input = self.query_one("#ask-input", AskInput)
            if ask_input.has_focus:
                ask_input.insert("/")
                return
        except Exception:
            pass
        search = self.query_one("#search-input", Input)
        search.display = True
        search.value = self._search_query
        search.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search submission: find first match or cycle on repeat Enter."""
        if event.input.id != "search-input":
            return
        query = event.value.strip().lower()
        if not query:
            self._dismiss_search()
            return

        # Same query: cycle to next match
        if query == self._search_query and self._search_matches:
            self._search_match_idx = (self._search_match_idx + 1) % len(
                self._search_matches
            )
            self._navigate_to(self._search_matches[self._search_match_idx])
            self._update_search_status()
            self.query_one("#step-list", ScrollableContainer).focus()
            return

        # New query: find all matches
        self._search_query = query
        self._search_matches = [
            i for i, txt in enumerate(self._group_text) if query in txt
        ]

        if self._search_matches:
            # Jump to first match at or after current position
            current = self._current_display_index()
            self._search_match_idx = 0
            for j, di in enumerate(self._search_matches):
                if di >= current:
                    self._search_match_idx = j
                    break
            self._navigate_to(self._search_matches[self._search_match_idx])

        self._highlight_matches()
        self._update_search_status()
        self.query_one("#step-list", ScrollableContainer).focus()

    def _dismiss_search(self) -> None:
        """Hide the search bar and clear search state."""
        search = self.query_one("#search-input", Input)
        search.display = False
        status = self.query_one("#search-status", Static)
        status.display = False
        self._search_query = ""
        self._search_matches = []
        self._search_match_idx = 0
        # Remove match highlights
        self._highlight_matches()
        self.query_one("#step-list", ScrollableContainer).focus()

    def _update_search_status(self) -> None:
        """Update the search status bar with match count."""
        c = get_theme_colors(self.app)
        status = self.query_one("#search-status", Static)
        status.display = True
        if not self._search_matches:
            status.update(
                Text(f"  No matches for '{self._search_query}'", style=c.error)
            )
        else:
            total = len(self._search_matches)
            idx = self._search_match_idx + 1
            t = Text()
            t.append(f"  '{self._search_query}'", style=c.primary)
            t.append(f"  {idx}/{total}", style=f"bold {c.fg}")
            t.append("  n next  N prev  esc close", style=c.fg_muted)
            status.update(t)

    def _highlight_matches(self) -> None:
        """Add/remove visual highlight on matching step rows."""
        rows = list(self.query(".step-row").results(Static))
        match_set = set(self._search_matches)
        for i, row in enumerate(rows):
            if i in match_set and self._search_matches:
                row.add_class("--search-match")
            else:
                row.remove_class("--search-match")

    def action_search_next(self) -> None:
        """Jump to the next search match."""
        if not self._search_matches:
            return
        self._search_match_idx = (self._search_match_idx + 1) % len(
            self._search_matches
        )
        self._navigate_to(self._search_matches[self._search_match_idx])
        self._update_search_status()

    def action_search_prev(self) -> None:
        """Jump to the previous search match."""
        if not self._search_matches:
            return
        self._search_match_idx = (self._search_match_idx - 1) % len(
            self._search_matches
        )
        self._navigate_to(self._search_matches[self._search_match_idx])
        self._update_search_status()

    # ----- Violation navigation (d / D) --------------------------------------

    def action_next_violation(self) -> None:
        """Jump to the next DENY/ESCALATE group."""
        if not self._violation_indices:
            self.notify("No violations in this trajectory", severity="information")
            return
        current = self._current_display_index()
        for di in self._violation_indices:
            if di > current:
                self._navigate_to(di)
                idx = self._violation_indices.index(di)
                total = len(self._violation_indices)
                self.notify(f"Violation {idx + 1}/{total}", timeout=2)
                return
        # Wrap to first
        self._navigate_to(self._violation_indices[0])
        self.notify(f"Violation 1/{len(self._violation_indices)} (wrapped)", timeout=2)

    def action_prev_violation(self) -> None:
        """Jump to the previous DENY/ESCALATE group."""
        if not self._violation_indices:
            self.notify("No violations in this trajectory", severity="information")
            return
        current = self._current_display_index()
        for di in reversed(self._violation_indices):
            if di < current:
                self._navigate_to(di)
                idx = self._violation_indices.index(di)
                total = len(self._violation_indices)
                self.notify(f"Violation {idx + 1}/{total}", timeout=2)
                return
        # Wrap to last
        last = self._violation_indices[-1]
        self._navigate_to(last)
        total = len(self._violation_indices)
        self.notify(f"Violation {total}/{total} (wrapped)", timeout=2)

    def on_key(self, event) -> None:
        """Intercept keys before ScrollableContainer consumes them."""
        # Don't intercept when ask input is focused
        try:
            ask_input = self.query_one("#ask-input")
            if ask_input.has_focus:
                return
        except Exception:
            pass

        # Don't intercept when search input is focused
        search = self.query_one("#search-input", Input)
        if search.has_focus:
            return

        # Navigation keys: intercept before ScrollableContainer eats them
        key_actions = {
            "down": self.action_cursor_down,
            "up": self.action_cursor_up,
            "j": self.action_cursor_down,
            "k": self.action_cursor_up,
            "left": self.action_cursor_left,
            "right": self.action_cursor_right,
            "h": self.action_cursor_left,
            "l": self.action_cursor_right,
            "slash": self.action_search,
            "n": self.action_search_next,
            "N": self.action_search_prev,
            "left_square_bracket": self.action_prev_step,
            "right_square_bracket": self.action_next_step,
            "d": self.action_next_violation,
            "D": self.action_prev_violation,
        }
        action = key_actions.get(event.key)
        if action is not None:
            action()
            event.stop()
