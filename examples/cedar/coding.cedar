@id("allow-prompts")
permit(principal, action == Coding_Agent::Action::"Prompt", resource);

@id("allow-read")
permit(principal, action == Coding_Agent::Action::"Read", resource);

@id("allow-web-search")
permit(principal, action == Coding_Agent::Action::"WebSearch", resource);

@id("allow-web-fetch")
permit(principal, action == Coding_Agent::Action::"WebFetch", resource);

@id("forbid-untrusted-fetch")
forbid(
  principal,
  action == Coding_Agent::Action::"WebFetch",
  resource
)
when {
  context has parameters &&
  (context.parameters.url like "*pastebin*" ||
   context.parameters.url like "*raw.githubusercontent.com*")
};

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

@id("allow-glob")
permit(principal, action == Coding_Agent::Action::"Glob", resource);

@id("allow-grep")
permit(principal, action == Coding_Agent::Action::"Grep", resource);

@id("allow-write")
permit(principal, action == Coding_Agent::Action::"Write", resource);

@id("allow-edit")
permit(principal, action == Coding_Agent::Action::"Edit", resource);

@id("forbid-sensitive-write")
forbid(
  principal,
  action == Coding_Agent::Action::"Write",
  resource
)
when {
  context has parameters &&
  (context.parameters.file_path like "*.env*" ||
   context.parameters.file_path like "*.git/*" ||
   context.parameters.file_path like "*credentials*" ||
   context.parameters.file_path like "*secrets*")
};

@id("forbid-sensitive-edit")
forbid(
  principal,
  action == Coding_Agent::Action::"Edit",
  resource
)
when {
  context has parameters &&
  (context.parameters.file_path like "*.env*" ||
   context.parameters.file_path like "*id_rsa*" ||
   context.parameters.file_path like "*.pem*")
};

@id("allow-bash")
permit(principal, action == Coding_Agent::Action::"Bash", resource);

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