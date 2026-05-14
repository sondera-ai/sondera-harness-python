// ============================================================================
// CLAUDE CODE - PLAN MODE POLICIES
// ============================================================================
//
// These policies enforce plan mode restrictions by blocking state-changing
// operations when permission_mode == "plan". In plan mode, Claude Code should
// only explore the codebase (read, search, etc.) and not make any modifications.
//
// NOTE: The typed parameters extension (context.parameters) is a local-only
// feature. These policies work with the local CedarPolicyHarness but typed
// parameter checks are not available on the remote server harness.
//
// ============================================================================

// ============================================================================
// PLAN MODE BLOCKING
// ============================================================================

@id("forbid-write-in-plan-mode")
forbid(
    principal,
    action == claude_code::Action::"PreToolUse",
    resource
)
when {
    context.tool == "Write" &&
    context has parameters &&
    context.parameters has permission_mode &&
    context.parameters.permission_mode == "plan"
}
unless {
    context.parameters has is_plan_file &&
    context.parameters.is_plan_file == true
};

@id("forbid-edit-in-plan-mode")
forbid(
    principal,
    action == claude_code::Action::"PreToolUse",
    resource
)
when {
    context.tool == "Edit" &&
    context has parameters &&
    context.parameters has permission_mode &&
    context.parameters.permission_mode == "plan"
}
unless {
    context.parameters has is_plan_file &&
    context.parameters.is_plan_file == true
};

// ============================================================================
// DEFAULT PERMIT
// ============================================================================

@id("permit-all")
permit(principal, action, resource);
