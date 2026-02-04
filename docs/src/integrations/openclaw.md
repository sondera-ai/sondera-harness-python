---
title: OpenClaw Integration
description: Add Sondera guardrails to OpenClaw AI agents
---

# OpenClaw Integration

<img src="https://mintcdn.com/clawdhub/-t5HSeZ3Y_0_wH4i/assets/openclaw-logo-text-dark.png?w=2500&fit=max&auto=format&n=-t5HSeZ3Y_0_wH4i&q=85&s=e7b1ad00141bc8497bee7df9e46ccebd" alt="OpenClaw" width="200" class="only-light">
<img src="https://mintcdn.com/clawdhub/FaXdIfo7gPK_jSWb/assets/openclaw-logo-text.png?w=2500&fit=max&auto=format&n=FaXdIfo7gPK_jSWb&q=85&s=23160e4a3cd4676702869ea051fd3f6e" alt="OpenClaw" width="200" class="only-dark">

AI agents can delete files, leak credentials, or run dangerous commands. Prompting them to "be careful" isn't enough. Prompts are suggestions, not guarantees.

Sondera adds a **deterministic safety layer** that checks every tool call against security rules *before* it executes. Unlike probabilistic safeguards, these rules always enforce. Built on [Cedar](https://www.cedarpolicy.com/), a policy language from AWS.

**Why this matters:** As agents become more autonomous, the stakes get higher. You can't scale human oversight to every tool call. Deterministic guardrails give you governance without constant supervision. Predictable boundaries hold regardless of what the agent is asked to do.

This integration runs locally with no external API calls required.

!!! warning "Proof of Concept"
    This integration is experimental and not officially supported. It may silently fail to block dangerous actions. Do not use with real data. Use at your own risk.

---

## Requirements

**OpenClaw 2026.2.0 or later** with plugin hook support.

If the extension installs but doesn't block anything, your OpenClaw version may not have the required hooks yet. Check for updates or [join the OpenClaw Discord](https://discord.gg/clawd) for the latest compatibility info.

---

## Installation

!!! warning "Pre-Release: Use Sondera Fork"
    The OpenClaw plugin hooks are not fully wired in the current release. We've submitted [PR #8448](https://github.com/openclaw/openclaw/pull/8448) to upstream these changes. Until it's merged, install from the Sondera fork using the instructions below. We recommend testing in the [Trail of Bits devcontainer](https://github.com/trailofbits/claude-code-devcontainer) for sandboxed environments.

```bash
# Clone the Sondera fork
git clone https://github.com/sondera-ai/openclaw.git
cd openclaw
git checkout sondera-pr

# Install and build
npm install -g pnpm
pnpm install
pnpm ui:build
pnpm build
pnpm openclaw onboard --install-daemon

# Start the gateway
pnpm openclaw gateway
# Dashboard: http://localhost:18789

# Dev container users (e.g. Trail of Bits devcontainer):
# Add to .devcontainer/devcontainer.json:
#   "forwardPorts": [18789],
#   "appPort": [18789]
# Then rebuild. Before pnpm install, run:
#   pnpm config set store-dir ~/.pnpm-store
# To start the gateway, use:
#   pnpm openclaw gateway --bind lan
```

**Standard Installation (after hooks are merged):**

```bash
openclaw plugins install @openclaw/sondera
```

The extension enables automatically with 41 default security rules.

---

## Verify It's Working

!!! tip "Restart your gateway"
    After installing the extension, restart your OpenClaw gateway to load the new policies. Use the OpenClaw app menu or run `openclaw gateway restart`.

Ask your agent to run a blocked command:

```bash
sudo whoami
```

You should see: `Blocked by Sondera policy. (sondera-block-sudo)`

<img src="/assets/images/openclaw-chat-light.png" alt="Sondera blocking sudo command in OpenClaw" class="only-light" style="border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
<img src="/assets/images/openclaw-chat-dark.png" alt="Sondera blocking sudo command in OpenClaw" class="only-dark" style="border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3);">

---

## How It Works

The extension hooks into OpenClaw at two stages:

| OpenClaw Hook | Stage | What It Checks |
|:--------------|:------|:---------------|
| `before_tool_call` | `PRE_TOOL` | Tool arguments before execution |
| `tool_result_persist` | `POST_TOOL` | Tool output before transcript storage |

**PRE_TOOL** evaluates policies before a tool executes. If denied, the tool is blocked and the agent sees the policy name:

```
Agent calls: rm -rf /tmp/cache
Sondera: DENY (sondera-block-rm)
Agent sees: "Blocked by Sondera policy. (sondera-block-rm)"
```

**What happens when blocked?** The agent sees the block message and stops that action. It won't automatically retry or find a workaround. You'll see exactly what was prevented and can decide how to proceed. This is intentional: guardrails stop dangerous actions, they don't make decisions for you.

**POST_TOOL** redacts sensitive content from session transcripts:

```
Tool returns: GITHUB_TOKEN=ghp_xxxxxxxxxxxx
Sondera: REDACT (sondera-redact-github-tokens)
Transcript shows: [REDACTED BY SONDERA POLICY]
```

!!! note "POST_TOOL limitation"
    Redaction only cleans what gets saved to transcripts. The agent and user still see secrets on screen during the session. PRE_TOOL blocking (preventing the read in the first place) is the stronger protection.

[:octicons-arrow-right-24: See the full stage diagram](../concepts/stages.md)

---

## Policy Packs

The extension ships with **103 rules** across three policy packs:

| Pack | Rules | Default | Description |
|:-----|:------|:--------|:------------|
| **Sondera Base** | 41 | Enabled | Blocks dangerous commands, protects credentials, redacts secrets |
| **OpenClaw System** | 24 | Opt-in | Protects workspace files (SOUL.md, etc.), sessions, config |
| **OWASP Agentic** | 38 | Opt-in | Based on [OWASP Top 10 for Agentic AI](https://genai.owasp.org). Supply chain, persistence, memory poisoning |

### Enable Additional Packs

```bash
# Protect OpenClaw workspace files
openclaw config set plugins.entries.sondera.config.a2_openclawSystemPack true

# Add OWASP Agentic rules (more restrictive)
openclaw config set plugins.entries.sondera.config.a3_owaspAgenticPack true
```

---

## What Gets Blocked

### Dangerous Commands

- `rm`, `rm -rf`: File deletion
- `sudo`, `su`: Privilege escalation
- `curl | bash`, `wget | sh`: Remote code execution
- `nc -e`, `netcat`: Reverse shells
- `chmod 777`, `mkfs`, `dd`: System damage

### Credential Access

- `.ssh/id_*`: SSH private keys
- `.env`, `.env.*`: Environment files
- `.aws/`, `.gcloud/`: Cloud credentials
- `.npmrc`, `.pypirc`: Package manager tokens
- Shell history files

### Data Exfiltration

- `curl --data @file`: Upload via curl
- External POST requests
- Pastebin URLs

### Output Redaction

API keys, tokens, and secrets are redacted from session transcripts:

- GitHub tokens (`ghp_*`, `gho_*`)
- AWS credentials (`AKIA*`)
- Anthropic keys (`sk-ant-*`)
- OpenAI keys (`sk-proj-*`)
- Database connection strings
- Private keys (PEM format)

---

## Configuration

Configure via the OpenClaw Settings UI or CLI:

<img src="/assets/images/openclaw-config-light.png" alt="Sondera configuration in OpenClaw Settings" class="only-light" style="border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
<img src="/assets/images/openclaw-config-dark.png" alt="Sondera configuration in OpenClaw Settings" class="only-dark" style="border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3);">

| Option | Default | Description |
|:-------|:--------|:------------|
| `a_policyPack` | `true` | Sondera Base Pack (41 rules) |
| `a2_openclawSystemPack` | `false` | OpenClaw System Pack (24 rules) |
| `a3_owaspAgenticPack` | `false` | OWASP Agentic Pack (38 rules) |
| `b_lockdown` | `false` | Block ALL tools unless explicitly permitted |
| `c_customRules` | `""` | Your own Cedar rules |
| `d_policyPath` | `""` | Use only this policy file (expert mode) |

### Lockdown Mode

Block everything by default, then permit only what you need. This is the most secure pattern for high-risk environments.

**Step 1: Enable lockdown mode**

```bash
openclaw config set plugins.entries.sondera.config.b_lockdown true
```

**Step 2: Add permit rules for allowed actions**

With lockdown enabled, all tools are blocked unless you explicitly permit them. Add permit rules via the Settings UI or `c_customRules`:

```cedar
// Allow reading any file (but not writing)
@id("permit-read-all")
permit(principal, action, resource)
when {
  action == Sondera::Action::"read"
};

// Allow only git and npm commands
@id("permit-git-npm")
permit(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "git *" ||
   context.params.command like "npm *")
};

// Allow writing only to src/ directory
@id("permit-write-src")
permit(principal, action, resource)
when {
  action == Sondera::Action::"write" &&
  context has params && context.params has path &&
  context.params.path like "*/src/*"
};
```

!!! tip "Start permissive, tighten gradually"
    If lockdown mode is too restrictive, start with the default policy pack and add `forbid` rules for specific things you want to block.

---

## Custom Rules

Add custom Cedar rules via the Settings UI or inline in config.

Rules use two keywords:

- `forbid(...)` blocks actions that match
- `permit(...)` allows actions that match (useful with Lockdown Mode)

!!! info "Rule precedence"
    If both `forbid` and `permit` match the same action, `forbid` wins. Deny always takes precedence.

**Example: Block a specific command**

```cedar
@id("block-docker-run")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  context.params.command like "*docker run*"
};
```

**Example: Block reading a specific directory**

```cedar
@id("block-read-secrets")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read" &&
  context has params && context.params has path &&
  context.params.path like "*/my-secrets/*"
};
```

**Example: Allow only git commands (with Lockdown Mode)**

```cedar
@id("allow-git-commands")
permit(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  context.params.command like "git *"
};
```

### Available Actions

| Action | Triggered By |
|:-------|:-------------|
| `Sondera::Action::"exec"` | Bash/shell commands |
| `Sondera::Action::"read"` | File reads |
| `Sondera::Action::"write"` | File writes |
| `Sondera::Action::"edit"` | File edits |
| `Sondera::Action::"glob"` | File pattern search |
| `Sondera::Action::"grep"` | Content search |

### Context Variables

- `context.params.command`: The shell command (for exec)
- `context.params.path`: The file path (for read/write/edit)
- `context.params.pattern`: The glob pattern (for glob)
- `context.params.url`: The URL (for web fetch)

[:octicons-arrow-right-24: Full Cedar syntax guide](../writing-policies.md)

---

## Disable

```bash
# Disable the extension
openclaw plugins disable sondera

# Re-enable
openclaw plugins enable sondera
```

---

## Policy Packs Reference

See the complete Cedar code for all 103 rules across the three policy packs.

[:octicons-arrow-right-24: View Cedar Policy Reference](openclaw-policies.md)

---

## Learn More

- [:octicons-arrow-right-24: Cedar Policy Language](https://www.cedarpolicy.com/) - Official Cedar syntax reference
- [:octicons-arrow-right-24: OWASP Agentic Top 10](https://genai.owasp.org) - Security framework behind the OWASP pack
- [:octicons-arrow-right-24: Writing Policies](../writing-policies.md) - Cedar syntax and common patterns
- [:octicons-arrow-right-24: Decisions](../concepts/decisions.md) - How ALLOW and DENY work
- [:octicons-arrow-right-24: Core Concepts](../concepts/index.md) - Understand the harness architecture

**Want guardrails for other agents?** Sondera works with multiple agent frameworks:

- [:octicons-arrow-right-24: LangGraph Integration](langgraph.md) - Add guardrails to LangGraph agents
- [:octicons-arrow-right-24: Google ADK Integration](adk.md) - Add guardrails to Google ADK agents
- [:octicons-arrow-right-24: Strands Integration](strands.md) - Add guardrails to Strands agents
- [:octicons-arrow-right-24: Custom Agents](custom.md) - Build guardrails for any agent framework

---

## Community

Questions or feedback? Join the conversation:

- [:octicons-comment-discussion-24: OpenClaw Discord](https://discord.gg/clawd) - Ask questions and get support
- [:octicons-mark-github-24: OpenClaw GitHub Issues](https://github.com/openclaw/openclaw/issues) - Report bugs or request features
