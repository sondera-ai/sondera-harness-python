"""Tool declarations and executor for LiteLLM function calling.

Uses the OpenAI-compatible tool format that LiteLLM supports across all
providers (Gemini, OpenAI, Anthropic, Ollama, vLLM, etc.).
"""

from __future__ import annotations

import functools
import inspect
import json
from typing import Any

from sondera.harness import TrajectoryStorage
from sondera.tui.ai.context import _enum_str
from sondera.types import Agent, Decision

_APP_ERROR = {"error": "App reference not available."}


def _require_app(func):
    """Decorator ensuring app reference is available for tool execution."""
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args, app=None, **kwargs):
            if not app:
                return _APP_ERROR
            return await func(*args, app=app, **kwargs)

        return async_wrapper

    @functools.wraps(func)
    def wrapper(*args, app=None, **kwargs):
        if not app:
            return _APP_ERROR
        return func(*args, app=app, **kwargs)

    return wrapper


# Settings keys the AI agent is allowed to modify, mapped to Settings field names
_MODIFIABLE_SETTINGS: dict[str, str] = {
    "AI_MODEL": "ai_model",
    "AI_MODEL_FAST": "ai_model_fast",
    "AI_API_KEY": "ai_api_key",
    "AI_API_BASE": "ai_api_base",
    "AI_HARNESS_ENABLED": "ai_harness_enabled",
}


def get_tool_declarations() -> list[dict[str, Any]]:
    """Return OpenAI-compatible tool declarations for governance tools."""
    return [
        {
            "type": "function",
            "function": {
                "name": "list_agents",
                "description": (
                    "List all registered agents with their names, IDs, and tool "
                    "counts. Use this to discover what agents exist, especially "
                    "when the user asks about agents not visible on the current screen."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_trajectory",
                "description": (
                    "Get the full step-by-step detail for a specific trajectory, "
                    "including every adjudication decision, tool calls, and policy "
                    "violations. Use this when the user asks about a specific "
                    "trajectory's steps or what happened during a particular run."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "trajectory_id": {
                            "type": "string",
                            "description": "The trajectory ID (full UUID or prefix).",
                        },
                    },
                    "required": ["trajectory_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_agent_trajectories",
                "description": (
                    "List recent trajectories for an agent. Returns trajectory IDs, "
                    "statuses, step counts, and violation counts. Use this to find "
                    "trajectories before drilling into one with get_trajectory."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_name_or_id": {
                            "type": "string",
                            "description": "Agent name (e.g. 'Trading Agent') or ID.",
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "Max trajectories to return (default 20).",
                        },
                    },
                    "required": ["agent_name_or_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_violations",
                "description": (
                    "List recent DENY and ESCALATE adjudication decisions. "
                    "Optionally filter by agent. Returns the decision, reason, "
                    "policy IDs, agent, and trajectory for each violation."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_name_or_id": {
                            "type": "string",
                            "description": (
                                "Agent name or ID to filter by. Omit for all agents."
                            ),
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "Max violations to return (default 30).",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_agent_details",
                "description": (
                    "Get full details for an agent: name, description, instruction, "
                    "tools, and configuration. Use this when the user asks about an "
                    "agent's setup or capabilities."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_name_or_id": {
                            "type": "string",
                            "description": "Agent name (e.g. 'Trading Agent') or ID.",
                        },
                    },
                    "required": ["agent_name_or_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "change_theme",
                "description": (
                    "Switch the dashboard theme. Call with no arguments to "
                    "list available themes, or pass a theme name to switch."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "theme": {
                            "type": "string",
                            "description": (
                                "Theme name to switch to. Omit to list all "
                                "available themes."
                            ),
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "take_screenshot",
                "description": (
                    "Save an SVG screenshot of the current dashboard screen."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "launch_screensaver",
                "description": (
                    "Launch the Flying Agents screensaver animation. "
                    "Agent cards fly across a starfield with wing colors "
                    "showing health status. Press any key to exit."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "show_keys",
                "description": (
                    "Toggle the keyboard shortcuts help panel that shows "
                    "all available key bindings for the current screen."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "preview_setting_update",
                "description": (
                    "Preview a settings change WITHOUT applying it. Shows the "
                    "current value and proposed new value. The user must confirm "
                    "before the change is applied. ALWAYS call this tool when the "
                    "user asks to change a setting, then ask them to confirm. "
                    "Modifiable: AI_MODEL, AI_MODEL_FAST, AI_API_KEY, AI_API_BASE, "
                    "AI_HARNESS_ENABLED. Read-only (not modifiable): "
                    "SONDERA_API_TOKEN, SONDERA_ENDPOINT."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": "The setting key to change.",
                            "enum": list(_MODIFIABLE_SETTINGS.keys()),
                        },
                        "value": {
                            "type": "string",
                            "description": (
                                "The new value. For AI_HARNESS_ENABLED use "
                                "'true' or 'false'."
                            ),
                        },
                    },
                    "required": ["key", "value"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "navigate_to_agent",
                "description": (
                    "Navigate the user to an agent's detail screen showing "
                    "its trajectories, violations, and metadata. Use when "
                    "the user says 'take me to', 'show me', or 'open' an agent."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_name_or_id": {
                            "type": "string",
                            "description": "Agent name (e.g. 'Trading Agent') or ID.",
                        },
                    },
                    "required": ["agent_name_or_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "navigate_to_trajectory",
                "description": (
                    "Navigate the user to a trajectory detail screen showing "
                    "step-by-step execution. Optionally jump to a specific step. "
                    "Use when the user says 'take me to', 'show me', or 'open' "
                    "a trajectory."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "trajectory_id": {
                            "type": "string",
                            "description": "Trajectory ID (full UUID or prefix).",
                        },
                        "step_number": {
                            "type": "integer",
                            "description": (
                                "1-based display step number to jump to. "
                                "Omit to start at the beginning."
                            ),
                        },
                        "denial_number": {
                            "type": "integer",
                            "description": (
                                "Jump to the Nth denial/violation "
                                "(e.g. 2 for second denial). "
                                "Takes priority over step_number."
                            ),
                        },
                    },
                    "required": ["trajectory_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "navigate_to_step",
                "description": (
                    "Navigate to a specific step within the currently open "
                    "trajectory. Use when the user says 'go to step N', "
                    "'show step N', or 'jump to step N' while already "
                    "viewing a trajectory."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "step_number": {
                            "type": "integer",
                            "description": (
                                "1-based display step number as shown in "
                                "the step list (the #N labels). Use the "
                                "numbers from the STEPS context."
                            ),
                        },
                    },
                    "required": ["step_number"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "navigate_to_denial",
                "description": (
                    "Navigate to the Nth denied or escalated step in the "
                    "currently open trajectory. Use when the user says "
                    "'go to the second deny', 'show the first violation', "
                    "'next denial', etc."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "denial_number": {
                            "type": "integer",
                            "description": (
                                "1-based denial number (e.g. 1 for first "
                                "denial, 2 for second). Defaults to 1."
                            ),
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "navigate_to_dashboard",
                "description": ("Return to the main dashboard from any screen."),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "navigate_to_violation",
                "description": (
                    "Find the first trajectory with policy violations (denied "
                    "or escalated steps) for an agent and navigate directly to "
                    "the violated step. Use when the user asks to see denials, "
                    "violations, or policy failures for an agent."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_name_or_id": {
                            "type": "string",
                            "description": "Agent name or ID.",
                        },
                    },
                    "required": ["agent_name_or_id"],
                },
            },
        },
    ]


def get_sdk_tools() -> list:
    """Convert OpenAI tool declarations to SDK Tool objects for agent registration."""
    from sondera import Parameter, Tool

    tools = []
    for decl in get_tool_declarations():
        func = decl["function"]
        props = func.get("parameters", {}).get("properties", {})
        sdk_params = [
            Parameter(
                name=name,
                description=prop.get("description", ""),
                type=prop.get("type", "string"),
            )
            for name, prop in props.items()
        ]
        tools.append(
            Tool(
                id=func["name"],
                name=func["name"],
                description=func.get("description", ""),
                parameters=sdk_params,
            )
        )
    return tools


# ---------------------------------------------------------------------------
# Agent name resolution
# ---------------------------------------------------------------------------


def _resolve_agent_id(
    name_or_id: str,
    agents: list[Agent],
    agents_map: dict[str, str],
) -> str | None:
    """Resolve a human-friendly name or partial ID to a full agent ID.

    Matching order:
    1. Exact ID match (full UUID)
    2. Exact name match (case-insensitive) via agents_map reverse lookup
    3. Substring match on name (case-insensitive)
    4. Prefix match on ID
    """
    needle = name_or_id.strip()
    if not needle:
        return None

    # 1. Exact ID
    for agent in agents:
        if agent.id == needle:
            return agent.id

    # 2. Exact name (case-insensitive)
    needle_lower = needle.lower()
    for agent in agents:
        if agent.name.lower() == needle_lower:
            return agent.id

    # 3. Substring match on name
    for agent in agents:
        if needle_lower in agent.name.lower():
            return agent.id

    # 4. Prefix match on ID
    for agent in agents:
        if agent.id.startswith(needle):
            return agent.id

    return None


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------


async def execute_tool(
    name: str,
    args: dict[str, Any],
    harness: TrajectoryStorage,
    agents: list[Agent],
    agents_map: dict[str, str],
    adjudications: list[Any] | None = None,
    pending_updates: dict[str, str] | None = None,
    app: Any = None,
) -> dict[str, Any]:
    """Dispatch a function call to the appropriate harness method.

    Returns a plain dict suitable for serialization as a FunctionResponse.
    """
    if name == "list_agents":
        return _exec_list_agents(agents, agents_map)
    if name == "get_trajectory":
        return await _exec_get_trajectory(
            args, harness, agents, agents_map, adjudications or []
        )
    if name == "list_agent_trajectories":
        return await _exec_list_agent_trajectories(args, harness, agents, agents_map)
    if name == "list_violations":
        return await _exec_list_violations(args, harness, agents, agents_map)
    if name == "get_agent_details":
        return await _exec_get_agent_details(args, agents, agents_map)
    if name == "change_theme":
        return _exec_change_theme(args, app=app)
    if name == "take_screenshot":
        return _exec_take_screenshot(app=app)
    if name == "launch_screensaver":
        return _exec_launch_screensaver(app=app)
    if name == "show_keys":
        return _exec_show_keys(app=app)
    if name == "preview_setting_update":
        return _exec_preview_setting_update(
            args, pending_updates if pending_updates is not None else {}
        )
    if name == "navigate_to_agent":
        return _exec_navigate_to_agent(args, agents, agents_map, app=app)
    if name == "navigate_to_trajectory":
        return await _exec_navigate_to_trajectory(
            args, harness, agents, agents_map, adjudications or [], app=app
        )
    if name == "navigate_to_step":
        return _exec_navigate_to_step(args, app=app)
    if name == "navigate_to_denial":
        return _exec_navigate_to_denial(args, app=app)
    if name == "navigate_to_dashboard":
        return _exec_navigate_to_dashboard(app=app)
    if name == "navigate_to_violation":
        return await _exec_navigate_to_violation(
            args, harness, agents, agents_map, app=app
        )
    return {"error": f"Unknown tool: {name}"}


# ---------------------------------------------------------------------------
# Individual tool implementations
# ---------------------------------------------------------------------------


def _exec_list_agents(
    agents: list[Agent],
    agents_map: dict[str, str],
) -> dict[str, Any]:
    return {
        "count": len(agents),
        "agents": [
            {
                "name": a.name,
                "id": a.id,
                "tools": len(a.tools),
            }
            for a in agents
        ],
    }


def _resolve_trajectory_id(prefix: str, adjudications: list[Any]) -> str | None:
    """Resolve a trajectory ID prefix to a full ID from cached adjudications."""
    if not prefix:
        return None
    # Collect unique trajectory IDs
    seen: set[str] = set()
    for adj in adjudications:
        tid = getattr(adj, "trajectory_id", "")
        if tid and tid not in seen:
            seen.add(tid)
            if tid == prefix:
                return tid
            if tid.startswith(prefix):
                return tid
    return None


async def _exec_get_trajectory(
    args: dict[str, Any],
    harness: TrajectoryStorage,
    agents: list[Agent],
    agents_map: dict[str, str],
    adjudications: list[Any] | None = None,
) -> dict[str, Any]:
    trajectory_id = str(args.get("trajectory_id", "")).strip()
    if not trajectory_id:
        return {"error": "trajectory_id is required"}

    # Try direct lookup first
    trajectory = await harness.get_trajectory(trajectory_id)

    # If not found and looks like a prefix, resolve from cached adjudications
    if trajectory is None and adjudications and len(trajectory_id) < 36:
        full_id = _resolve_trajectory_id(trajectory_id, adjudications)
        if full_id:
            trajectory = await harness.get_trajectory(full_id)

    if trajectory is None:
        return {"error": f"Trajectory {trajectory_id} not found"}

    return _serialize_adjudicated_trajectory(trajectory, agents_map)


async def _exec_list_agent_trajectories(
    args: dict[str, Any],
    harness: TrajectoryStorage,
    agents: list[Agent],
    agents_map: dict[str, str],
) -> dict[str, Any]:
    name_or_id = str(args.get("agent_name_or_id", "")).strip()
    page_size = int(args.get("page_size", 20))

    agent_id = _resolve_agent_id(name_or_id, agents, agents_map)
    if agent_id is None:
        return {"error": f"No agent found matching '{name_or_id}'"}

    agent_name = agents_map.get(agent_id, agent_id[:16])
    trajectories, _ = await harness.list_trajectories(
        agent_id=agent_id, page_size=min(page_size, 50)
    )
    return {
        "agent": agent_name,
        "agent_id": agent_id,
        "count": len(trajectories),
        "trajectories": [_serialize_trajectory_summary(t) for t in trajectories],
    }


async def _exec_list_violations(
    args: dict[str, Any],
    harness: TrajectoryStorage,
    agents: list[Agent],
    agents_map: dict[str, str],
) -> dict[str, Any]:
    name_or_id = str(args.get("agent_name_or_id", "")).strip() or None
    page_size = int(args.get("page_size", 30))

    agent_id = None
    if name_or_id:
        agent_id = _resolve_agent_id(name_or_id, agents, agents_map)
        if agent_id is None:
            return {"error": f"No agent found matching '{name_or_id}'"}

    # Strategy 1: server-side adjudication records
    records, _ = await harness.list_adjudications(
        agent_id=agent_id, page_size=min(page_size, 100)
    )
    violations = [
        r for r in records if r.adjudication.decision.value in ("deny", "escalate")
    ]
    if violations:
        return {
            "count": len(violations),
            "violations": [_serialize_violation(v, agents_map) for v in violations],
        }

    # Strategy 2: scan trajectories with deny/escalate counts and extract
    # denied steps directly. Active trajectories often don't appear in the
    # adjudication index yet, but their decision_summary is populated.
    try:
        trajectories, _ = await harness.list_trajectories(
            agent_id=agent_id,  # type: ignore[arg-type]
            page_size=20,
        )
        violated_tids = [
            t.id for t in trajectories if t.deny_count > 0 or t.escalate_count > 0
        ]
        if violated_tids:
            step_violations: list[dict[str, Any]] = []
            for tid in violated_tids[:5]:
                full = await harness.get_trajectory(tid)
                if full is None:
                    continue
                a_name = agents_map.get(full.agent_id, full.agent_id[:16])
                for i, step in enumerate(full.steps):
                    decision = _enum_str(step.adjudication.decision).upper()
                    if decision in ("DENY", "ESCALATE"):
                        v: dict[str, Any] = {
                            "decision": decision,
                            "agent": a_name,
                            "reason": step.adjudication.reason[:_TEXT_CAP],
                            "trajectory_id": tid,
                            "step_index": i,
                        }
                        if step.adjudication.policies:
                            v["policies"] = [
                                p.id for p in step.adjudication.policies[:5]
                            ]
                        step_violations.append(v)
                        if len(step_violations) >= page_size:
                            break
                if len(step_violations) >= page_size:
                    break
            if step_violations:
                return {
                    "count": len(step_violations),
                    "violations": step_violations,
                }
    except Exception:
        pass

    return {"count": 0, "violations": []}


async def _exec_get_agent_details(
    args: dict[str, Any],
    agents: list[Agent],
    agents_map: dict[str, str],
) -> dict[str, Any]:
    name_or_id = str(args.get("agent_name_or_id", "")).strip()
    agent_id = _resolve_agent_id(name_or_id, agents, agents_map)
    if agent_id is None:
        return {"error": f"No agent found matching '{name_or_id}'"}

    for agent in agents:
        if agent.id == agent_id:
            return _serialize_agent(agent)

    return {"error": f"Agent {agent_id} not found in local cache"}


# ---------------------------------------------------------------------------
# App action tools
# ---------------------------------------------------------------------------


@_require_app
def _exec_change_theme(args: dict[str, Any], app: Any) -> dict[str, Any]:
    """Switch the TUI theme or list available themes."""
    available = list(app._registered_themes.keys())
    theme = str(args.get("theme", "")).strip()
    if not theme:
        return {
            "current": app.theme,
            "available": available,
            "message": f"Current theme: {app.theme}. {len(available)} themes available.",
        }
    # Fuzzy match: normalize spaces/underscores to hyphens, case-insensitive
    if theme not in available:
        normalized = theme.lower().replace(" ", "-").replace("_", "-")
        for name in available:
            if name.lower() == normalized:
                theme = name
                break
        else:
            # Substring match as fallback
            for name in available:
                if normalized in name.lower():
                    theme = name
                    break
    if theme not in available:
        return {"error": f"Unknown theme '{theme}'. Available: {', '.join(available)}"}
    previous = app.theme
    if theme == previous:
        return {"theme": theme, "message": f"Already using {theme}."}
    app.theme = theme
    return {"theme": theme, "previous": previous, "message": f"Switched to {theme}."}


@_require_app
def _exec_take_screenshot(app: Any) -> dict[str, Any]:
    """Save an SVG screenshot of the current screen."""
    try:
        path = app.save_screenshot()
        return {"path": str(path), "message": f"Screenshot saved to {path}."}
    except Exception as e:
        return {"error": f"Screenshot failed: {e}"}


@_require_app
def _exec_launch_screensaver(app: Any) -> dict[str, Any]:
    """Launch the Flying Agents screensaver."""
    try:
        app.action_screensaver()
        return {"message": "Screensaver launched. Press any key to exit."}
    except Exception as e:
        return {"error": f"Screensaver failed: {e}"}


@_require_app
def _exec_show_keys(app: Any) -> dict[str, Any]:
    """Toggle the keys/help panel."""
    try:
        if app.screen.query("HelpPanel"):
            app.action_hide_help_panel()
            return {"visible": False, "message": "Keys panel hidden."}
        else:
            app.action_show_help_panel()
            return {"visible": True, "message": "Keys panel shown."}
    except Exception as e:
        return {"error": f"Keys panel failed: {e}"}


# ---------------------------------------------------------------------------
# Navigation tools
# ---------------------------------------------------------------------------


def _deferred_step_navigate(screen: Any, display_index: int, app: Any) -> None:
    """Schedule in-screen step navigation on the next message pump cycle.

    Tool calls run inside the streaming async worker. Calling _navigate_to
    directly can be overwritten by subsequent widget updates in the same
    render frame. Deferring with set_timer ensures the navigation runs
    after the current batch of updates is painted.
    """

    def _do_navigate() -> None:
        screen._navigate_to(display_index)
        screen.call_after_refresh(screen._scroll_to_selected)

    screen.set_timer(0.1, _do_navigate)
    app._ask_state.focus_pending = True


@_require_app
def _exec_navigate_to_agent(
    args: dict[str, Any],
    agents: list[Agent],
    agents_map: dict[str, str],
    app: Any,
) -> dict[str, Any]:
    """Navigate to an agent's detail screen."""

    name_or_id = str(args.get("agent_name_or_id", "")).strip()
    agent_id = _resolve_agent_id(name_or_id, agents, agents_map)
    if agent_id is None:
        return {"error": f"No agent found matching '{name_or_id}'."}

    agent = next((a for a in agents if a.id == agent_id), None)
    if agent is None:
        return {"error": f"Agent {agent_id} not found."}

    # Try to get status counts from the app's precomputed agent statuses
    kwargs: dict[str, Any] = {}
    for status in getattr(app, "_agent_statuses", []):
        if status.agent.id == agent_id:
            kwargs["denied_count"] = status.denied_count
            kwargs["awaiting_count"] = status.awaiting_count
            kwargs["total_trajectories"] = status.total_trajectories
            break

    from sondera.tui.screens.agent import AgentScreen

    app.push_screen(AgentScreen(agent, **kwargs))
    app._ask_state.focus_pending = True
    return {"navigated": agent.name, "screen": "agent_detail"}


@_require_app
async def _exec_navigate_to_trajectory(
    args: dict[str, Any],
    harness: Any,
    agents: list[Agent],
    agents_map: dict[str, str],
    adjudications: list[Any],
    app: Any,
) -> dict[str, Any]:
    """Navigate to a trajectory detail screen."""

    trajectory_id = str(args.get("trajectory_id", "")).strip()
    if not trajectory_id:
        return {"error": "trajectory_id is required."}

    # step_number is 1-based display index (matches context numbering)
    step_number = args.get("step_number")
    denial_number = args.get("denial_number")
    display_index: int | None = None
    if step_number is not None and denial_number is None:
        display_index = max(int(step_number) - 1, 0)

    # Fetch the full trajectory
    trajectory = await harness.get_trajectory(trajectory_id)

    # If not found and looks like a prefix, resolve from cached adjudications
    if trajectory is None and adjudications and len(trajectory_id) < 36:
        full_id = _resolve_trajectory_id(trajectory_id, adjudications)
        if full_id:
            trajectory = await harness.get_trajectory(full_id)

    if trajectory is None:
        return {"error": f"Trajectory {trajectory_id} not found."}

    from sondera.tui.screens.trajectory import (
        TrajectoryScreen,
        _build_step_groups,
        _enrich_step_groups,
    )

    # If denial_number is set, resolve it to a display index
    if denial_number is not None:
        dn = int(denial_number)
        groups = _build_step_groups(trajectory.steps)
        _enrich_step_groups(groups, trajectory.steps)
        violations = [
            g.display_index
            for g in groups
            if g.decision in (Decision.DENY, Decision.ESCALATE)
        ]
        if not violations:
            return {"error": "No violations in this trajectory."}
        if dn < 1 or dn > len(violations):
            return {
                "error": f"Only {len(violations)} violation(s), "
                f"but denial_number={dn} was requested."
            }
        display_index = violations[dn - 1]

    # If already viewing this trajectory, navigate within it instead of pushing
    current_screen = app.screen
    if (
        isinstance(current_screen, TrajectoryScreen)
        and current_screen.trajectory.id == trajectory.id
        and display_index is not None
    ):
        _deferred_step_navigate(current_screen, display_index, app)
    else:
        # For new screens, convert display index to raw step index
        raw_step: int | None = None
        if display_index is not None:
            groups = _build_step_groups(trajectory.steps)
            if 0 <= display_index < len(groups):
                raw_step = groups[display_index].step_indices[0]
        app.push_screen(TrajectoryScreen(trajectory, initial_step=raw_step))
        app._ask_state.focus_pending = True

    agent_name = agents_map.get(trajectory.agent_id, trajectory.agent_id[:16])
    result: dict[str, Any] = {
        "navigated": trajectory.id,
        "agent": agent_name,
        "screen": "trajectory_detail",
        "steps": len(trajectory.steps),
    }
    if denial_number is not None:
        result["jumped_to_denial"] = int(denial_number)
        if display_index is not None:
            result["step_number"] = display_index + 1
    elif step_number is not None:
        result["jumped_to_step"] = int(step_number)
    return result


@_require_app
def _exec_navigate_to_step(args: dict[str, Any], app: Any) -> dict[str, Any]:
    """Navigate to a step within the current trajectory screen."""

    from sondera.tui.screens.trajectory import TrajectoryScreen

    screen = app.screen
    if not isinstance(screen, TrajectoryScreen):
        return {"error": "Not currently viewing a trajectory."}

    step_number = int(args.get("step_number", 0))
    if step_number < 1:
        return {"error": "step_number must be >= 1."}

    # step_number is 1-based display index (matches context numbering)
    display_index = step_number - 1
    total_display = len(screen._step_groups)
    if display_index >= total_display:
        return {
            "error": f"Step {step_number} out of range "
            f"(trajectory has {total_display} display steps)."
        }

    _deferred_step_navigate(screen, display_index, app)

    return {
        "navigated_to_step": step_number,
        "total_steps": total_display,
        "screen": "trajectory_detail",
    }


@_require_app
def _exec_navigate_to_denial(args: dict[str, Any], app: Any) -> dict[str, Any]:
    """Navigate to the Nth denial within the current trajectory screen."""

    from sondera.tui.screens.trajectory import TrajectoryScreen

    screen = app.screen
    if not isinstance(screen, TrajectoryScreen):
        return {"error": "Not currently viewing a trajectory."}

    violations = screen._violation_indices
    if not violations:
        return {"error": "No violations in this trajectory."}

    denial_number = int(args.get("denial_number", 1))
    if denial_number < 1:
        denial_number = 1

    if denial_number > len(violations):
        return {
            "error": f"Only {len(violations)} violation(s) in this trajectory, "
            f"but denial_number={denial_number} was requested."
        }

    display_index = violations[denial_number - 1]
    _deferred_step_navigate(screen, display_index, app)

    # Report the display step number (1-based)
    return {
        "navigated_to_denial": denial_number,
        "total_violations": len(violations),
        "step_number": display_index + 1,
        "screen": "trajectory_detail",
    }


@_require_app
def _exec_navigate_to_dashboard(app: Any) -> dict[str, Any]:
    """Return to the main dashboard."""
    app.action_show_dashboard()
    # Dashboard AskPanel is already mounted (not newly created), so
    # focus_pending won't be consumed by _initial_sync. Schedule focus
    # directly after the screen transition settles.
    try:
        panel = app.screen.query_one("#ask-panel")
        panel.call_after_refresh(panel.focus_input)
    except Exception:
        pass
    return {"navigated": "dashboard", "screen": "dashboard"}


@_require_app
async def _exec_navigate_to_violation(
    args: dict[str, Any],
    harness: Any,
    agents: list[Agent],
    agents_map: dict[str, str],
    app: Any,
) -> dict[str, Any]:
    """Find the first trajectory with violations for an agent and navigate to it."""

    name_or_id = str(args.get("agent_name_or_id", "")).strip()
    agent_id = _resolve_agent_id(name_or_id, agents, agents_map)
    if agent_id is None:
        return {"error": f"No agent found matching '{name_or_id}'."}

    agent_name = agents_map.get(agent_id, agent_id[:16])
    errors: list[str] = []

    # Strategy 1: Check list_adjudications for server-recorded violations
    violated_tid: str | None = None
    initial_step: int | None = None
    try:
        records, _ = await harness.list_adjudications(agent_id=agent_id, page_size=50)
        violation = next(
            (
                r
                for r in records
                if r.adjudication.decision.value in ("deny", "escalate")
            ),
            None,
        )
        if violation:
            violated_tid = violation.trajectory_id
            initial_step = violation.step_index
    except Exception as e:
        errors.append(f"adjudications: {e}")

    # Strategy 2: Check decision_summary from listed trajectories
    trajectories: list[Any] = []
    if violated_tid is None:
        try:
            trajectories, _ = await harness.list_trajectories(
                agent_id=agent_id, page_size=20
            )
            for t in trajectories:
                if t.deny_count > 0 or t.escalate_count > 0:
                    violated_tid = t.id
                    break
        except Exception as e:
            errors.append(f"list_trajectories: {e}")

    # Strategy 3: Load recent trajectories fully and scan step-level decisions.
    # This catches violations in active/running trajectories where neither
    # list_adjudications nor decision_summary are populated.
    if violated_tid is None and trajectories:
        try:
            for t in trajectories[:10]:
                full = await harness.get_trajectory(t.id)
                if full is None:
                    continue
                for i, step in enumerate(full.steps):
                    decision = _enum_str(step.adjudication.decision).upper()
                    if decision in ("DENY", "ESCALATE"):
                        violated_tid = t.id
                        initial_step = i
                        break
                if violated_tid:
                    break
        except Exception as e:
            errors.append(f"scan: {e}")

    if violated_tid is None:
        msg = f"No violations found for {agent_name}."
        if errors:
            msg += f" Errors: {'; '.join(errors)}"
        return {"error": msg}

    # Fetch full trajectory (may already have it from strategy 3)
    trajectory = await harness.get_trajectory(violated_tid)
    if trajectory is None:
        return {"error": f"Could not load trajectory {violated_tid}."}

    # If we don't have a step index yet, scan steps
    if initial_step is None:
        for i, step in enumerate(trajectory.steps):
            decision = _enum_str(step.adjudication.decision).upper()
            if decision in ("DENY", "ESCALATE"):
                initial_step = i
                break

    from sondera.tui.screens.trajectory import TrajectoryScreen

    app.push_screen(TrajectoryScreen(trajectory, initial_step=initial_step))
    app._ask_state.focus_pending = True

    return {
        "navigated": trajectory.id,
        "agent": agent_name,
        "screen": "trajectory_detail",
        "violation_step": initial_step,
        "deny_count": trajectory.deny_count,
        "escalate_count": trajectory.escalate_count,
    }


# ---------------------------------------------------------------------------
# Settings tools
# ---------------------------------------------------------------------------


def _validate_setting_value(key: str, value: str) -> str | None:
    """Validate a setting value. Returns error message or None if valid."""
    if key in ("AI_MODEL", "AI_MODEL_FAST"):
        if not value.strip():
            return "Model name can't be empty."
        return None
    if key == "AI_API_KEY":
        # Allow empty to clear, but warn
        return None
    if key == "AI_API_BASE":
        if value.strip() and not value.startswith(("http://", "https://")):
            return "URL should start with http:// or https://."
        return None
    if key == "AI_HARNESS_ENABLED":
        if value.lower() not in ("true", "false", "1", "0", "yes", "no"):
            return "Must be true or false."
        return None
    return None


def _obfuscate_key(value: str | None) -> str:
    """Obfuscate an API key for display: show first 4 and last 4 chars."""
    if not value:
        return "(not set)"
    if len(value) <= 10:
        return value[:2] + "..." + value[-2:]
    return value[:4] + "..." + value[-4:]


def _exec_preview_setting_update(
    args: dict[str, Any],
    pending_updates: dict[str, str],
) -> dict[str, Any]:
    """Preview a setting change without applying it."""
    import sondera.settings as _settings

    key = str(args.get("key", "")).strip().upper()
    value = str(args.get("value", ""))

    if key not in _MODIFIABLE_SETTINGS:
        return {
            "error": f"'{key}' is not modifiable. Modifiable keys: {', '.join(_MODIFIABLE_SETTINGS)}"
        }

    # Validate
    error = _validate_setting_value(key, value)
    if error:
        return {"error": error}

    # Read current value
    field_name = _MODIFIABLE_SETTINGS[key]
    current = getattr(_settings.SETTINGS, field_name, None)

    # Obfuscate sensitive values
    is_sensitive = "KEY" in key or "TOKEN" in key
    display_current = (
        _obfuscate_key(str(current)) if is_sensitive and current else str(current)
    )
    display_new = _obfuscate_key(value) if is_sensitive else value

    # Store pending update (mutable dict shared with panel)
    pending_updates[key] = value

    result: dict[str, Any] = {
        "key": key,
        "current_value": display_current,
        "new_value": display_new,
        "status": "pending_confirmation",
        "message": "Ask the user to confirm this change. They can type 'yes' to apply or 'no' to cancel.",
    }

    # Warn about provider change for model settings
    if key in ("AI_MODEL", "AI_MODEL_FAST") and "/" in value:
        new_provider = value.split("/", 1)[0]
        current_provider = _settings.SETTINGS.ai_provider_name
        if new_provider != current_provider:
            result["note"] = (
                f"This changes the provider from {current_provider} to {new_provider}. Make sure the API key is compatible."
            )

    return result


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

_MAX_STEPS = 80
_TEXT_CAP = 500
# Budget (chars) for the serialized trajectory JSON sent back to the model.
# Keeps the function response small enough for Gemini to process effectively.
_TRAJECTORY_BUDGET = 12_000


def _serialize_adjudicated_trajectory(
    t: Any, agents_map: dict[str, str]
) -> dict[str, Any]:
    """Serialize an AdjudicatedTrajectory to a plain dict for the model.

    Prioritizes DENY/ESCALATE steps so the model always sees violations.
    For large trajectories, ALLOW steps get trimmed to stay within budget.
    """

    agent_name = agents_map.get(t.agent_id, t.agent_id[:16])
    result: dict[str, Any] = {
        "id": t.id,
        "agent": agent_name,
        "agent_id": t.agent_id,
        "status": _enum_str(t.status),
        "step_count": len(t.steps),
        "deny_count": t.deny_count,
        "escalate_count": t.escalate_count,
        "allow_count": t.allow_count,
    }
    if t.duration is not None:
        result["duration_seconds"] = round(t.duration, 1)

    # Separate violation steps (always included in full) from allow steps
    violation_indices: list[int] = []
    allow_indices: list[int] = []
    for i, step in enumerate(t.steps):
        decision = _enum_str(step.adjudication.decision).upper()
        if decision in ("DENY", "ESCALATE"):
            violation_indices.append(i)
        else:
            allow_indices.append(i)

    # Serialize all violation steps first (full detail, capped at 40)
    steps: list[dict[str, Any]] = []
    budget_used = 0
    for i in violation_indices[:40]:
        s = _serialize_adjudicated_step(i + 1, t.steps[i])
        steps.append(s)
    budget_used = len(json.dumps(steps))

    # Fill remaining budget with allow steps (abbreviated for large trajectories)
    is_large = len(t.steps) > 40
    text_cap = 150 if is_large else _TEXT_CAP
    allow_limit = min(len(allow_indices), _MAX_STEPS - len(steps))

    for i in allow_indices[:allow_limit]:
        s = _serialize_adjudicated_step(i + 1, t.steps[i], text_cap=text_cap)
        entry_size = len(json.dumps(s))
        if budget_used + entry_size > _TRAJECTORY_BUDGET:
            break
        steps.append(s)
        budget_used += entry_size

    # Sort by step number so the model sees chronological order
    steps.sort(key=lambda s: s.get("step", 0))

    omitted = len(t.steps) - len(steps)
    if omitted > 0:
        steps.append({"note": f"... {omitted} more steps omitted (mostly ALLOW)"})
    result["steps"] = steps
    result["note"] = (
        "Step numbers here are raw indices. The UI groups steps so display "
        "numbers may differ. Prefer the '#N' step numbers from the STEPS "
        "context when referencing steps to the user."
    )
    return result


def _serialize_adjudicated_step(
    num: int, step: Any, text_cap: int = _TEXT_CAP
) -> dict[str, Any]:
    """Serialize a single AdjudicatedStep."""
    adj = step.adjudication
    decision = _enum_str(adj.decision).upper()
    s: dict[str, Any] = {
        "step": num,
        "decision": decision,
        "stage": _enum_str(step.step.stage),
        "role": _enum_str(step.step.role),
    }
    # Content preview
    content = step.step.content
    if isinstance(content, dict):
        ctype = content.get("content_type", "")
        if ctype == "prompt":
            s["content"] = str(content.get("text", ""))[:text_cap]
        elif ctype == "tool_request":
            s["tool_id"] = content.get("tool_id", "")
            args_str = str(content.get("args", {}))[:text_cap]
            s["args"] = args_str
        elif ctype == "tool_response":
            s["tool_id"] = content.get("tool_id", "")
            s["response"] = str(content.get("response", ""))[:text_cap]
    elif hasattr(content, "content_type"):
        ctype = content.content_type
        if ctype == "prompt":
            s["content"] = str(content.text)[:text_cap]
        elif ctype == "tool_request":
            s["tool_id"] = content.tool_id
            s["args"] = str(content.args)[:text_cap]
        elif ctype == "tool_response":
            s["tool_id"] = content.tool_id
            s["response"] = str(content.response)[:text_cap]

    if decision != "ALLOW":
        s["reason"] = adj.reason[:text_cap]
        if adj.policies:
            s["policies"] = [p.id for p in adj.policies[:5]]

    return s


def _serialize_trajectory_summary(t: Any) -> dict[str, Any]:
    """Serialize a Trajectory (from list) to a summary dict."""
    result: dict[str, Any] = {
        "id": t.id,
        "status": _enum_str(t.status),
        "steps": t.step_count,
    }
    if t.deny_count > 0:
        result["denied"] = t.deny_count
    if t.escalate_count > 0:
        result["escalated"] = t.escalate_count
    if t.duration is not None:
        result["duration_seconds"] = round(t.duration, 1)
    return result


def _serialize_violation(record: Any, agents_map: dict[str, str]) -> dict[str, Any]:
    """Serialize an AdjudicationRecord to a violation dict."""
    agent_name = agents_map.get(record.agent_id, record.agent_id[:16])
    adj = record.adjudication
    result: dict[str, Any] = {
        "decision": _enum_str(adj.decision).upper(),
        "agent": agent_name,
        "reason": adj.reason[:_TEXT_CAP],
        "trajectory_id": record.trajectory_id,
    }
    if adj.policies:
        result["policies"] = [p.id for p in adj.policies[:5]]
    if record.step_index is not None:
        result["step_index"] = record.step_index
    return result


def _serialize_agent(agent: Any) -> dict[str, Any]:
    """Serialize an Agent to a detail dict."""
    result: dict[str, Any] = {
        "id": agent.id,
        "name": agent.name,
    }
    if agent.description:
        result["description"] = agent.description[:_TEXT_CAP]
    if agent.instruction:
        result["instruction"] = agent.instruction[:_TEXT_CAP]
    if agent.tools:
        result["tools"] = [
            {
                "name": t.name,
                "description": t.description[:200] if t.description else "",
            }
            for t in agent.tools
        ]
    return result
