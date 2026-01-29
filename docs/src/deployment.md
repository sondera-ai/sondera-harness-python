---
title: Deployment
description: Choose between local Cedar policies or Sondera Platform
---

# Deployment

When you integrate Sondera Harness into your agent, you need to choose where policy evaluation happens. This page helps you understand your options and pick the right one for your situation.

**What you're deploying:** Your agent code stays the same either way. You're choosing where your *policies* live and where *evaluation* happens:

- **Platform:** Policies are managed in Sondera (cloud, self-hosted, or VPC) with built-in tooling
- **Local:** Policies are defined in your code and evaluated on the same machine

Both options use the same policy language ([Cedar](https://www.cedarpolicy.com/)) and the same harness interface. You can start local and move to Platform later without changing your agent code.

---

## Which Should I Choose?

<div class="grid cards" markdown>

-   :material-cloud:{ .lg .middle } **Platform**

    ---

    Choose Platform (`SonderaRemoteHarness`) when you need:

    - Policy management across multiple agents
    - Pre-built policy packs for common use cases
    - Audit logs and compliance reporting
    - Team collaboration and access control
    - Air-gapped or on-prem deployment options

    [:octicons-arrow-right-24: Platform setup](#platform-sonderaremoteharness)

-   :material-laptop:{ .lg .middle } **Local**

    ---

    Choose local (`CedarPolicyHarness`) when you want:

    - Quick experimentation without an account
    - A handful of policies you manage yourself
    - Zero external dependencies

    [:octicons-arrow-right-24: Local setup](#local-cedarpolicyharness)

</div>

---

## Platform (SonderaRemoteHarness)

Platform evaluation sends requests to Sondera (cloud, self-hosted, or VPC). Policies are managed through the web UI or API.

### Getting Started

1. **Sign up** at [sondera.ai](https://sondera.ai) with Google or GitHub
2. **Create an API token** in Settings → API Tokens
3. **Set your credentials** via environment variables:

```bash
export SONDERA_HARNESS_ENDPOINT="your-harness.sondera.ai:443"
export SONDERA_API_TOKEN="<YOUR_SONDERA_API_KEY>"
```

Or create a `.env` file or `~/.sondera/env`:

```
SONDERA_HARNESS_ENDPOINT=your-harness.sondera.ai:443
SONDERA_API_TOKEN=<YOUR_SONDERA_API_KEY>
```

### Setup

```{.python notest}
from sondera import SonderaRemoteHarness, Agent

# Create harness (reads SONDERA_API_TOKEN from environment)
harness = SonderaRemoteHarness()

# Define your agent
agent = Agent(
    id="my-agent",
    name="My_Agent",
    description="What this agent does",
)

# Start a trajectory
await harness.initialize(agent=agent)
```

That's it. Policies are managed in the Platform web UI.

---

## Local (CedarPolicyHarness)

Local evaluation runs entirely on your machine. Policies are defined in your code or loaded from files.

### Setup

```{.python notest}
from sondera.harness import CedarPolicyHarness
from sondera import Agent

# Define Cedar policies
policies = '''
@id("forbid-dangerous-bash")
forbid(
  principal,
  action == Coding_Agent::Action::"Bash",
  resource
)
when {
  context has parameters &&
  (context.parameters.command like "*rm -rf /*" ||
   context.parameters.command like "*mkfs*" ||
   context.parameters.command like "*dd if=/dev/zero*" ||
   context.parameters.command like "*> /dev/sda*")
};
'''

# Generate Cedar schema from the agent
schema = agent_to_cedar_schema(my_agent)

# Create local policy engine
harness = CedarPolicyHarness(
    policy_set=policies,
    schema=schema,
)

await harness.initialize()
# Use same adjudication API as RemoteHarness
```

For larger policy sets, load from `.cedar` files:

```{.python notest}
from pathlib import Path

policies = Path("policies/agent.cedar").read_text()
harness = CedarPolicyHarness(
    policy_set=policies,
    schema=schema,
)
```

### Switching to Platform

Both harnesses share the same interface. When you're ready to move to Platform, it's a one-line change:

```{.python notest}
# Before
harness = CedarPolicyHarness(policy_set=policies, agent=my_agent)

# After
harness = SonderaRemoteHarness()
```

---

## Configuration Reference

### Environment Variables

| Variable | Description | Default |
|:---------|:------------|:--------|
| `SONDERA_HARNESS_ENDPOINT` | Platform gRPC endpoint | `harness.sondera.ai:443` |
| `SONDERA_API_TOKEN` | Your API token | Required for Platform |

### Platform Options

| Parameter | Type | Description |
|:----------|:-----|:------------|
| `sondera_harness_endpoint` | `str` | Platform endpoint (overrides env var) |
| `sondera_api_key` | `str` | API token (overrides env var) |

### Local Options

| Parameter | Type | Description |
|:----------|:-----|:------------|
| `policy_set` | `str` | Cedar policies as a string |
| `schema` | `str` | Cedar schema (use `agent_to_cedar_schema()` to generate) |

---

## Next Steps

- [Integrations](integrations/index.md): Wire Sondera into LangGraph, Google ADK, or Strands
- [Writing Policies](writing-policies.md): Define what your agent can and can't do
