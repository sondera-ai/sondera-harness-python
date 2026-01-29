---
title: Troubleshooting
description: Common issues and solutions for Sondera Harness
---

# Troubleshooting

Common issues and solutions.

---

## Why was my action denied?

Every `Adjudication` includes a `reason` field explaining which policy triggered the denial:

```{.python notest}
result = await harness.adjudicate(stage, role, content)
if result.is_denied:
    print(result.reason)
    # e.g., "forbid-dangerous-bash: command matches forbidden pattern"
```

Use the TUI to see decisions in real-time with full context:

```bash
uv run sondera   # or just `sondera` if installed globally via pip
```

!!! note "Platform only"
    The TUI requires [Sondera Platform](https://sondera.ai) (`SonderaRemoteHarness`). The local `CedarPolicyHarness` doesn't persist trajectory data.

---

## My policy isn't being evaluated

### Check: Action name mismatch

Cedar actions are derived from tool names. Spaces and hyphens become underscores:

| Tool Name | Cedar Action |
|:----------|:-------------|
| `File Write` | `My_Agent::Action::"File_Write"` |
| `send-email` | `My_Agent::Action::"send_email"` |

**Fix:** Ensure your policy action name matches the transformed tool name.

### Check: Stage mismatch

A `PRE_TOOL` policy won't fire on `POST_MODEL` adjudications.

**Fix:** Verify your policy targets the stage where you're calling `adjudicate()`.

### Check: Missing context existence check

If your policy uses `context.parameters.X`, Cedar errors if the field doesn't exist.

**Fix:** Always include existence checks:

```cedar
forbid(principal, action, resource)
when {
  context has parameters &&
  context.parameters has command &&
  context.parameters.command like "*dangerous*"
};
```

---

## How do I debug my Cedar policies?

**1. Validate syntax before loading:**

```{.python notest}
from sondera.harness.cedar import validate_policy

errors = validate_policy(my_policy_string)
if errors:
    print("Policy errors:", errors)
```

**2. Use the TUI** to step through adjudications and see which policies matched:

```bash
uv run sondera   # or just `sondera` if installed globally via pip
```

<figure markdown="span">
  ![Sondera TUI](assets/sondera-tui.gif){ width="600" }
</figure>

!!! note "Platform only"
    The TUI requires `SonderaRemoteHarness`. It won't show data from `CedarPolicyHarness` since the local harness doesn't persist trajectories.

**3. Check your schema** matches your agent's tools. Mismatched action names silently skip policies.

**4. Test in isolation** with unit tests:

```{.python notest}
@pytest.mark.asyncio
async def test_my_policy():
    harness = CedarPolicyHarness(policy_set=policy, schema=schema)
    await harness.initialize(agent=agent)

    result = await harness.adjudicate(
        Stage.PRE_TOOL, Role.MODEL,
        ToolRequestContent(tool_id="Bash", args={"command": "rm -rf /"})
    )

    assert result.is_denied
    print(f"Reason: {result.reason}")
```

---

## Connection issues with Sondera Platform

**Common errors:**

- `Connection refused` — Endpoint unreachable
- `SSL certificate problem` — TLS configuration issue
- `Unauthorized` — Invalid or expired API token

**Debug steps:**

```bash
# 1. Verify endpoint is reachable
curl -v https://harness.sondera.ai:443

# 2. Check environment variables
echo $SONDERA_HARNESS_ENDPOINT
echo $SONDERA_API_TOKEN

# 3. Test with verbose logging
export GRPC_VERBOSITY=DEBUG
python your_script.py
```

**Corporate proxies:** If behind a proxy, ensure gRPC traffic is allowed on port 443:

```bash
export HTTPS_PROXY=http://proxy.company.com:8080
```

---

## Testing policies without running the full agent

Use the harness directly in a test:

```python
import pytest
from sondera import CedarPolicyHarness, Agent, Tool, ToolRequestContent, Stage, Role
from sondera.harness.cedar.schema import agent_to_cedar_schema

@pytest.fixture
async def harness():
    agent = Agent(
        id="test",
        provider_id="test",
        name="Test Agent",
        tools=[Tool(name="Bash", description="Shell commands")],
    )
    policy = '''
    @id("no-rm-rf")
    forbid(principal, action == Test_Agent::Action::"Bash", resource)
    when { context.parameters.command like "*rm -rf*" };
    '''
    h = CedarPolicyHarness(policy_set=policy, schema=agent_to_cedar_schema(agent))
    await h.initialize(agent=agent)
    return h

@pytest.mark.asyncio
async def test_blocks_rm_rf(harness):
    result = await harness.adjudicate(
        Stage.PRE_TOOL, Role.MODEL,
        ToolRequestContent(tool_id="Bash", args={"command": "rm -rf /"})
    )
    assert result.is_denied

@pytest.mark.asyncio
async def test_allows_safe_commands(harness):
    result = await harness.adjudicate(
        Stage.PRE_TOOL, Role.MODEL,
        ToolRequestContent(tool_id="Bash", args={"command": "ls -la"})
    )
    assert result.is_allowed
```

Run with:

```bash
uv run pytest test_policies.py -v
```

---

## LangGraph: Middleware not firing

**Check middleware is in the list:**

```{.python notest}
agent = create_agent(
    model=my_model,
    tools=my_tools,
    middleware=[middleware],  # Must be included
)
```

**Check agent initialization:**

```{.python notest}
await harness.initialize(agent=sondera_agent)
```

---

## Google ADK: Plugin callbacks not called

**Check plugin is registered with Runner:**

```{.python notest}
runner = Runner(
    agent=agent,
    app_name="my-app",
    plugins=[plugin],  # Must be included
)
```

---

## Strands: Hook not intercepting

**Check hook is passed to Agent:**

```{.python notest}
agent = Agent(
    system_prompt="...",
    model="...",
    hooks=[hook],  # Must be included
)
```

**AWS credentials not working?** Strands uses Amazon Bedrock by default. Ensure your AWS credentials are configured:

```bash
export AWS_REGION=us-east-1
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
```

---

## Error Handling

Sondera raises specific exceptions you can catch and handle gracefully.

### Exception Hierarchy

```
SonderaError (base)
├── ConfigurationError      # Missing config (API key, endpoint)
├── AuthenticationError     # Invalid or expired token
├── TrajectoryError         # Trajectory not found
│   └── TrajectoryNotInitializedError  # adjudicate() before initialize()
├── PolicyError
│   ├── PolicyViolationError  # Policy denied an action
│   └── PolicyEvaluationError # Policy syntax/evaluation failure
├── AgentError              # Agent registration/lookup failed
└── ToolError
    └── ToolBlockedError    # Tool blocked by policy (BLOCK strategy)
```

### Catching Specific Exceptions

```{.python notest}
from sondera import CedarPolicyHarness
from sondera.exceptions import (
    SonderaError,
    ConfigurationError,
    AuthenticationError,
    TrajectoryNotInitializedError,
    PolicyViolationError,
    PolicyEvaluationError,
    ToolBlockedError,
)

try:
    result = await harness.adjudicate(stage, role, content)
except TrajectoryNotInitializedError:
    # Forgot to call initialize() first
    await harness.initialize(agent=agent)
    result = await harness.adjudicate(stage, role, content)
except PolicyEvaluationError as e:
    # Policy has syntax error or references unknown fields
    logger.error(f"Policy error: {e}")
    # Fail open or closed based on your requirements
    raise
except SonderaError as e:
    # Catch-all for other Sondera errors
    logger.error(f"Sondera error: {e}")
    raise
```

### Exception Attributes

Some exceptions include useful attributes:

```{.python notest}
try:
    result = await harness.adjudicate(stage, role, content)
except PolicyViolationError as e:
    print(e.stage)        # Stage where violation occurred
    print(e.reason)       # Why the policy denied
    print(e.adjudication) # Full Adjudication object

try:
    await execute_tool(tool_call)
except ToolBlockedError as e:
    print(e.tool_name)    # Which tool was blocked
    print(e.tool_args)    # Arguments that were blocked
```

### Remote Harness Errors

When using `SonderaRemoteHarness`, handle connection issues:

```{.python notest}
from sondera import SonderaRemoteHarness
from sondera.exceptions import AuthenticationError, ConfigurationError

try:
    harness = SonderaRemoteHarness(
        sondera_api_key=os.getenv("SONDERA_API_KEY"),
    )
    await harness.initialize(agent=agent)
except ConfigurationError:
    # Missing API key or endpoint
    logger.error("SONDERA_API_KEY not set")
    raise
except AuthenticationError:
    # Invalid or expired token
    logger.error("Invalid API key")
    raise
except Exception as e:
    # Connection failures, network issues
    logger.error(f"Connection failed: {e}")
    raise
```

### Graceful Degradation

For non-critical applications, you might want to continue without policy enforcement if the harness fails:

```python
async def safe_adjudicate(harness, stage, role, content):
    """Adjudicate with graceful fallback."""
    try:
        return await harness.adjudicate(stage, role, content)
    except PolicyEvaluationError as e:
        # Log but allow (fail open)
        logger.warning(f"Policy evaluation failed: {e}")
        return Adjudication(decision=Decision.ALLOW, reason="Policy evaluation failed")
    except TrajectoryNotInitializedError:
        # Initialize and retry
        await harness.initialize(agent=agent)
        return await harness.adjudicate(stage, role, content)
```

!!! warning "Fail Open vs Fail Closed"
    The example above fails open (allows on error). For security-critical applications, fail closed instead:

    ```python
    except PolicyEvaluationError as e:
        logger.error(f"Policy evaluation failed: {e}")
        return Adjudication(decision=Decision.DENY, reason="Policy evaluation failed")
    ```

---

## Getting Help

- **Discord** — Ask questions, share what you're building: [discord.gg/8zMbcnDnZs](https://discord.gg/8zMbcnDnZs)
- **GitHub Issues** — Bug reports and feature requests: [github.com/sondera-ai/sondera-harness-python/issues](https://github.com/sondera-ai/sondera-harness-python/issues)
- **Cedar Docs** — Deep dive into the policy language: [cedarpolicy.com](https://docs.cedarpolicy.com/)
