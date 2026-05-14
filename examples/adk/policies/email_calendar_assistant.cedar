// ============================================================
// Email & Calendar Assistant — Cedar Policy Example
// ============================================================
//
// Demonstrates an allowlist approach: each tool is explicitly
// permitted. Unlisted tools are denied by default.
//
// ============================================================

// Allow all user and model prompts
@id("allow-prompts")
permit(principal, action == email_calendar_assistant::Action::"Prompt", resource);

// Allow all tool outputs
@id("allow-tool-output")
permit(principal, action == email_calendar_assistant::Action::"ToolOutput", resource);

// ============================================================
// PERMIT: Tool allowlist
// ============================================================

// Allow reading emails
@id("allow-read-emails")
permit(
  principal,
  action == email_calendar_assistant::Action::"PreToolUse",
  resource
)
when { context.tool == "get_unread_emails" };

// Allow reading calendar events
@id("allow-read-calendar")
permit(
  principal,
  action == email_calendar_assistant::Action::"PreToolUse",
  resource
)
when { context.tool == "get_calendar_events" };

// Allow creating calendar events
@id("allow-create-event")
permit(
  principal,
  action == email_calendar_assistant::Action::"PreToolUse",
  resource
)
when { context.tool == "create_calendar_event" };

// Allow sending emails (restricted by forbid rules below)
@id("allow-send-email")
permit(
  principal,
  action == email_calendar_assistant::Action::"PreToolUse",
  resource
)
when { context.tool == "send_email" };

// ============================================================
// FORBID: Email restrictions
// ============================================================

// Forbid sending emails to external domains (only allow @company.com)
@id("forbid-external-email")
@description("Block emails to non-company domains")
forbid(
  principal,
  action == email_calendar_assistant::Action::"PreToolUse",
  resource
)
when {
  context.tool == "send_email" &&
  context has parameters &&
  !(context.parameters.to like "*@company.com")
};

// Forbid emails with suspicious subjects
@id("forbid-suspicious-subjects")
@description("Block emails with potentially sensitive content in subject")
forbid(
  principal,
  action == email_calendar_assistant::Action::"PreToolUse",
  resource
)
when {
  context.tool == "send_email" &&
  context has parameters &&
  (context.parameters.subject like "*password*" ||
   context.parameters.subject like "*credential*" ||
   context.parameters.subject like "*secret*" ||
   context.parameters.subject like "*api key*")
};

// Rate limiting: forbid operations after 100 steps
@id("rate-limit")
forbid(
  principal,
  action,
  resource
)
when {
  resource has step_count &&
  resource.step_count > 100
};
