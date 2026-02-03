---
title: Policies
description: Define agent behavior with code, not prompts
---

# Policies

Policies are rules that define what your agent can and can't do. Instead of embedding guardrails in prompts or hardcoding logic in your agent scaffold, you write policies in a dedicated language and enforce them from outside the agent. This is **policy-as-code**, and it's how you get reliable, auditable control over agent behavior.

---

## Why Policy-as-Code?

Prompt-based guardrails are fragile. They can be bypassed by prompt injection, ignored by the model, or forgotten when you update the system prompt. Hardcoded rules are tedious: every agent needs different logic, and updates mean changing code everywhere.

Policies solve both problems:

| Approach | Problem | Policy-as-code solution |
|:---------|:--------|:------------------------|
| **Prompts** | Can be bypassed or ignored | Policies enforce from outside the agent |
| **Hardcoded rules** | Tedious, per-agent, scattered | Policies are centralized and reusable |
| **Ad-hoc checks** | Inconsistent, hard to audit | Policies are versioned and auditable |

With policies, you define rules once and apply them across all your agents. Updates happen in one place. And because the harness enforces policies from outside the scaffold, they can't be bypassed by the agent itself.

---

## Cedar: The Policy Language

Sondera uses [Cedar](https://www.cedarpolicy.com/), an open-source policy language created by AWS. Cedar is designed for authorization logic: it's fast, auditable, and expressive enough to handle complex rules without becoming unreadable.

For complete syntax reference, operators, and testing patterns, see [Writing Policies](../writing-policies.md).

A Cedar policy has three parts:

```cedar
@id("policy-name")
permit(principal, action, resource)
when { context has parameters_json };
```

- **Effect**: `permit` (allow) or `forbid` (deny)
- **Scope**: Who (`principal`), what (`action`), on what (`resource`)
- **Conditions**: Optional `when` clause for fine-grained control

In the agent context:

| Term | What it means |
|:-----|:--------------|
| `principal` | Your agent (the entity making requests) |
| `action` | A list of operations (e.g., `Read`, `Prompt`, `Transfer`) |
| `resource` | The trajectory or message being evaluated |

Here's a real example:

```cedar
@id("block-dangerous-commands")
forbid(principal, action == MyAgent::Action::"Bash", resource)
when {
  context has parameters_json &&  // parameters_json is always available as a JSON string
  (context.parameters_json like "*rm -rf*" ||
   context.parameters_json like "*sudo*")
};
```

This policy blocks any Bash command containing `rm -rf` or `sudo`. The harness evaluates it at the PRE_TOOL stage, before the command executes.

---

## How Policies Become Decisions

When you call `harness.adjudicate()`, Cedar evaluates your policies and returns a [decision](decisions.md): ALLOW, DENY, or ESCALATE.

Cedar evaluates in this order:

1. **Check forbid policies**: If any `forbid` matches, then **DENY** (or **ESCALATE** if all matching forbids have `@escalate`)
2. **Check permit policies**: If any `permit` matches, then **ALLOW**
3. **Default**: If no policies match, then **DENY**

This is a **default-deny** model. Actions are blocked unless explicitly permitted. It's safer: a missing policy means "don't allow" rather than "allow everything."

```cedar
// Even though this permits everything...
permit(principal, action, resource);

// ...this forbid still blocks DeleteFiles (forbid takes precedence)
forbid(principal, action == MyAgent::Action::"DeleteFiles", resource);
```

When a policy denies an action, you choose how to handle it: **block** the agent entirely, or **steer** it by returning the reason so it can try a different approach. For actions that need approval rather than outright denial, use the `@escalate` annotation to trigger an **escalate** decision. See [Decisions](decisions.md) for details.

---

## What Policies Can Access

Policies evaluate against a `context` object that contains information about the current request. What's available depends on the [stage](stages.md):

| Stage | What you can check | Example |
|:------|:-------------------|:--------|
| `PRE_MODEL` / `POST_MODEL` | Text content, role | `resource.content like "*ignore instructions*"` |
| `PRE_TOOL` | Tool arguments | `context.parameters_json like "*command*"` |
| `POST_TOOL` | Tool results | `context.response_json like "*secret*"` |

!!! warning "Always use `has` checks"

    Cedar produces an error if you access a field that doesn't exist. Always check before accessing. For example:
    
    ```cedar
    forbid(principal, action, resource)
    when {
      context has parameters &&
      context.parameters has command &&
      context.parameters.command like "*dangerous*"
    };
    ```

You can also access trajectory state to write policies based on what the agent has already done:

```cedar
@id("limit-tool-calls")
forbid(principal, action, resource)
when { resource.step_count > 50 };
```

For complete stage-by-stage examples, see [Stages](stages.md).

---

## Policy Patterns

### Allow by default, block specific actions

```cedar
// Allow everything
permit(principal, action, resource);

// Except these dangerous tools
forbid(principal, action == MyAgent::Action::"DeleteDatabase", resource);
forbid(principal, action == MyAgent::Action::"SendEmail", resource);
```

### Block by default, allow specific actions

```cedar
// Only allow these tools
permit(principal, action == MyAgent::Action::"Search", resource);
permit(principal, action == MyAgent::Action::"Read", resource);

// Everything else is denied by default (no permit matches)
```

### Conditional rules

```cedar
@id("spending-limit")
forbid(principal, action == MyAgent::Action::"Transfer", resource)
when {
  context has parameters &&
  context.parameters has amount &&
  context.parameters.amount > 10000
};

@id("block-sensitive-paths")
forbid(principal, action == MyAgent::Action::"FileWrite", resource)
when {
  context has parameters &&
  context.parameters has path &&
  context.parameters.path like "/etc/*"
};
```

---

## Annotations

Policies must include an `@id` annotation to identify them in adjudication results. This makes it easy to see which policy allowed or denied an action.

```cedar
@id("high-value-transfer-block")
forbid(principal, action == MyAgent::Action::"Transfer", resource)
when {
  context has parameters &&
  context.parameters has amount &&
  context.parameters.amount > 100000
};
```

When a policy matches, its metadata is included in `result.policies`. See [Decisions](decisions.md#accessing-policy-metadata-from-cedar-annotations) for how to access policy metadata in your code.

---

## Local vs Platform

Policies can be defined locally in your code (`CedarPolicyHarness`) or managed centrally in Sondera Platform (`SonderaRemoteHarness`). Both use the same policy language and API.

[:octicons-arrow-right-24: Compare deployment options](../deployment.md)

---

## Next Steps

- [**Stages**](stages.md): Where policies are evaluated in the agent loop
- [**Trajectories**](trajectories.md): How policy decisions are recorded
- [**Writing Policies**](../writing-policies.md): Complete guide to Cedar syntax and patterns
