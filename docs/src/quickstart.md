---
title: Quickstart
description: Run your first policy evaluation in under a minute
---

# Quickstart

## Why Sondera Harness

The more you trust an agent, the more you can let it do. But trust requires guarantees.

Sondera Harness lets you define what's allowed in code. The agent stays within those limits, or it doesn't act. No hoping the prompt works. Bounded agents are reliable. Reliable agents can do more.

---

**Want to try it now?** Open the notebook in Colab and run it in your browser. No setup required.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/sondera-ai/sondera-harness-python/blob/main/docs/src/notebooks/quickstart.ipynb){target="_blank"}

---

## Install

Python 3.12+ required. Clone the repo to get started:

=== "uv (recommended)"

    Don't have uv? Install it first:
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

    Then clone and install:
    ```bash
    git clone https://github.com/sondera-ai/sondera-harness-python.git
    cd sondera-harness-python
    uv sync --all-extras --group examples
    ```

=== "pip"

    ```bash
    git clone https://github.com/sondera-ai/sondera-harness-python.git
    cd sondera-harness-python
    pip install -e ".[examples]"
    ```

---

## What happens when an agent runs `rm -rf /`?

Nothing, if your policy blocks it.

We'll walk through [`examples/cedar/coding_agent.py`](https://github.com/sondera-ai/sondera-harness-python/blob/main/examples/cedar/coding_agent.py). It simulates a coding agent making requests - reading files, writing to `.env`, running bash - and shows which actions the policy allows or blocks. **Nothing actually executes.** It's safe to try.

The example creates a policy for a coding agent:

- **Allow** reading any file
- **Allow** writing files, *except* `.env`, credentials, and secrets
- **Allow** bash commands, *except* destructive ones like `rm -rf /`

The policy is written in [Cedar](https://www.cedarpolicy.com/), a language designed for authorization. Cedar checks *who* (principal) can do *what* (action) on *which* (resource). The pattern: **permit by default, then forbid specific things**. See [Writing Policies](writing-policies.md) for the full syntax.

```cedar
// Allow writing files
@id("allow-write")
permit(principal, action == Coding_Agent::Action::"Write", resource);

// But not sensitive ones
@id("forbid-sensitive-write")
forbid(principal, action == Coding_Agent::Action::"Write", resource)
when {
  context has parameters &&
  (context.parameters.file_path like "*.env*" ||
   context.parameters.file_path like "*credentials*")
};

// Allow bash commands
@id("allow-bash")
permit(principal, action == Coding_Agent::Action::"Bash", resource);

// But not dangerous ones
@id("forbid-dangerous-bash")
forbid(principal, action == Coding_Agent::Action::"Bash", resource)
when {
  context has parameters &&
  context.parameters.command like "*rm -rf /*"
};
```

**Key insight:** `forbid` always wins over `permit`. This lets you start permissive and layer on restrictions.

!!! note "Where does `Coding_Agent` come from?"
    The namespace is generated from your agent's tools. Sondera inspects your tool definitions and creates a Cedar schema automatically. See [Writing Policies](writing-policies.md) for details.

---

## How It Works

The example loads the policy into a `CedarPolicyHarness`, then calls `adjudicate()` for each action the agent wants to take. The harness returns `ALLOW` or `DENY`:

```{.python notest}
from sondera import CedarPolicyHarness, Decision, Stage, Role, ToolRequestContent

# Create harness with your policy
harness = CedarPolicyHarness(policy_set=policy_set, schema=schema)
await harness.initialize(agent=agent)

# Ask: "Would writing to .env be allowed?"
result = await harness.adjudicate(
    Stage.PRE_TOOL,                    # Check before the tool runs
    Role.MODEL,                        # The AI model is requesting this
    ToolRequestContent(
        tool_id="Write",
        args={"file_path": "/code/.env", "content": "SECRET=xxx"}
    ),
)
print(result.decision)  # Decision.DENY - blocked by policy

# Ask: "Would running 'git status' be allowed?"
result = await harness.adjudicate(
    Stage.PRE_TOOL,
    Role.MODEL,
    ToolRequestContent(tool_id="Bash", args={"command": "git status"}),
)
print(result.decision)  # Decision.ALLOW - safe command
```

`Stage.PRE_TOOL` means "check this before executing the tool." `Role.MODEL` indicates the AI requested this action. See [Stages](concepts/stages.md) and [Decisions](concepts/decisions.md) for more.

---

## Run It

Run the example to see the policy in action. This only evaluates decisions - **no actual commands execute**:

```bash
uv run python examples/cedar/coding_agent.py
```

```
SUCCESS  | Reading a file (Decision.ALLOW)
ERROR    | Writing to .env file (Decision.DENY)
SUCCESS  | Writing to test file (Decision.ALLOW)
ERROR    | Dangerous bash command (Decision.DENY)
SUCCESS  | Safe bash command (Decision.ALLOW)
ERROR    | Editing SSH key (Decision.DENY)
```

The policy worked: safe operations allowed, dangerous ones blocked.

---

## Try It Yourself

You just ran your first policy evaluation. Now experiment with the example:

- **Block a new command** - Add a `forbid` rule for `curl` or `wget` and test it
- **Allow a blocked path** - Remove `*.env*` from the forbid rule and see `.env` writes succeed
- **Add a new test** - Copy an `adjudicate()` call and try a different tool or argument
- **Change the pattern** - Try `*password*` or `*secret*` in a `like` clause

The example is yours to break and rebuild.

---

## Next Steps

- [Integrations](integrations/index.md) - Add Sondera to LangGraph, ADK, or Strands
- [Writing Policies](writing-policies.md) - Cedar syntax and common patterns
- [Core Concepts](concepts/index.md) - Understand stages, decisions, and trajectories
