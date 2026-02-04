---
title: OpenClaw Policy Reference
description: Complete Cedar policy reference for Sondera guardrails - 103 security rules for AI agents
---

# OpenClaw Policy Reference

<img src="https://mintcdn.com/clawdhub/-t5HSeZ3Y_0_wH4i/assets/openclaw-logo-text-dark.png?w=2500&fit=max&auto=format&n=-t5HSeZ3Y_0_wH4i&q=85&s=e7b1ad00141bc8497bee7df9e46ccebd" alt="OpenClaw" width="200" class="only-light">
<img src="https://mintcdn.com/clawdhub/FaXdIfo7gPK_jSWb/assets/openclaw-logo-text.png?w=2500&fit=max&auto=format&n=FaXdIfo7gPK_jSWb&q=85&s=23160e4a3cd4676702869ea051fd3f6e" alt="OpenClaw" width="200" class="only-dark">

Complete reference for all 103 Cedar security rules included with the Sondera extension for OpenClaw. Use these as examples for writing your own custom rules.

[:octicons-arrow-left-24: Back to OpenClaw Integration](openclaw.md)

---

## Sondera Base Pack (41 rules)

The default policy pack enabled on installation. Blocks dangerous commands, protects credentials, and redacts secrets from output.

### Dangerous Commands

```cedar title="sondera-block-rm"
@id("sondera-block-rm")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  context.params.command like "*rm *"
};
```

```cedar title="sondera-block-rf-flags"
@id("sondera-block-rf-flags")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (
    context.params.command like "*-rf*" ||
    context.params.command like "*-fr*"
  )
};
```

```cedar title="sondera-block-sudo"
@id("sondera-block-sudo")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  context.params.command like "*sudo *"
};
```

```cedar title="sondera-block-su"
@id("sondera-block-su")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  context.params.command like "*su *"
};
```

```cedar title="sondera-block-chmod-777"
@id("sondera-block-chmod-777")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  context.params.command like "*chmod 777*"
};
```

```cedar title="sondera-block-disk-operations"
@id("sondera-block-disk-operations")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*mkfs*" ||
   context.params.command like "*dd if=*" ||
   context.params.command like "*>/dev/sd*" ||
   context.params.command like "*>/dev/nvme*")
};
```

```cedar title="sondera-block-kill-system"
@id("sondera-block-kill-system")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*kill -9 1*" ||
   context.params.command like "*pkill -9 init*" ||
   context.params.command like "*killall*")
};
```

```cedar title="sondera-block-shutdown"
@id("sondera-block-shutdown")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*shutdown*" ||
   context.params.command like "*reboot*" ||
   context.params.command like "*poweroff*" ||
   context.params.command like "*init 0*")
};
```

### Remote Code Prevention

```cedar title="sondera-block-curl-shell"
@id("sondera-block-curl-shell")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*curl*|*sh*" ||
   context.params.command like "*curl*|*bash*" ||
   context.params.command like "*wget*|*sh*" ||
   context.params.command like "*wget*|*bash*" ||
   context.params.command like "*curl*-o*&&*sh*" ||
   context.params.command like "*curl*-o*&&*bash*")
};
```

```cedar title="sondera-block-base64-shell"
@id("sondera-block-base64-shell")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*base64*-d*|*sh*" ||
   context.params.command like "*base64*-d*|*bash*" ||
   context.params.command like "*base64*--decode*|*sh*")
};
```

```cedar title="sondera-block-netcat"
@id("sondera-block-netcat")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*nc *-e*" ||
   context.params.command like "*nc *-c*" ||
   context.params.command like "*netcat*-e*" ||
   context.params.command like "*ncat*-e*")
};
```

```cedar title="sondera-block-curl-upload"
@id("sondera-block-curl-upload")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*curl*--data*@*" ||
   context.params.command like "*curl*-d*@*" ||
   context.params.command like "*curl*-F*@*" ||
   context.params.command like "*curl*--upload-file*")
};
```

### Sensitive File Protection

```cedar title="sondera-block-read-ssh-keys"
@id("sondera-block-read-ssh-keys")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read" &&
  context has params && context.params has path &&
  (context.params.path like "*/.ssh/id_*" ||
   context.params.path like "*/.ssh/authorized_keys*" ||
   context.params.path like "*.pem")
};
```

```cedar title="sondera-block-read-credentials"
@id("sondera-block-read-credentials")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read" &&
  context has params && context.params has path &&
  (context.params.path like "*credentials*" ||
   context.params.path like "*secrets*" ||
   context.params.path like "*.env" ||
   context.params.path like "*.env.*")
};
```

```cedar title="sondera-block-read-cloud-creds"
@id("sondera-block-read-cloud-creds")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read" &&
  context has params && context.params has path &&
  (context.params.path like "*/.aws/*" ||
   context.params.path like "*/.gcloud/*" ||
   context.params.path like "*/.azure/*" ||
   context.params.path like "*/.kube/config*")
};
```

```cedar title="sondera-block-read-docker-creds"
@id("sondera-block-read-docker-creds")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read" &&
  context has params && context.params has path &&
  context.params.path like "*/.docker/config.json*"
};
```

```cedar title="sondera-block-read-package-tokens"
@id("sondera-block-read-package-tokens")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read" &&
  context has params && context.params has path &&
  (context.params.path like "*/.npmrc*" ||
   context.params.path like "*/.pypirc*" ||
   context.params.path like "*/pip.conf*")
};
```

```cedar title="sondera-block-read-shell-history"
@id("sondera-block-read-shell-history")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read" &&
  context has params && context.params has path &&
  (context.params.path like "*/.bash_history" ||
   context.params.path like "*/.zsh_history" ||
   context.params.path like "*/.sh_history" ||
   context.params.path like "*/.history" ||
   context.params.path like "*/.node_repl_history" ||
   context.params.path like "*/.python_history" ||
   context.params.path like "*/.psql_history" ||
   context.params.path like "*/.mysql_history" ||
   context.params.path like "*/.rediscli_history")
};
```

```cedar title="sondera-block-write-ssh"
@id("sondera-block-write-ssh")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"write" &&
  context has params && context.params has path &&
  context.params.path like "*/.ssh/*"
};
```

```cedar title="sondera-block-write-env"
@id("sondera-block-write-env")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"write" &&
  context has params && context.params has path &&
  (context.params.path like "*.env" ||
   context.params.path like "*.env.*")
};
```

```cedar title="sondera-block-write-git-internals"
@id("sondera-block-write-git-internals")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"write" &&
  context has params && context.params has path &&
  context.params.path like "*/.git/*"
};
```

```cedar title="sondera-block-edit-sensitive"
@id("sondera-block-edit-sensitive")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"edit" &&
  context has params && context.params has path &&
  (context.params.path like "*/.ssh/*" ||
   context.params.path like "*.env" ||
   context.params.path like "*.pem" ||
   context.params.path like "*credentials*")
};
```

```cedar title="sondera-block-write-system-dirs"
@id("sondera-block-write-system-dirs")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"write" &&
  context has params && context.params has path &&
  (context.params.path like "/etc/*" ||
   context.params.path like "/usr/*" ||
   context.params.path like "/bin/*" ||
   context.params.path like "/sbin/*" ||
   context.params.path like "/boot/*" ||
   context.params.path like "/sys/*" ||
   context.params.path like "/proc/*")
};
```

```cedar title="sondera-block-glob-sensitive"
@id("sondera-block-glob-sensitive")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"glob" &&
  context has params && context.params has pattern &&
  (context.params.pattern like "*/.ssh/*" ||
   context.params.pattern like "*/.aws/*" ||
   context.params.pattern like "*/.gnupg/*")
};
```

### Network Restrictions

```cedar title="sondera-block-paste-sites"
@id("sondera-block-paste-sites")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*pastebin.com*" ||
   context.params.command like "*paste.ee*" ||
   context.params.command like "*hastebin*" ||
   context.params.command like "*0x0.st*")
};
```

```cedar title="sondera-block-curl-post-external"
@id("sondera-block-curl-post-external")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  context.params.command like "*curl*-X POST*" &&
  !(context.params.command like "*localhost*") &&
  !(context.params.command like "*127.0.0.1*")
};
```

### Output Redaction (POST_TOOL)

```cedar title="sondera-redact-api-keys"
@id("sondera-redact-api-keys")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read_result" &&
  context has response &&
  (context.response like "*_API_KEY=*" ||
   context.response like "*_API_KEY\"*" ||
   context.response like "*API_KEY=*" ||
   context.response like "*APIKEY=*" ||
   context.response like "*api_key=*" ||
   context.response like "*apikey=*" ||
   context.response like "*api_key\":*" ||
   context.response like "*apiKey\":*")
};
```

```cedar title="sondera-redact-secrets"
@id("sondera-redact-secrets")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read_result" &&
  context has response &&
  (context.response like "*_SECRET=*" ||
   context.response like "*_SECRET\"*" ||
   context.response like "*SECRET=*" ||
   context.response like "*SECRET_KEY=*" ||
   context.response like "*_TOKEN=*" ||
   context.response like "*_TOKEN\"*" ||
   context.response like "*PASSWORD=*" ||
   context.response like "*PRIVATE_KEY=*" ||
   context.response like "*password\":*" ||
   context.response like "*secret\":*")
};
```

```cedar title="sondera-redact-aws-creds"
@id("sondera-redact-aws-creds")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read_result" &&
  context has response &&
  (context.response like "*AWS_ACCESS_KEY*" ||
   context.response like "*AWS_SECRET*" ||
   context.response like "*AKIA*")
};
```

```cedar title="sondera-redact-github-tokens"
@id("sondera-redact-github-tokens")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read_result" &&
  context has response &&
  (context.response like "*ghp_*" ||
   context.response like "*gho_*" ||
   context.response like "*ghu_*" ||
   context.response like "*ghs_*" ||
   context.response like "*ghr_*" ||
   context.response like "*GITHUB_TOKEN*")
};
```

```cedar title="sondera-redact-slack-tokens"
@id("sondera-redact-slack-tokens")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read_result" &&
  context has response &&
  (context.response like "*xoxb-*" ||
   context.response like "*xoxp-*" ||
   context.response like "*xoxa-*" ||
   context.response like "*xoxr-*")
};
```

```cedar title="sondera-redact-db-conn-strings"
@id("sondera-redact-db-conn-strings")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read_result" &&
  context has response &&
  (context.response like "*postgres://*:*@*" ||
   context.response like "*mysql://*:*@*" ||
   context.response like "*mongodb://*:*@*" ||
   context.response like "*redis://*:*@*")
};
```

```cedar title="sondera-redact-private-keys"
@id("sondera-redact-private-keys")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read_result" &&
  context has response &&
  (context.response like "*-----BEGIN*PRIVATE KEY-----*" ||
   context.response like "*-----BEGIN RSA PRIVATE*" ||
   context.response like "*-----BEGIN EC PRIVATE*" ||
   context.response like "*-----BEGIN OPENSSH PRIVATE*")
};
```

```cedar title="sondera-redact-anthropic-keys"
@id("sondera-redact-anthropic-keys")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read_result" &&
  context has response &&
  (context.response like "*sk-ant-*" ||
   context.response like "*ANTHROPIC_API_KEY*")
};
```

```cedar title="sondera-redact-openai-keys"
@id("sondera-redact-openai-keys")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read_result" &&
  context has response &&
  (context.response like "*sk-proj-*" ||
   context.response like "*sk-svcacct-*" ||
   context.response like "*OPENAI_API_KEY*")
};
```

```cedar title="sondera-redact-huggingface-tokens"
@id("sondera-redact-huggingface-tokens")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read_result" &&
  context has response &&
  (context.response like "*hf_*" ||
   context.response like "*HF_TOKEN*" ||
   context.response like "*HUGGINGFACE_*")
};
```

```cedar title="sondera-redact-stripe-keys"
@id("sondera-redact-stripe-keys")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read_result" &&
  context has response &&
  (context.response like "*sk_live_*" ||
   context.response like "*sk_test_*" ||
   context.response like "*pk_live_*" ||
   context.response like "*pk_test_*" ||
   context.response like "*rk_live_*" ||
   context.response like "*rk_test_*")
};
```

```cedar title="sondera-redact-google-keys"
@id("sondera-redact-google-keys")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read_result" &&
  context has response &&
  (context.response like "*AIza*" ||
   context.response like "*GOOGLE_API_KEY*" ||
   context.response like "*GOOGLE_APPLICATION_CREDENTIALS*")
};
```

```cedar title="sondera-redact-sendgrid-keys"
@id("sondera-redact-sendgrid-keys")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read_result" &&
  context has response &&
  context.response like "*SG.*"
};
```

```cedar title="sondera-redact-twilio-keys"
@id("sondera-redact-twilio-keys")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read_result" &&
  context has response &&
  (context.response like "*TWILIO_*" ||
   context.response like "*ACCOUNT_SID*")
};
```

### Guardrail Integrity

```cedar title="sondera-block-self-modify"
@id("sondera-block-self-modify")
forbid(principal, action, resource)
when {
  (action == Sondera::Action::"write" || action == Sondera::Action::"edit") &&
  context has params && context.params has path &&
  context.params.path like "*/extensions/sondera/*"
};
```

---

## OpenClaw System Pack (24 rules)

Protects OpenClaw system files from tampering. Opt-in pack for workspace and session protection.

### Workspace Identity Files

```cedar title="openclaw-block-workspace-identity"
@id("openclaw-block-workspace-identity")
forbid(principal, action, resource)
when {
  (action == Sondera::Action::"write" || action == Sondera::Action::"edit") &&
  context has params && context.params has path &&
  (context.params.path like "*/SOUL.md" ||
   context.params.path like "*/IDENTITY.md" ||
   context.params.path like "*/USER.md" ||
   context.params.path == "SOUL.md" ||
   context.params.path == "IDENTITY.md" ||
   context.params.path == "USER.md")
};
```

```cedar title="openclaw-block-exec-identity"
@id("openclaw-block-exec-identity")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*> SOUL.md*" ||
   context.params.command like "*>SOUL.md*" ||
   context.params.command like "*>> SOUL.md*" ||
   context.params.command like "*> IDENTITY.md*" ||
   context.params.command like "*> USER.md*" ||
   context.params.command like "*tee*SOUL.md*" ||
   context.params.command like "*tee*IDENTITY.md*" ||
   context.params.command like "*tee*USER.md*" ||
   context.params.command like "*sed -i*SOUL.md*" ||
   context.params.command like "*sed -i*IDENTITY.md*" ||
   context.params.command like "*sed -i*USER.md*")
};
```

```cedar title="openclaw-block-workspace-instructions"
@id("openclaw-block-workspace-instructions")
forbid(principal, action, resource)
when {
  (action == Sondera::Action::"write" || action == Sondera::Action::"edit") &&
  context has params && context.params has path &&
  (context.params.path like "*/TOOLS.md" ||
   context.params.path like "*/AGENTS.md" ||
   context.params.path like "*/BOOTSTRAP.md" ||
   context.params.path like "*/BOOT.md" ||
   context.params.path like "*/HEARTBEAT.md")
};
```

```cedar title="openclaw-block-exec-instructions"
@id("openclaw-block-exec-instructions")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*> TOOLS.md*" ||
   context.params.command like "*> AGENTS.md*" ||
   context.params.command like "*> BOOTSTRAP.md*" ||
   context.params.command like "*tee*TOOLS.md*" ||
   context.params.command like "*tee*AGENTS.md*" ||
   context.params.command like "*sed -i*TOOLS.md*" ||
   context.params.command like "*sed -i*AGENTS.md*")
};
```

```cedar title="openclaw-block-skill-instructions"
@id("openclaw-block-skill-instructions")
forbid(principal, action, resource)
when {
  (action == Sondera::Action::"write" || action == Sondera::Action::"edit") &&
  context has params && context.params has path &&
  (context.params.path like "*/SKILL.md" ||
   context.params.path == "SKILL.md")
};
```

```cedar title="openclaw-block-exec-skill"
@id("openclaw-block-exec-skill")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*> SKILL.md*" ||
   context.params.command like "*tee*SKILL.md*" ||
   context.params.command like "*sed -i*SKILL.md*")
};
```

### Configuration Protection

```cedar title="openclaw-block-main-config"
@id("openclaw-block-main-config")
forbid(principal, action, resource)
when {
  (action == Sondera::Action::"write" || action == Sondera::Action::"edit") &&
  context has params && context.params has path &&
  context.params.path like "*/.openclaw/openclaw.json"
};
```

```cedar title="openclaw-block-credentials"
@id("openclaw-block-credentials")
forbid(principal, action, resource)
when {
  (action == Sondera::Action::"write" || action == Sondera::Action::"edit") &&
  context has params && context.params has path &&
  context.params.path like "*/.openclaw/credentials/*"
};
```

```cedar title="openclaw-block-auth-profiles"
@id("openclaw-block-auth-profiles")
forbid(principal, action, resource)
when {
  (action == Sondera::Action::"write" || action == Sondera::Action::"edit") &&
  context has params && context.params has path &&
  context.params.path like "*/.openclaw/agents/*/agent/auth-profiles.json"
};
```

```cedar title="openclaw-block-read-credentials"
@id("openclaw-block-read-credentials")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read" &&
  context has params && context.params has path &&
  (context.params.path like "*/.openclaw/credentials/*" ||
   context.params.path like "*/.openclaw/agents/*/agent/auth-profiles.json")
};
```

### Session Protection

```cedar title="openclaw-block-session-transcripts"
@id("openclaw-block-session-transcripts")
forbid(principal, action, resource)
when {
  (action == Sondera::Action::"write" || action == Sondera::Action::"edit") &&
  context has params && context.params has path &&
  context.params.path like "*/.openclaw/agents/*/sessions/*.jsonl"
};
```

```cedar title="openclaw-block-session-registry"
@id("openclaw-block-session-registry")
forbid(principal, action, resource)
when {
  (action == Sondera::Action::"write" || action == Sondera::Action::"edit") &&
  context has params && context.params has path &&
  context.params.path like "*/.openclaw/agents/*/sessions/sessions.json"
};
```

```cedar title="openclaw-block-memory-databases"
@id("openclaw-block-memory-databases")
forbid(principal, action, resource)
when {
  (action == Sondera::Action::"write" || action == Sondera::Action::"edit") &&
  context has params && context.params has path &&
  context.params.path like "*/.openclaw/agents/*/sessions/*.sqlite"
};
```

### Plugin & Security

```cedar title="openclaw-block-plugin-manifests"
@id("openclaw-block-plugin-manifests")
forbid(principal, action, resource)
when {
  (action == Sondera::Action::"write" || action == Sondera::Action::"edit") &&
  context has params && context.params has path &&
  (context.params.path like "*/openclaw.plugin.json" ||
   context.params.path == "openclaw.plugin.json") &&
  !(context.params.path like "*/extensions/sondera/*")
};
```

```cedar title="openclaw-block-claude-settings"
@id("openclaw-block-claude-settings")
forbid(principal, action, resource)
when {
  (action == Sondera::Action::"write" || action == Sondera::Action::"edit") &&
  context has params && context.params has path &&
  (context.params.path like "*/.claude/settings.json" ||
   context.params.path like "*/.claude/settings.local.json")
};
```

```cedar title="openclaw-block-git-hooks"
@id("openclaw-block-git-hooks")
forbid(principal, action, resource)
when {
  (action == Sondera::Action::"write" || action == Sondera::Action::"edit") &&
  context has params && context.params has path &&
  context.params.path like "*/.git/hooks/*"
};
```

```cedar title="openclaw-block-security-config"
@id("openclaw-block-security-config")
forbid(principal, action, resource)
when {
  (action == Sondera::Action::"write" || action == Sondera::Action::"edit") &&
  context has params && context.params has path &&
  (context.params.path like "*/.secrets.baseline" ||
   context.params.path like "*/.pre-commit-config.yaml" ||
   context.params.path like "*/.detect-secrets.cfg")
};
```

### Anthropic/Claude Protection

```cedar title="openclaw-block-read-anthropic"
@id("openclaw-block-read-anthropic")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read" &&
  context has params && context.params has path &&
  context.params.path like "*/.anthropic/*"
};
```

```cedar title="openclaw-block-write-anthropic"
@id("openclaw-block-write-anthropic")
forbid(principal, action, resource)
when {
  (action == Sondera::Action::"write" || action == Sondera::Action::"edit") &&
  context has params && context.params has path &&
  context.params.path like "*/.anthropic/*"
};
```

```cedar title="openclaw-block-read-claude-desktop"
@id("openclaw-block-read-claude-desktop")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read" &&
  context has params && context.params has path &&
  (context.params.path like "*/.local/share/io.anthropic.claude/*" ||
   context.params.path like "*/Library/Application Support/Claude/*")
};
```

```cedar title="openclaw-block-write-claude-desktop"
@id("openclaw-block-write-claude-desktop")
forbid(principal, action, resource)
when {
  (action == Sondera::Action::"write" || action == Sondera::Action::"edit") &&
  context has params && context.params has path &&
  (context.params.path like "*/.local/share/io.anthropic.claude/*" ||
   context.params.path like "*/Library/Application Support/Claude/*")
};
```

```cedar title="openclaw-block-read-huggingface"
@id("openclaw-block-read-huggingface")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read" &&
  context has params && context.params has path &&
  (context.params.path like "*/.huggingface/*" ||
   context.params.path like "*/.cache/huggingface/token")
};
```

```cedar title="openclaw-block-write-huggingface"
@id("openclaw-block-write-huggingface")
forbid(principal, action, resource)
when {
  (action == Sondera::Action::"write" || action == Sondera::Action::"edit") &&
  context has params && context.params has path &&
  (context.params.path like "*/.huggingface/*" ||
   context.params.path like "*/.cache/huggingface/token")
};
```

```cedar title="openclaw-block-vscode-extensions"
@id("openclaw-block-vscode-extensions")
forbid(principal, action, resource)
when {
  (action == Sondera::Action::"write" || action == Sondera::Action::"edit") &&
  context has params && context.params has path &&
  (context.params.path like "*/.vscode/extensions/*" ||
   context.params.path like "*/.vscode-server/extensions/*")
};
```

---

## OWASP Agentic Pack (38 rules)

Advanced rules based on [OWASP Top 10 for Agentic Applications](https://genai.owasp.org). More restrictive - review before enabling.

### ASI01 - Agent Goal Hijack

```cedar title="owasp-block-shell-eval"
@id("owasp-block-shell-eval")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*eval *" ||
   context.params.command like "*$(*)*" && context.params.command like "*curl*")
};
```

### ASI02 - Tool Misuse

```cedar title="owasp-block-dns-exfil"
@id("owasp-block-dns-exfil")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*nslookup*`*`*" ||
   context.params.command like "*dig*`*`*" ||
   context.params.command like "*host*$(*)*")
};
```

```cedar title="owasp-block-socat"
@id("owasp-block-socat")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  context.params.command like "*socat*"
};
```

```cedar title="owasp-block-external-copy"
@id("owasp-block-external-copy")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*scp *@*:*" ||
   context.params.command like "*rsync*@*:*") &&
  !(context.params.command like "*localhost*") &&
  !(context.params.command like "*127.0.0.1*")
};
```

```cedar title="owasp-block-tar-exfil"
@id("owasp-block-tar-exfil")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*tar*|*curl*" ||
   context.params.command like "*tar*|*nc*" ||
   context.params.command like "*tar*|*netcat*")
};
```

```cedar title="owasp-block-db-dump"
@id("owasp-block-db-dump")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*mysqldump*--all-databases*" ||
   context.params.command like "*pg_dumpall*" ||
   context.params.command like "*mongodump*")
};
```

### ASI03 - Identity & Privilege Abuse

```cedar title="owasp-block-user-management"
@id("owasp-block-user-management")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*useradd*" ||
   context.params.command like "*userdel*" ||
   context.params.command like "*usermod*" ||
   context.params.command like "*adduser*" ||
   context.params.command like "*deluser*" ||
   context.params.command like "*groupadd*" ||
   context.params.command like "*passwd*")
};
```

```cedar title="owasp-block-read-passwd"
@id("owasp-block-read-passwd")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read" &&
  context has params && context.params has path &&
  (context.params.path like "*/etc/passwd*" ||
   context.params.path like "*/etc/shadow*" ||
   context.params.path like "*/etc/sudoers*" ||
   context.params.path like "*/etc/gshadow*")
};
```

```cedar title="owasp-block-browser-creds"
@id("owasp-block-browser-creds")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read" &&
  context has params && context.params has path &&
  (context.params.path like "*/.config/google-chrome/*Login*" ||
   context.params.path like "*/.mozilla/firefox/*.default*/logins.json*" ||
   context.params.path like "*/Library/Application Support/Google/Chrome/*Login*" ||
   context.params.path like "*Keychain*")
};
```

```cedar title="owasp-block-gpg-keys"
@id("owasp-block-gpg-keys")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read" &&
  context has params && context.params has path &&
  (context.params.path like "*/.gnupg/private*" ||
   context.params.path like "*/.gnupg/secring*" ||
   context.params.path like "*.asc" && context.params.path like "*private*")
};
```

```cedar title="owasp-block-setuid"
@id("owasp-block-setuid")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*chmod*+s*" ||
   context.params.command like "*chmod*u+s*" ||
   context.params.command like "*chmod*g+s*" ||
   context.params.command like "*chmod*4*" ||
   context.params.command like "*chmod*2*")
};
```

### ASI04 - Supply Chain Attacks

```cedar title="owasp-block-pip-url"
@id("owasp-block-pip-url")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*pip*install*http://*" ||
   context.params.command like "*pip*install*https://*" ||
   context.params.command like "*pip*install*git+*")
};
```

```cedar title="owasp-block-npm-git"
@id("owasp-block-npm-git")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*npm*install*git://*" ||
   context.params.command like "*npm*install*git+*" ||
   context.params.command like "*npm*install*github:*")
};
```

```cedar title="owasp-block-untrusted-repos"
@id("owasp-block-untrusted-repos")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*add-apt-repository*ppa:*" ||
   context.params.command like "*apt-key*add*" ||
   context.params.command like "*rpm*--import*")
};
```

```cedar title="owasp-block-package-config-write"
@id("owasp-block-package-config-write")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"write" &&
  context has params && context.params has path &&
  (context.params.path like "*/etc/apt/sources.list*" ||
   context.params.path like "*/etc/yum.repos.d/*" ||
   context.params.path like "*/.npmrc*" ||
   context.params.path like "*/.pip/pip.conf*")
};
```

```cedar title="owasp-block-download-exec"
@id("owasp-block-download-exec")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*wget*&&*chmod*+x*" ||
   context.params.command like "*curl*&&*chmod*+x*" ||
   context.params.command like "*curl*-o*;*chmod*")
};
```

### ASI05 - Unexpected Code Execution

```cedar title="owasp-block-python-exec"
@id("owasp-block-python-exec")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*python*-c*exec(*" ||
   context.params.command like "*python*-c*eval(*" ||
   context.params.command like "*python*-c*compile(*" ||
   context.params.command like "*python*-c*__import__(*")
};
```

```cedar title="owasp-block-node-exec"
@id("owasp-block-node-exec")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*node*-e*eval(*" ||
   context.params.command like "*node*-e*Function(*" ||
   context.params.command like "*node*-e*require(*child_process*")
};
```

```cedar title="owasp-block-ruby-exec"
@id("owasp-block-ruby-exec")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*ruby*-e*eval*" ||
   context.params.command like "*ruby*-e*system*" ||
   context.params.command like "*ruby*-e*exec*")
};
```

```cedar title="owasp-block-perl-exec"
@id("owasp-block-perl-exec")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*perl*-e*eval*" ||
   context.params.command like "*perl*-e*system*")
};
```

```cedar title="owasp-block-pickle-load"
@id("owasp-block-pickle-load")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*pickle.load*" ||
   context.params.command like "*pickle.loads*" ||
   context.params.command like "*marshal.load*" ||
   context.params.command like "*yaml.load*" ||
   context.params.command like "*yaml.unsafe_load*")
};
```

```cedar title="owasp-block-crontab"
@id("owasp-block-crontab")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*crontab*-e*" ||
   context.params.command like "*crontab*-r*" ||
   context.params.command like "*crontab*-l*|*" ||
   context.params.command like "*/etc/cron*")
};
```

```cedar title="owasp-block-cron-write"
@id("owasp-block-cron-write")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"write" &&
  context has params && context.params has path &&
  (context.params.path like "*/etc/cron*" ||
   context.params.path like "*/var/spool/cron*")
};
```

```cedar title="owasp-block-systemd"
@id("owasp-block-systemd")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*systemctl*enable*" ||
   context.params.command like "*systemctl*start*" ||
   context.params.command like "*systemctl*daemon-reload*")
};
```

```cedar title="owasp-block-systemd-write"
@id("owasp-block-systemd-write")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"write" &&
  context has params && context.params has path &&
  (context.params.path like "*/etc/systemd/*" ||
   context.params.path like "*/.config/systemd/*" ||
   context.params.path like "*.service")
};
```

```cedar title="owasp-block-launchd"
@id("owasp-block-launchd")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"write" &&
  context has params && context.params has path &&
  (context.params.path like "*/LaunchAgents/*" ||
   context.params.path like "*/LaunchDaemons/*")
};
```

### ASI06 - Memory & Context Poisoning

```cedar title="owasp-block-agent-memory"
@id("owasp-block-agent-memory")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read" &&
  context has params && context.params has path &&
  (context.params.path like "*/.openclaw/agents/*" ||
   context.params.path like "*/.openclaw/sessions/*")
};
```

```cedar title="owasp-block-agent-config-write"
@id("owasp-block-agent-config-write")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"write" &&
  context has params && context.params has path &&
  (context.params.path like "*/.openclaw/agents/*" ||
   context.params.path like "*/.openclaw/sessions/*")
};
```

```cedar title="owasp-block-agent-edit"
@id("owasp-block-agent-edit")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"edit" &&
  context has params && context.params has path &&
  (context.params.path like "*/.openclaw/agents/*" ||
   context.params.path like "*/.openclaw/sessions/*")
};
```

```cedar title="owasp-block-vector-db"
@id("owasp-block-vector-db")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read" &&
  context has params && context.params has path &&
  (context.params.path like "*.faiss*" ||
   context.params.path like "*.chroma*" ||
   context.params.path like "*/embeddings/*" ||
   context.params.path like "*/vector_store/*")
};
```

```cedar title="owasp-block-vector-db-write"
@id("owasp-block-vector-db-write")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"write" &&
  context has params && context.params has path &&
  (context.params.path like "*.faiss*" ||
   context.params.path like "*.chroma*" ||
   context.params.path like "*/embeddings/*" ||
   context.params.path like "*/vector_store/*")
};
```

```cedar title="owasp-redact-oauth-tokens"
@id("owasp-redact-oauth-tokens")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read_result" &&
  context has response &&
  (context.response like "*access_token*" ||
   context.response like "*refresh_token*" ||
   context.response like "*bearer *" ||
   context.response like "*Bearer *")
};
```

```cedar title="owasp-redact-jwt"
@id("owasp-redact-jwt")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read_result" &&
  context has response &&
  (context.response like "*eyJ*.*.*" ||
   context.response like "*JWT*=*")
};
```

### ASI07 - Inter-Agent Communication

```cedar title="owasp-block-mcp-config"
@id("owasp-block-mcp-config")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"read" &&
  context has params && context.params has path &&
  (context.params.path like "*/mcp.json*" ||
   context.params.path like "*/.mcp/*" ||
   context.params.path like "*mcp-servers*")
};
```

```cedar title="owasp-block-mcp-write"
@id("owasp-block-mcp-write")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"write" &&
  context has params && context.params has path &&
  (context.params.path like "*/mcp.json*" ||
   context.params.path like "*/.mcp/*" ||
   context.params.path like "*mcp-servers*")
};
```

```cedar title="owasp-block-agent-cards"
@id("owasp-block-agent-cards")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"write" &&
  context has params && context.params has path &&
  (context.params.path like "*/.well-known/agent.json*" ||
   context.params.path like "*agent-card*")
};
```

### ASI10 - Rogue Agent Prevention

```cedar title="owasp-block-agent-spawn"
@id("owasp-block-agent-spawn")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*nohup*&*" ||
   context.params.command like "*disown*" ||
   context.params.command like "*screen*-dm*" ||
   context.params.command like "*tmux*new-session*-d*")
};
```

```cedar title="owasp-block-fork-bomb"
@id("owasp-block-fork-bomb")
forbid(principal, action, resource)
when {
  action == Sondera::Action::"exec" &&
  context has params && context.params has command &&
  (context.params.command like "*while true*do*fork*" ||
   context.params.command like "*while :*do*done*" ||
   context.params.command like "*for i in*; do*&*done*")
};
```

---

## Writing Your Own Rules

Use these policies as templates for custom rules. Key patterns:

- **Action matching:** `action == Sondera::Action::"exec"` (exec, read, write, edit, glob, grep)
- **Context guards:** Always use `context has params && context.params has <field>` before accessing
- **Pattern matching:** Use `like "*pattern*"` for wildcard matching
- **Combining conditions:** Use `&&` (AND), `||` (OR), `!` (NOT)

[:octicons-arrow-right-24: Full Cedar syntax guide](../writing-policies.md)
