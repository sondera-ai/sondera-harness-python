---
title: Writing Policies
description: Learn Cedar policy syntax and patterns for agent governance
---

# Writing Policies

Policies are written in [Cedar](https://www.cedarpolicy.com/), an open-source language for authorization. This guide covers syntax and patterns. For the concepts behind policy-as-code, see [Policies](concepts/policies.md).

## Getting Started

### Why Policies?

Agents are autonomous but need boundaries. Policies define what actions are allowed or blocked, evaluated at six stages in the agent loop:

| Stage | When | Example |
|:------|:-----|:--------|
| `PRE_RUN` | Before agent starts | Session auth, rate limits |
| `PRE_MODEL` | Before LLM call | Block prompt injection |
| `POST_MODEL` | After LLM response | Filter sensitive output |
| `PRE_TOOL` | Before tool runs | Check arguments, spending limits |
| `POST_TOOL` | After tool runs | Sanitize results, block PII |
| `POST_RUN` | After agent completes | Audit logging |

See [Stages](concepts/stages.md) for details on each stage.

When a policy denies an action, the agent receives feedback and can try a different approach. This is called **steering**.

```text
Agent: "I'll delete the temp files with rm -rf /"
Policy: DENIED - "Destructive command blocked"
Agent: "Let me try a safer approach: rm /tmp/cache/*.tmp"
Policy: ALLOWED
```

Without policies, agents can execute destructive commands, leak secrets, get stuck in loops, or access systems they shouldn't.

---

### Quick Start

#### Hello World

The simplest policy allows everything:

```cedar
permit(principal, action, resource);
```

This is useful for development but not production. Let's add a safety rail:

```cedar
// Allow everything by default
permit(principal, action, resource);

// Block one dangerous pattern
@id("no-rm-rf")
forbid(principal, action, resource)
when { context has parameters_json && context.parameters_json like "*rm -rf*" };
```

!!! tip "How Evaluation Works"
    - If **any** `forbid` policy matches → **DENY**
    - If **any** `permit` policy matches and no `forbid` → **ALLOW**
    - If **no policies** match → **DENY** (default deny)

    Forbid always wins. This means you can start permissive and add restrictions.

#### Starter Policy Set

A minimal starting point:

```cedar
// Allow all actions by default
permit(principal, action, resource);

// Prevent runaway agents
@id("step-limit")
forbid(principal, action, resource)
when { resource has step_count && resource.step_count > 100 };

// Block dangerous commands (add more from Safety Policies section)
@id("no-rm-rf")
forbid(principal, action, resource)
when { context has parameters_json && context.parameters_json like "*rm -rf*" };
```

See [Policy Patterns](#policy-patterns) below for comprehensive safety, security, and compliance policies to add.

---

### Policy Syntax

A Cedar policy has three parts:

```cedar
// Allow an action unconditionally
@id("allow-reads")
permit(principal, action, resource);

// Block an action with a condition
@id("block-dangerous")
forbid(principal, action, resource)
when { context has parameters_json };
```

| Part | Description |
|:-----|:------------|
| `@id` | Optional identifier for the policy (shows in denial reasons) |
| `permit` / `forbid` | Allow or deny the action |
| `principal` | Who is making the request (the agent) |
| `action` | The tool being called (e.g., `My_Agent::Action::"Bash"`) |
| `resource` | The trajectory being acted upon (has `step_count`) |
| `context` | Data about the request: tool arguments (`parameters_json`) and responses (`response_json`) |
| `when` | Conditions that must be true for the policy to match |

#### Action Names

Cedar action names are derived from your tool names:

| Tool Name | Cedar Action |
|:----------|:-------------|
| `Bash` | `My_Agent::Action::"Bash"` |
| `File Write` | `My_Agent::Action::"File_Write"` |
| `send-email` | `My_Agent::Action::"send_email"` |

!!! tip "Name Transformation Rules"
    - Agent name becomes the namespace (e.g., `My_Agent::`)
    - Spaces become underscores: `File Write` → `File_Write`
    - Hyphens become underscores: `send-email` → `send_email`
    - Action names are quoted: `"Bash"`

!!! info "About Example Action Names"
    Policies in this guide use placeholder names like `My_Agent::Action::"Bash"`. Replace `My_Agent` with your agent's name and use your actual tool names. The schema is generated automatically from your agent definition.

#### Context Object

The `context` object contains the tool's arguments and response. There are two ways to access this data:

| Field | When Available | Use Case |
|:------|:---------------|:---------|
| `parameters_json` | Always (PRE_TOOL) | Pattern matching with `like` |
| `parameters` | Only if tool has JSON schema | Typed access, numeric comparisons |
| `response_json` | Always (POST_TOOL) | Pattern matching with `like` |
| `response` | Only if tool has JSON schema | Typed access to response fields |

**Why two versions?** `parameters_json` is always available as a string, so you can use `like "*pattern*"` for simple matching. `parameters` gives you typed fields (for `> 1000` comparisons), but requires defining a JSON schema on your tool.

```text
// String version - always works, use pattern matching
context.parameters_json like "*rm -rf*"

// Typed version - needs JSON schema, enables comparisons
context.parameters.amount > 1000
```

!!! warning "Always Check for Existence"
    Cedar errors if you access a field that doesn't exist.

    **For pattern matching** (always works at PRE_TOOL):
    ```text
    when {
      context has parameters_json &&
      context.parameters_json like "*dangerous*"
    };
    ```

    **For typed access** (requires JSON schema on tool):
    ```text
    when {
      context has parameters &&
      context.parameters has amount &&
      context.parameters.amount > 1000
    };
    ```

!!! info "Custom Context Fields"
    Fields like `context.environment`, `context.user_role`, `context.file_was_read`, or `context.hour` shown in examples below are **not automatically populated**. Your application must track this state and pass these fields when calling `adjudicate()`.

#### Resource Object

The `resource` is the current trajectory (a single agent run from start to finish). It tracks:

```text
resource.step_count  // Total steps taken so far (across all tools)
```

Use `step_count` to limit how long an agent can run, preventing infinite loops or runaway costs. The count increments with each tool call.

---

## Policy Patterns

### Reliability Policies

These policies make agents more predictable and prevent runaway behavior.

#### Limit Total Steps

Stop agents that run too long. `step_count` tracks the total number of steps in the trajectory (across all tools):

```cedar
@id("step-limit")
forbid(principal, action, resource)
when { resource has step_count && resource.step_count > 100 };
```

You can set different limits for different tools. This blocks expensive tools earlier in the trajectory:

```cedar
// Block external API calls after 20 total steps
@id("api-call-limit")
forbid(principal, action == My_Agent::Action::"ExternalAPI", resource)
when { resource has step_count && resource.step_count > 20 };

// Block LLM calls after 10 total steps
@id("llm-tool-limit")
forbid(principal, action == My_Agent::Action::"AskClaude", resource)
when { resource has step_count && resource.step_count > 10 };

// Allow other tools up to 100 steps
@id("general-step-limit")
forbid(principal, action, resource)
when { resource has step_count && resource.step_count > 100 };
```

!!! note "Step Count is Trajectory-Wide"
    `step_count` is the total steps across ALL tools, not per-tool. To track per-tool call counts, your application must maintain that state and pass it via custom context fields.

#### Enforce Workflow Order

Require certain actions before others. These examples use custom context fields that your application must populate:

```cedar
// Must read a file before writing to it (prevents blind overwrites)
// Requires your app to set context.file_was_read = true after reads
@id("read-before-write")
forbid(principal, action == My_Agent::Action::"FileWrite", resource)
when {
  context has parameters &&
  context.parameters has path &&
  !(context has file_was_read && context.file_was_read == true)
};

// Must run tests before committing
// Requires your app to set context.tests_passed = true after test runs
@id("test-before-commit")
forbid(principal, action == My_Agent::Action::"GitCommit", resource)
when {
  !(context has tests_passed && context.tests_passed == true)
};
```

!!! note
    `file_was_read` and `tests_passed` are custom context fields your app must provide. See [Custom Context Fields](#context-object) above.

#### Output Validation

Ensure tool responses meet expectations:

```cedar
// Block empty responses that might indicate failures
@id("no-empty-responses")
forbid(principal, action, resource)
when {
  context has response_json &&
  (context.response_json == "{}" ||
   context.response_json == "null" ||
   context.response_json == "\"\"")
};
```

---

### Safety Policies

These policies prevent agents from causing harm, whether intentional or accidental.

#### Block Dangerous Commands

```cedar
@id("no-destructive-bash")
forbid(principal, action == My_Agent::Action::"Bash", resource)
when {
  context has parameters_json &&
  (context.parameters_json like "*rm -rf /*" ||
   context.parameters_json like "*rm -rf ~*" ||
   context.parameters_json like "*rm -rf .*" ||
   context.parameters_json like "*mkfs*" ||
   context.parameters_json like "*dd if=/dev/zero*" ||
   context.parameters_json like "*dd of=/dev/*" ||
   context.parameters_json like "*> /dev/sda*" ||
   context.parameters_json like "*format c:*")
};
```

#### Block Sensitive Paths

```cedar
@id("no-system-writes")
forbid(principal, action == My_Agent::Action::"FileWrite", resource)
when {
  context has parameters_json &&
  (context.parameters_json like "*\"/etc/*" ||
   context.parameters_json like "*\"/usr/*" ||
   context.parameters_json like "*\"/bin/*" ||
   context.parameters_json like "*\"/sbin/*" ||
   context.parameters_json like "*\"/boot/*")
};

@id("no-ssh-access")
forbid(principal, action, resource)
when {
  context has parameters_json &&
  context.parameters_json like "*/.ssh/*"
};
```

#### Workspace Sandboxing

Only allow file operations within a specific directory. This requires **not** using the blanket `permit(principal, action, resource);` for file operations:

**Option 1: Default-deny approach (no blanket permit for files)**

```cedar
// Allow reads only in workspace
permit(principal, action == My_Agent::Action::"FileRead", resource)
when {
  context has parameters_json &&
  context.parameters_json like "*\"/workspace/*"
};

// Allow writes only in workspace
permit(principal, action == My_Agent::Action::"FileWrite", resource)
when {
  context has parameters_json &&
  context.parameters_json like "*\"/workspace/*"
};

// No blanket permit for file operations - default deny kicks in
// Other tools can have their own permits
permit(principal, action == My_Agent::Action::"Bash", resource);
```

**Option 2: Blanket permit with forbid overrides**

```cedar
// Allow everything by default
permit(principal, action, resource);

// Block file operations outside workspace
@id("workspace-only-reads")
forbid(principal, action == My_Agent::Action::"FileRead", resource)
when {
  context has parameters_json &&
  !(context.parameters_json like "*\"/workspace/*")
};

@id("workspace-only-writes")
forbid(principal, action == My_Agent::Action::"FileWrite", resource)
when {
  context has parameters_json &&
  !(context.parameters_json like "*\"/workspace/*")
};
```

#### Prompt Injection Defense

Block common prompt injection patterns in user inputs:

```cedar
@id("prompt-injection-defense")
forbid(principal, action == My_Agent::Action::"Prompt", resource)
when {
  context has parameters_json &&
  (context.parameters_json like "*ignore previous instructions*" ||
   context.parameters_json like "*ignore all previous*" ||
   context.parameters_json like "*disregard above*" ||
   context.parameters_json like "*forget your instructions*" ||
   context.parameters_json like "*you are now*" ||
   context.parameters_json like "*new persona*" ||
   context.parameters_json like "*jailbreak*" ||
   context.parameters_json like "*DAN mode*")
};
```

#### Block Harmful Outputs

Prevent the agent from generating dangerous content:

```cedar
@id("no-malicious-output")
forbid(principal, action, resource)
when {
  context has response_json &&
  (context.response_json like "*<script>*" ||
   context.response_json like "*javascript:*" ||
   context.response_json like "*onclick=*" ||
   context.response_json like "*onerror=*")
};
```

#### Spending Limits

These examples require `parameters_json_schema` on the TransferMoney tool for typed access:

```cedar
// Hard limit: block transactions over $10,000
@id("transaction-hard-limit")
forbid(principal, action == My_Agent::Action::"TransferMoney", resource)
when {
  context has parameters &&
  context.parameters has amount &&
  context.parameters.amount > 10000
};

// Soft limit: require approval for $1,000-$10,000
// Your app must set context.approved = true after human approval
@id("transaction-approval-required")
forbid(principal, action == My_Agent::Action::"TransferMoney", resource)
when {
  context has parameters &&
  context.parameters has amount &&
  context.parameters.amount > 1000 &&
  context.parameters.amount <= 10000 &&
  !(context has approved && context.approved == true)
};
```

---

### Security Policies

These policies protect secrets, credentials, and system access.

#### Prevent Secret Leakage

Block API keys and credentials from appearing in outputs:

```cedar
@id("no-secrets-in-output")
forbid(principal, action, resource)
when {
  context has response_json &&
  (context.response_json like "*sk-*" ||           // OpenAI API keys
   context.response_json like "*sk_live_*" ||      // Stripe keys
   context.response_json like "*sk_test_*" ||      // Stripe test keys
   context.response_json like "*AKIA*" ||          // AWS access keys
   context.response_json like "*ghp_*" ||          // GitHub personal tokens
   context.response_json like "*gho_*" ||          // GitHub OAuth tokens
   context.response_json like "*glpat-*" ||        // GitLab tokens
   context.response_json like "*xoxb-*" ||         // Slack bot tokens
   context.response_json like "*xoxp-*")           // Slack user tokens
};

@id("no-password-patterns")
forbid(principal, action, resource)
when {
  context has response_json &&
  (context.response_json like "*password=*" ||
   context.response_json like "*password\":*" ||
   context.response_json like "*passwd=*" ||
   context.response_json like "*secret=*" ||
   context.response_json like "*api_key=*" ||
   context.response_json like "*apikey=*")
};
```

#### Block Credential File Access

```cedar
@id("no-credential-files")
forbid(principal, action, resource)
when {
  context has parameters_json &&
  (context.parameters_json like "*/.env*" ||
   context.parameters_json like "*/.netrc*" ||
   context.parameters_json like "*/.aws/credentials*" ||
   context.parameters_json like "*/.config/gcloud*" ||
   context.parameters_json like "*/credentials.json*" ||
   context.parameters_json like "*/secrets.yaml*" ||
   context.parameters_json like "*/secrets.json*" ||
   context.parameters_json like "*/.npmrc*" ||
   context.parameters_json like "*/.pypirc*")
};
```

#### Privilege Escalation Prevention

```cedar
@id("no-privilege-escalation")
forbid(principal, action == My_Agent::Action::"Bash", resource)
when {
  context has parameters_json &&
  (context.parameters_json like "*sudo *" ||
   context.parameters_json like "*sudo\t*" ||
   context.parameters_json like "*su -*" ||
   context.parameters_json like "*su root*" ||
   context.parameters_json like "*chmod 777*" ||
   context.parameters_json like "*chmod +s*" ||
   context.parameters_json like "*chown root*" ||
   context.parameters_json like "*setuid*")
};
```

#### Network Access Control

Restrict which domains the agent can access:

```cedar
// Allow only approved domains (requires parameters_json_schema for typed access)
@id("approved-domains-only")
forbid(principal, action == My_Agent::Action::"HttpRequest", resource)
when {
  context has parameters &&
  context.parameters has url &&
  !(context.parameters.url like "*api.example.com*" ||
    context.parameters.url like "*internal.company.com*" ||
    context.parameters.url like "*github.com*")
};

// Block known dangerous destinations (pattern matching works without schema)
@id("block-dangerous-urls")
forbid(principal, action == My_Agent::Action::"HttpRequest", resource)
when {
  context has parameters_json &&
  (context.parameters_json like "*localhost*" ||
   context.parameters_json like "*127.0.0.1*" ||
   context.parameters_json like "*0.0.0.0*" ||
   context.parameters_json like "*169.254.*" ||      // Link-local
   context.parameters_json like "*metadata.google*")  // Cloud metadata
};
```

#### Database Security

```cedar
// Block all write operations (forbid approach is safer than permit)
@id("read-only-database")
forbid(principal, action == My_Agent::Action::"DatabaseQuery", resource)
when {
  context has parameters_json &&
  (context.parameters_json like "*INSERT *" ||
   context.parameters_json like "*INSERT\t*" ||
   context.parameters_json like "*UPDATE *" ||
   context.parameters_json like "*UPDATE\t*" ||
   context.parameters_json like "*DELETE *" ||
   context.parameters_json like "*DELETE\t*" ||
   context.parameters_json like "*DROP *" ||
   context.parameters_json like "*TRUNCATE *" ||
   context.parameters_json like "*ALTER *" ||
   context.parameters_json like "*CREATE *")
};

// Block SQL injection patterns
@id("no-sql-injection")
forbid(principal, action == My_Agent::Action::"DatabaseQuery", resource)
when {
  context has parameters_json &&
  (context.parameters_json like "*; DROP*" ||
   context.parameters_json like "*; DELETE*" ||
   context.parameters_json like "*' OR '1'='1*" ||
   context.parameters_json like "*\" OR \"1\"=\"1*" ||
   context.parameters_json like "*UNION SELECT*")
};
```

!!! tip "Forbid vs Permit for Security"
    Use `forbid` to block dangerous operations rather than `permit` to allow safe ones. A forbid-based approach is safer because it blocks known-bad patterns, while a permit-based approach might miss edge cases.

---

### Compliance Policies

These policies help meet regulatory and organizational requirements.

#### PII Protection (GDPR/CCPA)

Block personally identifiable information from appearing in outputs:

```cedar
@id("no-pii-in-output")
forbid(principal, action, resource)
when {
  context has response_json &&
  (context.response_json like "*SSN:*" ||
   context.response_json like "*social security*" ||
   context.response_json like "*driver's license*" ||
   context.response_json like "*passport number*" ||
   context.response_json like "*credit card*" ||
   context.response_json like "*bank account*")
};
```

!!! note "Email Detection Limitations"
    Pattern-based email detection (e.g., `*@*.com*`) produces many false positives. For robust PII detection, consider using a dedicated PII scanner before passing data to the harness, then set a context flag like `context.contains_pii`.

#### Human-in-the-Loop

Require human approval for high-risk actions. Your application must set `context.human_approved = true` after receiving approval:

```cedar
// Requires your app to pass context.human_approved (boolean) and context.environment

// Require approval for production changes
@id("production-approval-required")
forbid(principal, action == My_Agent::Action::"Deploy", resource)
when {
  context has environment &&
  context.environment == "production" &&
  !(context has human_approved && context.human_approved == true)
};

// Require approval for customer-facing communications
@id("customer-email-approval")
forbid(principal, action == My_Agent::Action::"SendEmail", resource)
when {
  context has parameters &&
  context.parameters has recipient_type &&
  context.parameters.recipient_type == "customer" &&
  !(context has human_approved && context.human_approved == true)
};

// Require approval for data deletion
@id("deletion-approval")
forbid(principal, action == My_Agent::Action::"DeleteRecord", resource)
when {
  !(context has human_approved && context.human_approved == true)
};
```

#### Role-Based Access

Restrict actions based on user roles. Your application must populate `context.user_role`:

```cedar
// Requires your app to pass context.user_role (string)
@id("admin-only-config")
forbid(principal, action == My_Agent::Action::"UpdateConfig", resource)
when {
  !(context has user_role && context.user_role == "admin")
};

@id("finance-only-transactions")
forbid(principal, action == My_Agent::Action::"TransferMoney", resource)
when {
  !(context has user_role &&
    (context.user_role == "finance" || context.user_role == "admin"))
};
```

---

## Reference

### Operators Reference

#### Comparison Operators

| Operator | Description | Example |
|:---------|:------------|:--------|
| `==` | Equals | `action == Agent::Action::"Bash"` |
| `!=` | Not equals | `context.role != "SYSTEM"` |
| `<` | Less than | `context.parameters.amount < 100` |
| `<=` | Less than or equal | `context.parameters.count <= 10` |
| `>` | Greater than | `context.parameters.amount > 1000` |
| `>=` | Greater than or equal | `resource.step_count >= 50` |

#### String Operators

| Operator | Description | Example |
|:---------|:------------|:--------|
| `like` | Wildcard match | `context.parameters_json like "/tmp/*"` |
| `==` | Exact match | `context.parameters.tool == "Bash"` |

!!! tip "Wildcard Patterns"
    - `*` matches any characters (including none)
    - `"*.txt"` matches `"file.txt"` and `".txt"`
    - `"*rm*"` matches `"rm"`, `"rm -rf"`, and `"perform"` (careful!)
    - Escape literal asterisks with `\*`

#### Logical Operators

| Operator | Description | Example |
|:---------|:------------|:--------|
| `&&` | And | `a > 0 && b > 0` |
| `\|\|` | Or | `a == 1 \|\| a == 2` |
| `!` | Not | `!(context has approved)` |

#### Existence Check

Always check if a field exists before accessing it:

```text
// Check single field
context has parameters_json

// Check nested field
context has parameters && context.parameters has amount
```

---

### Testing Policies

Test policies without running your full agent. The SDK includes a complete example:

```bash
# Clone the repo and run the example
git clone https://github.com/sondera-ai/sondera-harness-python.git
cd sondera-harness-python
uv run python examples/cedar/coding_agent.py
```

The example tests multiple scenarios:

- **Allow:** Reading files, glob searches, safe bash commands
- **Deny:** Writing to `.env` files, editing SSH keys, dangerous bash commands, fetching from untrusted URLs

See [`examples/cedar/coding_agent.py`](https://github.com/sondera-ai/sondera-harness-python/blob/main/examples/cedar/coding_agent.py) for the full source.

### Testing Policy Changes Against Historical Trajectories

When updating policies, validate that new rules don't allow previously-denied actions. This pattern replays historical trajectories against your new policy set:

```python
from sondera import CedarPolicyHarness, SonderaRemoteHarness, Decision
from sondera.harness.cedar.schema import agent_to_cedar_schema

async def test_policy_change_is_safe(agent, new_policies):
    """Ensure new policy doesn't allow previously-denied actions."""
    platform = SonderaRemoteHarness()
    local = CedarPolicyHarness(policy_set=new_policies, schema=agent_to_cedar_schema(agent))

    for traj_summary in await platform.list_trajectories(agent_id=agent.id):
        traj = await platform.get_trajectory(traj_summary.id)
        if traj is None:
            continue

        await local.initialize(agent=agent)
        for adj_step in traj.steps:
            new_result = await local.adjudicate(
                adj_step.step.stage, adj_step.step.role, adj_step.step.content
            )
            # If old policy denied, new policy must also deny
            if adj_step.adjudication.decision == Decision.DENY:
                assert new_result.decision == Decision.DENY, (
                    f"Regression: {adj_step.step.stage.value} was denied, now allowed"
                )
        await local.finalize()
```

This approach catches policy regressions before they reach production.

---

## More Resources

- [**Cedar Playground**](https://www.cedarpolicy.com/en/playground): Try policies interactively
- [**Cedar Documentation**](https://docs.cedarpolicy.com/): Full language reference
- [**Example Policies**](https://github.com/sondera-ai/sondera-harness-python/tree/main/examples): Real-world patterns
