<div align="center">

  <h1>Sondera Harness</h1>

  <p><strong>Deterministic guardrails for AI agents.</strong></p>

  <p>Open-source. Works with LangGraph, ADK, Strands, or any custom agent.</p>

  <p>
    <a href="https://docs.sondera.ai/">Docs</a>
    ·
    <a href="https://docs.sondera.ai/quickstart/">Quickstart</a>
    ·
    <a href="https://github.com/sondera-ai/sondera-harness-python/tree/main/examples">Examples</a>
    ·
    <a href="https://join.slack.com/t/sonderacommunity/shared_invite/zt-3onw10qhj-5UNQ7EMuAbPk0nTwh_sNcw">Slack</a>
  </p>

  <p>
    <a href="https://pypi.org/project/sondera-harness/"><img src="https://img.shields.io/pypi/v/sondera-harness.svg" alt="PyPI version"></a>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python 3.12+"></a>
    <a href="LICENSE"><img src="https://img.shields.io/github/license/sondera-ai/sondera-harness-python.svg" alt="License: MIT"></a>
  </p>

</div>

---

## What is Sondera Harness?

Sondera Harness evaluates [Cedar](https://www.cedarpolicy.com/) policies before your agent's actions execute. When a policy denies an action, the agent gets a reason why and can try a different approach. Same input, same verdict. Deterministic, not probabilistic.

**Example policy:**

```cedar
forbid(principal, action, resource)
when { context has parameters_json && context.parameters_json like "*rm -rf*" };
```

This policy stops your agent from running `rm -rf`, every time.

## Quickstart

> **Try it now:** [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/sondera-ai/sondera-harness-python/blob/main/docs/src/notebooks/quickstart.ipynb) - no install required.

### 1. Install

```bash
uv add "sondera-harness[langgraph]"   # or: pip install "sondera-harness[langgraph]"
```

Works with [LangChain/LangGraph](https://docs.sondera.ai/integrations/langgraph/), [Google ADK](https://docs.sondera.ai/integrations/adk/), [Strands](https://docs.sondera.ai/integrations/strands/), and [custom agents](https://docs.sondera.ai/integrations/custom/).

### 2. Add to Your Agent (LangGraph)

```python
from langchain.agents import create_agent
from sondera.harness import SonderaRemoteHarness
from sondera.langgraph import SonderaHarnessMiddleware, Strategy, create_agent_from_langchain_tools

# Analyze your tools and create agent metadata
sondera_agent = create_agent_from_langchain_tools(
    tools=my_tools,
    agent_id="langchain-agent",
    agent_name="My LangChain Agent",
    agent_description="An agent that helps with tasks",
)

# Create harness with agent
harness = SonderaRemoteHarness(agent=sondera_agent)

# Create middleware
middleware = SonderaHarnessMiddleware(
    harness=harness,
    strategy=Strategy.BLOCK,  # or Strategy.STEER
)

# Create agent with middleware
agent = create_agent(
    model=my_model,
    tools=my_tools,
    middleware=[middleware],
)
```

> [!NOTE]
> This example uses Sondera Platform ([free account](https://sondera.ai)), which also enables the TUI below. For local-only development, see [CedarPolicyHarness](https://docs.sondera.ai/integrations/custom/).

### 3. See It in Action

<div align="center">
  <img src="docs/src/assets/sondera-tui.gif" alt="Sondera TUI" width="700" />
</div>

```bash
uv run sondera   # or: sondera (if installed via pip)
```

## Why Sondera Harness?

- **Steer, don't block:** Denied actions include a reason. Return it to the model, and it tries something else.
- **Deterministic:** Stop debugging prompts. Rules are predictable.
- **Drop-in integration:** Native middleware for LangGraph, Google ADK, and Strands.
- **Full observability:** Every action, every decision, every reason. Audit-ready.

## Documentation

- [Quickstart](https://docs.sondera.ai/quickstart/)
- [Writing Policies](https://docs.sondera.ai/writing-policies/)
- [Integrations](https://docs.sondera.ai/integrations/)
- [Reference](https://docs.sondera.ai/reference/)

## Community

- [Slack](https://join.slack.com/t/sonderacommunity/shared_invite/zt-3onw10qhj-5UNQ7EMuAbPk0nTwh_sNcw) for questions and feedback
- [GitHub Issues](https://github.com/sondera-ai/sondera-harness-python/issues) for bugs
- [Contributing](CONTRIBUTING.md) for development setup

## License

[MIT](LICENSE)
