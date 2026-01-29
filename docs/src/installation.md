---
title: Installation
description: Install Sondera Harness with your preferred package manager and framework
---

# Installation

Install Sondera Harness with your preferred package manager. Choose the extra that matches your agent framework.

---

## Requirements

- Python 3.12 or higher
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

Don't have uv? Install it:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Install

Pick your framework, then run one of the commands:

=== "LangGraph"

    **uv (recommended):**
    ```bash
    uv add "sondera-harness[langgraph]"
    ```
    **pip:**
    ```bash
    pip install "sondera-harness[langgraph]"
    ```

=== "Google ADK"

    **uv (recommended):**
    ```bash
    uv add "sondera-harness[adk]"
    ```
    **pip:**
    ```bash
    pip install "sondera-harness[adk]"
    ```

=== "Strands"

    **uv (recommended):**
    ```bash
    uv add "sondera-harness[strands]"
    ```
    **pip:**
    ```bash
    pip install "sondera-harness[strands]"
    ```

=== "Custom Agent"

    **uv (recommended):**
    ```bash
    uv add sondera-harness
    ```
    **pip:**
    ```bash
    pip install sondera-harness
    ```

---

## Verify Installation

Confirm the package installed correctly:

=== "uv"

    ```bash
    uv run python -c "from sondera import CedarPolicyHarness; print('Sondera Harness installed successfully!')"
    ```

=== "pip"

    ```bash
    python -c "from sondera import CedarPolicyHarness; print('Sondera Harness installed successfully!')"
    ```

---

## Configuration (Platform Only)

If you're using **Sondera Platform** (`SonderaRemoteHarness`), set your API credentials:

```bash
export SONDERA_HARNESS_ENDPOINT="your-harness.sondera.ai:443"
export SONDERA_API_TOKEN="<YOUR_SONDERA_API_KEY>"
```

Or create a `.env` file or `~/.sondera/env`:

```
SONDERA_HARNESS_ENDPOINT=your-harness.sondera.ai:443
SONDERA_API_TOKEN=<YOUR_SONDERA_API_KEY>
```

!!! note "Local evaluation doesn't need this"
    The Quickstart uses `CedarPolicyHarness` for local policy evaluation, which doesn't require API credentials. See [Deployment](deployment.md) for details on choosing local vs platform.

---

## Next Steps

- [Integrations](integrations/index.md) - Wire the harness into your framework
- [Writing Policies](writing-policies.md) - Learn Cedar syntax and patterns
