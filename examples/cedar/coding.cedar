// ============================================================
// Coding Agent — Cedar Policy Example
// ============================================================
//
// Demonstrates an allowlist approach: each tool is explicitly
// permitted via a `context.tool` guard. Unlisted tools are
// denied by default. Forbid rules add restrictions on top.
//
// ============================================================

@id("allow-prompts")
permit(principal, action == Coding_Agent::Action::"Prompt", resource);

// Allow all tool outputs
@id("allow-tool-output")
permit(principal, action == Coding_Agent::Action::"ToolOutput", resource);

// ============================================================
// PERMIT: Tool allowlist
// ============================================================

// Read-only operations — generally safe
@id("allow-read")
permit(principal, action == Coding_Agent::Action::"PreToolUse", resource)
when { context.tool == "Read" };

@id("allow-glob")
permit(principal, action == Coding_Agent::Action::"PreToolUse", resource)
when { context.tool == "Glob" };

@id("allow-grep")
permit(principal, action == Coding_Agent::Action::"PreToolUse", resource)
when { context.tool == "Grep" };

// State-changing operations — permitted but restricted by forbid rules
@id("allow-write")
permit(principal, action == Coding_Agent::Action::"PreToolUse", resource)
when { context.tool == "Write" };

@id("allow-edit")
permit(principal, action == Coding_Agent::Action::"PreToolUse", resource)
when { context.tool == "Edit" };

@id("allow-bash")
permit(principal, action == Coding_Agent::Action::"PreToolUse", resource)
when { context.tool == "Bash" };

// Network operations — permitted but restricted by forbid rules
@id("allow-web-search")
permit(principal, action == Coding_Agent::Action::"PreToolUse", resource)
when { context.tool == "WebSearch" };

@id("allow-web-fetch")
permit(principal, action == Coding_Agent::Action::"PreToolUse", resource)
when { context.tool == "WebFetch" };

// ============================================================
// FORBID: Dangerous operations
// ============================================================

@id("forbid-untrusted-fetch")
forbid(
  principal,
  action == Coding_Agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "WebFetch" &&
  context has parameters &&
  (context.parameters.url like "*pastebin*" ||
   context.parameters.url like "*raw.githubusercontent.com*")
};

@id("forbid-sensitive-write")
forbid(
  principal,
  action == Coding_Agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Write" &&
  context has parameters &&
  (context.parameters.file_path like "*.env*" ||
   context.parameters.file_path like "*.git/*" ||
   context.parameters.file_path like "*credentials*" ||
   context.parameters.file_path like "*secrets*")
};

@id("forbid-sensitive-edit")
forbid(
  principal,
  action == Coding_Agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Edit" &&
  context has parameters &&
  (context.parameters.file_path like "*.env*" ||
   context.parameters.file_path like "*id_rsa*" ||
   context.parameters.file_path like "*.pem*")
};

@id("forbid-dangerous-bash")
forbid(
  principal,
  action == Coding_Agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Bash" &&
  context has parameters &&
  (context.parameters.command like "*rm -rf /*" ||
   context.parameters.command like "*mkfs*" ||
   context.parameters.command like "*dd if=/dev/zero*" ||
   context.parameters.command like "*> /dev/sda*")
};

// ============================================================
// FORBID: Rate limiting
// ============================================================

@id("rate-limit-trajectory")
forbid(
  principal,
  action,
  resource
)
when {
  resource has step_count &&
  resource.step_count > 1000
};
