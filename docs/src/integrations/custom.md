---
title: Custom Agent Integration
description: Use the Sondera Harness API directly for any agent architecture
---

# Custom Agent Integration

Easily add [policy](../concepts/policies.md) enforcement to any agent using the Sondera Harness API directly. This guide covers installation, configuration, handling policy denials, and working examples.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/sondera-ai/sondera-harness-python/blob/main/docs/src/notebooks/custom.ipynb){target="_blank"}

---

## Installation

=== "uv"

    ```bash
    uv add sondera-harness
    ```

=== "pip"

    ```bash
    pip install sondera-harness
    ```

---

## Configuration

Set your API credentials via environment variables:

```bash
export SONDERA_API_TOKEN="<your-api-key>"
export SONDERA_HARNESS_ENDPOINT="harness.sondera.ai"  # Optional, this is the default
```

Or create a `.env` file (project root or `~/.sondera/env`):

```
SONDERA_API_TOKEN=<your-api-key>
SONDERA_HARNESS_ENDPOINT=harness.sondera.ai  # Optional
```

---

## Quick Start

Use the Sondera Harness API directly for full control over policy enforcement:

```{.python notest}
from sondera import SonderaRemoteHarness, Agent, Decision, PromptContent, Role, Stage

# Create a harness instance
harness = SonderaRemoteHarness(
    sondera_harness_endpoint="localhost:50051",
    sondera_api_key="<YOUR_SONDERA_API_KEY>",
    sondera_harness_client_secure=True,  # Enable TLS for production
)

# Define your agent
agent = Agent(
    id="my-agent",
    provider_id="custom",
    name="My Assistant",
    description="A helpful AI assistant",
    instruction="Be helpful, accurate, and safe",
    tools=[],
)

# Initialize a trajectory
await harness.initialize(agent=agent)

# Adjudicate user input
adjudication = await harness.adjudicate(
    Stage.PRE_MODEL,
    Role.USER,
    PromptContent(text="Hello, can you help me?"),
)

if adjudication.decision == Decision.ALLOW:
    # Proceed with agent logic
    pass
elif adjudication.decision == Decision.DENY:
    print(f"Request blocked: {adjudication.reason}")

# Finalize the trajectory
await harness.finalize()
```

[:octicons-arrow-right-24: Learn how to write policies](../writing-policies.md)

---

## How It Works

You control exactly when policies are evaluated by calling `adjudicate()`:

| Your Code | Stage | What to Check |
|:----------|:------|:--------------|
| Before each model call | `PRE_MODEL` | User input, context |
| After model responds | `POST_MODEL` | Model output |
| Before tool execution | `PRE_TOOL` | Tool arguments |
| After tool completes | `POST_TOOL` | Tool results |

[:octicons-arrow-right-24: See the full agent loop diagram](../concepts/stages.md)

---

## Handling Decisions

The `adjudicate()` method returns an `Adjudication` object with the policy decision:

| Property | Description |
|:---------|:------------|
| `adjudication.decision` | `Decision.ALLOW`, `Decision.DENY`, or `Decision.ESCALATE` |
| `adjudication.reason` | Explanation of why the action was denied or escalated |

### BLOCK Pattern

Stop execution immediately on denial. Use for security-critical actions:

```{.python notest}
from sondera import Decision

adjudication = await harness.adjudicate(Stage.PRE_TOOL, Role.MODEL, tool_content)

if adjudication.decision == Decision.DENY:
    await harness.finalize()
    raise Exception(f"Action blocked: {adjudication.reason}")

# Only execute if allowed
result = my_tool_function(**tool_args)
```

### STEER Pattern

Feed the denial back to the model so it can try a different approach:

```{.python notest}
from sondera import Decision

adjudication = await harness.adjudicate(Stage.PRE_TOOL, Role.MODEL, tool_content)

if adjudication.decision == Decision.DENY:
    # Add denial to conversation so model can adapt
    messages.append({
        "role": "user",
        "content": f"Tool blocked: {adjudication.reason}. Try a different approach."
    })
    # Continue the agent loop - model will try something else
```

!!! tip "STEER keeps agents running"
    With STEER, the agent learns from policy feedback and can self-correct. This is more robust than hard blocking for autonomous agents.

---

## Local Cedar Policies

Use `CedarPolicyHarness` to evaluate policies locally without connecting to Sondera Platform:

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

# Create local policy engine
harness = CedarPolicyHarness(
    policy_set=policies,
    agent=my_agent,
)

await harness.initialize()
# Use same adjudication API as RemoteHarness
```

[:octicons-arrow-right-24: Full example: Coding Agent](https://github.com/sondera-ai/sondera-harness-python/blob/main/examples/cedar/coding_agent.py)

---

## Handling Escalations

When a policy uses the `@escalate` annotation, the harness returns `Decision.ESCALATE` instead of `Decision.DENY`. This signals that the action needs approval before proceeding, rather than being blocked outright.

### Basic Escalation Pattern

```python
from sondera import CedarPolicyHarness, Decision, ToolRequestContent, Stage, Role

async def execute_with_escalation(harness: CedarPolicyHarness, tool_call: dict) -> str:
    """Execute a tool call, handling escalations for approval."""

    result = await harness.adjudicate(
        Stage.PRE_TOOL,
        Role.MODEL,
        ToolRequestContent(
            tool_id=tool_call["name"],
            parameters=tool_call["args"],
        ),
    )

    if result.decision == Decision.ALLOW:
        return execute_tool(tool_call)

    if result.decision == Decision.DENY:
        # Hard denial - do not allow override
        return f"Action '{tool_call['name']}' blocked: {result.reason}"

    if result.decision == Decision.ESCALATE:
        # Escalation - request approval before proceeding
        annotation = result.annotations[0]
        print(f"Action requires approval: {tool_call['name']}")
        print(f"Reason: {annotation.description}")
        print(f"Route to: {annotation.escalate_arg}")  # e.g., "finance-team"

        approved = await request_approval(
            action=tool_call["name"],
            args=tool_call["args"],
            reason=annotation.description,
            route_to=annotation.escalate_arg,
        )

        if approved:
            return execute_tool(tool_call)  # Your tool execution function
        else:
            return f"Action '{tool_call['name']}' was rejected."


async def request_approval(action: str, args: dict, reason: str, route_to: str) -> bool:
    """Request approval for an escalated action.

    Replace this with your actual approval mechanism:
    - Slack notification (route to specific channel based on route_to)
    - Email approval
    - Web UI confirmation
    - CLI prompt
    """
    # Example: simple CLI prompt
    response = input(f"[{route_to}] Approve '{action}' with args {args}? (y/n): ")
    return response.lower() == "y"
```

### Webhook-Based Escalation

For production systems, use webhooks or message queues. The `escalate_arg` can route approvals to different teams:

```python
import httpx
from sondera import CedarPolicyHarness, Decision, ToolRequestContent, Stage, Role

# Map escalate_arg values to Slack webhook URLs
SLACK_WEBHOOKS = {
    "finance-team": "https://hooks.slack.com/services/xxx/finance",
    "ops-team": "https://hooks.slack.com/services/xxx/ops",
    "security-team": "https://hooks.slack.com/services/xxx/security",
}

async def escalate_to_slack(harness: CedarPolicyHarness, tool_call: dict) -> str:
    """Escalate actions to the appropriate Slack channel for approval."""

    result = await harness.adjudicate(
        Stage.PRE_TOOL,
        Role.MODEL,
        ToolRequestContent(
            tool_id=tool_call["name"],
            parameters=tool_call["args"],
        ),
    )

    if result.decision == Decision.ALLOW:
        return execute_tool(tool_call)  # Your tool execution function

    if result.decision == Decision.DENY:
        return f"Action blocked: {result.reason}"

    if result.decision == Decision.ESCALATE:
        annotation = result.annotations[0]
        webhook_url = SLACK_WEBHOOKS.get(annotation.escalate_arg)

        if not webhook_url:
            return f"No webhook configured for: {annotation.escalate_arg}"

        async with httpx.AsyncClient() as client:
            await client.post(webhook_url, json={
                "text": f"Action requires approval: {tool_call['name']}",
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*Action:* `{tool_call['name']}`"},
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*Reason:* {annotation.description}"},
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {"type": "button", "text": {"type": "plain_text", "text": "Approve"}, "action_id": "approve"},
                            {"type": "button", "text": {"type": "plain_text", "text": "Reject"}, "action_id": "reject"},
                        ],
                    },
                ],
            })

        # In practice, you'd wait for a callback from Slack
        return f"Escalated to {annotation.escalate_arg} for approval"
```

---

## Examples

- [Coding Agent](https://github.com/sondera-ai/sondera-harness-python/blob/main/examples/cedar/coding_agent.py) - Local policy evaluation with `CedarPolicyHarness`

---

## Next Steps

- [:octicons-arrow-right-24: Writing Policies](../writing-policies.md) - Cedar syntax and common patterns
- [:octicons-arrow-right-24: Decisions](../concepts/decisions.md) - How ALLOW, DENY, and ESCALATE work
- [:octicons-arrow-right-24: Troubleshooting](../troubleshooting.md) - Common issues and solutions
