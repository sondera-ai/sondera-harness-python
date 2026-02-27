// ============================================================================
// CLAUDE CODE - PLAN MODE POLICIES
// ============================================================================
//
// These policies enforce plan mode restrictions by blocking state-changing
// operations when permission_mode == "plan". In plan mode, Claude Code should
// only explore the codebase (read, search, etc.) and not make any modifications.
//
// ============================================================================

// ============================================================================
// PLAN MODE BLOCKING
// ============================================================================

@id("forbid-write-in-plan-mode")
forbid(
    principal,
    action == claude_code::Action::"Write",
    resource
)
when {
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
    action == claude_code::Action::"Edit",
    resource
)
when {
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
