// ============================================================
// Coding Assistant — Cedar Policy Example (Pydantic AI)
// ============================================================
//
// Demonstrates an allowlist approach: each tool is explicitly
// permitted via a `context.tool` guard. Unlisted tools are
// denied by default. Forbid rules add restrictions on top.
//
// ============================================================

// ============================================================
// PERMIT: Baseline access
// ============================================================

@id("allow-prompts")
permit(principal, action == coding_assistant::Action::"Prompt", resource);

// Allow all tool outputs
@id("allow-tool-output")
permit(principal, action == coding_assistant::Action::"ToolOutput", resource);

// ============================================================
// PERMIT: Tool allowlist
// ============================================================

// Read-only operations
@id("allow-read-file")
permit(principal, action == coding_assistant::Action::"PreToolUse", resource)
when { context.tool == "read_file" };

@id("allow-list-directory")
permit(principal, action == coding_assistant::Action::"PreToolUse", resource)
when { context.tool == "list_directory" };

@id("allow-search-files")
permit(principal, action == coding_assistant::Action::"PreToolUse", resource)
when { context.tool == "search_files" };

// State-changing operations (restricted by forbid rules below)
@id("allow-write-file")
permit(principal, action == coding_assistant::Action::"PreToolUse", resource)
when { context.tool == "write_file" };

@id("allow-run-command")
permit(principal, action == coding_assistant::Action::"PreToolUse", resource)
when { context.tool == "run_command" };

// ============================================================
// FORBID: Dangerous shell commands
// ============================================================

@id("forbid-destructive-commands")
@description("Block destructive shell commands like rm -rf, mkfs, dd")
forbid(
  principal,
  action == coding_assistant::Action::"PreToolUse",
  resource
)
when {
  context.tool == "run_command" &&
  context has parameters &&
  (context.parameters.command like "*rm -rf*" ||
   context.parameters.command like "*rm -r /*" ||
   context.parameters.command like "*mkfs*" ||
   context.parameters.command like "*dd if=*" ||
   context.parameters.command like "*:(){:|:&};:*" ||
   context.parameters.command like "*> /dev/sd*" ||
   context.parameters.command like "*chmod 777 /*")
};

@id("forbid-privilege-escalation")
@description("Block commands that attempt privilege escalation")
forbid(
  principal,
  action == coding_assistant::Action::"PreToolUse",
  resource
)
when {
  context.tool == "run_command" &&
  context has parameters &&
  (context.parameters.command like "*sudo *" ||
   context.parameters.command like "*su -*" ||
   context.parameters.command like "*passwd*" ||
   context.parameters.command like "*chown*")
};

// ============================================================
// FORBID: Sensitive file access
// ============================================================

@id("forbid-read-secrets")
@description("Block reading sensitive credential files")
forbid(
  principal,
  action == coding_assistant::Action::"PreToolUse",
  resource
)
when {
  context.tool == "read_file" &&
  context has parameters &&
  (context.parameters.file_path like "*.env*" ||
   context.parameters.file_path like "*credentials*" ||
   context.parameters.file_path like "*secret*" ||
   context.parameters.file_path like "*/etc/shadow*" ||
   context.parameters.file_path like "*id_rsa*" ||
   context.parameters.file_path like "*id_ed25519*")
};

@id("forbid-write-system-paths")
@description("Block writing to system directories")
forbid(
  principal,
  action == coding_assistant::Action::"PreToolUse",
  resource
)
when {
  context.tool == "write_file" &&
  context has parameters &&
  (context.parameters.file_path like "/etc/*" ||
   context.parameters.file_path like "/usr/*" ||
   context.parameters.file_path like "/bin/*" ||
   context.parameters.file_path like "/sbin/*" ||
   context.parameters.file_path like "/var/*")
};

// ============================================================
// FORBID: Rate limiting
// ============================================================

@id("rate-limit")
@description("Halt agent after 100 steps to prevent runaway execution")
forbid(
  principal,
  action,
  resource
)
when {
  resource has step_count &&
  resource.step_count > 100
};
