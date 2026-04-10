// ============================================================
// PERMIT: Baseline access
// ============================================================

@id("allow-prompts")
permit(principal, action == coding_assistant::Action::"Prompt", resource);

// Allow read-only operations
@id("allow-read-file")
permit(principal, action == coding_assistant::Action::"read_file", resource);

@id("allow-list-directory")
permit(principal, action == coding_assistant::Action::"list_directory", resource);

@id("allow-search-files")
permit(principal, action == coding_assistant::Action::"search_files", resource);

// Allow file writes (restricted by forbid rules below)
@id("allow-write-file")
permit(principal, action == coding_assistant::Action::"write_file", resource);

// Allow shell commands (restricted by forbid rules below)
@id("allow-run-command")
permit(principal, action == coding_assistant::Action::"run_command", resource);

// ============================================================
// FORBID: Dangerous shell commands
// ============================================================

@id("forbid-destructive-commands")
@description("Block destructive shell commands like rm -rf, mkfs, dd")
forbid(
  principal,
  action == coding_assistant::Action::"run_command",
  resource
)
when {
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
  action == coding_assistant::Action::"run_command",
  resource
)
when {
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
  action == coding_assistant::Action::"read_file",
  resource
)
when {
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
  action == coding_assistant::Action::"write_file",
  resource
)
when {
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
