# Cedar Policy Harness Example

Demonstrates local policy enforcement using `CedarPolicyHarness` with the Cedar policy language.

## Overview

This example shows how to use the Cedar policy-as-code engine for agent governance without requiring a remote Harness Service. It implements a coding agent with comprehensive policy rules that:

- **Allow safe operations**: File reading, code searching (Glob/Grep), web searches
- **Forbid dangerous file operations**: Writing to `.env`, `.git/`, credentials, secrets; editing SSH keys, PEM files
- **Forbid dangerous bash commands**: `rm -rf /`, `mkfs`, disk operations
- **Forbid untrusted web fetches**: Pastebin, raw GitHub URLs
- **Rate limiting**: Blocks operations after 1000 trajectory steps

## Installation

```bash
uv sync
```

## Running the Example

```bash
# Run the coding agent with Cedar policy enforcement
uv run python coding_agent.py
```

The script will:
1. Generate a Cedar schema from the agent definition
2. Load Cedar policies from the inline policy set
3. Run a series of adjudication tests demonstrating ALLOW/DENY decisions
4. Export the schema and policies to `coding.cedarschema` and `coding.cedar` files

## Policy Examples

The Cedar policies use a permit-by-default, forbid-for-dangerous pattern:

```cedar
// Allow read operations - reading is generally safe
@id("allow-read")
permit(principal, action == Coding_Agent::Action::"Read", resource);

// Forbid writing to sensitive configuration files
@id("forbid-sensitive-write")
forbid(
  principal,
  action == Coding_Agent::Action::"Write",
  resource
)
when {
  context has parameters &&
  (context.parameters.file_path like "*.env*" ||
   context.parameters.file_path like "*.git/*")
};
```

## Use Cases

- **Local testing**: Test policies without deploying to Harness Service
- **Offline governance**: Run agents with policy enforcement in air-gapped environments
- **Policy development**: Rapidly iterate on Cedar policies before production deployment
- **CI/CD validation**: Integrate policy checks into automated testing pipelines
