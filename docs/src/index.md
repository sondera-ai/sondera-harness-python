---
title: Sondera Harness
description: Deterministic guardrails for AI agents.
---

<div class="hero" markdown>

# Sondera Harness

**Deterministic guardrails for AI agents.**

Open-source. Works with LangGraph, ADK, Strands, or any custom agent.

[![PyPI version](https://img.shields.io/pypi/v/sondera-harness.svg)](https://pypi.org/project/sondera-harness/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/sondera-ai/sondera-harness-python/blob/main/LICENSE)

[:material-rocket-launch: Get Started](quickstart.md){ .md-button .md-button--primary }
[:material-github: GitHub](https://github.com/sondera-ai/sondera-harness-python){ .md-button .md-button--secondary }

</div>

---

## What is Sondera Harness?

Sondera Harness evaluates [Cedar](https://www.cedarpolicy.com/) policies before your agent's actions execute. When a policy denies an action, the agent gets a reason why and can try a different approach. Same input, same verdict. Deterministic, not probabilistic.

**Example policy:**

```cedar
@id("forbid-risky-fs-shell")
forbid(
  principal,
  action == Action::"Bash",
  resource
)
when {
  context has parameters &&
  (context.parameters.command like "*rm -rf /*" ||
   context.parameters.command like "*mkfs*" ||
   context.parameters.command like "*dd if=/dev/zero*" ||
   context.parameters.command like "*> /dev/sda*")
};
```

This policy stops your agent from running `rm -rf`, every time.

---

## Why Use Sondera Harness?

- **:material-navigation: Steer, don't block.** Denied actions include a reason. Return it to the model, and it tries something else.
- **:material-check-circle: Deterministic.** Stop debugging prompts. Rules are predictable.
- **:material-puzzle: Drop-in integration.** Native middleware for LangGraph, Google ADK, and Strands.
- **:material-replay: Full observability.** Every action, every decision, every reason. Audit-ready.

[:octicons-arrow-right-24: Learn about decisions](concepts/decisions.md)

[:octicons-arrow-right-24: Explore trajectories](concepts/trajectories.md)

---

## See Everything in Real-Time

The TUI shows trajectories, adjudications, and policy decisions as your agent runs.

<figure markdown="span">
  ![Sondera TUI](assets/sondera-tui.gif){ width="700" }
</figure>

```bash
uv run sondera   # or just `sondera` if installed globally via pip
```

!!! note "Platform only"
    The TUI requires [Sondera Platform](https://sondera.ai) (`SonderaRemoteHarness`). The local `CedarPolicyHarness` doesn't persist trajectory data.

---

## Installation

Python 3.12+ required.

=== "uv (recommended)"

    ```bash
    uv add sondera-harness
    ```

    With framework extras:
    ```bash
    uv add "sondera-harness[langgraph]"   # LangGraph
    uv add "sondera-harness[adk]"         # Google ADK
    uv add "sondera-harness[strands]"     # Strands
    ```

=== "pip"

    ```bash
    pip install sondera-harness
    ```

    With framework extras:
    ```bash
    pip install "sondera-harness[langgraph]"   # LangGraph
    pip install "sondera-harness[adk]"         # Google ADK
    pip install "sondera-harness[strands]"     # Strands
    ```

---

## Add Sondera Harness to Your Agent

=== "LangGraph"

    ```python
    from langchain.agents import create_agent
    from sondera import CedarPolicyHarness
    from sondera.langgraph import SonderaHarnessMiddleware, Strategy

    harness = CedarPolicyHarness(policy_set=policy, schema=schema)
    middleware = SonderaHarnessMiddleware(harness=harness, strategy=Strategy.STEER)

    agent = create_agent(model, tools=tools, middleware=[middleware])
    ```

    [:octicons-arrow-right-24: Full LangGraph guide](integrations/langgraph.md)

=== "Google ADK"

    ```python
    from google.adk import Agent, Runner
    from sondera import SonderaRemoteHarness
    from sondera.adk import SonderaHarnessPlugin

    harness = SonderaRemoteHarness()
    plugin = SonderaHarnessPlugin(harness=harness)

    runner = Runner(
        agent=agent,
        app_name="my-app",
        plugins=[plugin],
    )
    ```

    [:octicons-arrow-right-24: Full ADK guide](integrations/adk.md)

=== "Strands"

    ```python
    from strands import Agent
    from sondera import SonderaRemoteHarness
    from sondera.strands import SonderaHarnessHook

    harness = SonderaRemoteHarness()
    hook = SonderaHarnessHook(harness=harness)

    agent = Agent(
        model="anthropic.claude-3-5-sonnet-20241022-v2:0",
        hooks=[hook],
    )
    ```

    [:octicons-arrow-right-24: Full Strands guide](integrations/strands.md)

=== "Custom"

    ```python
    from sondera import CedarPolicyHarness, Stage, Role, ToolRequestContent

    harness = CedarPolicyHarness(policy_set=policy, schema=schema)
    await harness.initialize(agent=agent)

    result = await harness.adjudicate(
        Stage.PRE_TOOL, Role.MODEL,
        ToolRequestContent(tool_id="Bash", args={"command": cmd})
    )
    ```

    [:octicons-arrow-right-24: Full custom integration guide](integrations/custom.md)

---

## Local or Platform

**CedarPolicyHarness** evaluates policies locally with no network calls or external dependencies. Good for development and simple deployments.

**SonderaRemoteHarness** connects to [Sondera Platform](https://sondera.ai) for team policy management, dashboards, and centralized audit logs.

Both implement the same interface. Switch by changing one line.

[:octicons-arrow-right-24: Deployment options](deployment.md)

---

## Need Help?

- [:fontawesome-brands-discord: Join our Discord](https://discord.gg/8zMbcnDnZs) for questions and feedback
- [:fontawesome-brands-github: Open an issue](https://github.com/sondera-ai/sondera-harness-python/issues) to report bugs

---

<div class="center" markdown>

[:material-rocket-launch: Get Started](quickstart.md){ .md-button .md-button--primary }

</div>
