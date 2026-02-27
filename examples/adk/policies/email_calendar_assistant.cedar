// Allow all user and model prompts
@id("allow-prompts")
permit(principal, action == email_calendar_assistant::Action::"Prompt", resource);

// Allow reading emails
@id("allow-read-emails")
permit(principal, action == email_calendar_assistant::Action::"get_unread_emails", resource);

// Allow reading calendar events
@id("allow-read-calendar")
permit(principal, action == email_calendar_assistant::Action::"get_calendar_events", resource);

// Allow creating calendar events
@id("allow-create-event")
permit(principal, action == email_calendar_assistant::Action::"create_calendar_event", resource);

// Allow sending emails by default (restricted by forbid rules below)
@id("allow-send-email")
permit(principal, action == email_calendar_assistant::Action::"send_email", resource);

// Forbid sending emails to external domains (only allow @company.com)
@id("forbid-external-email")
@description("Block emails to non-company domains")
forbid(
  principal,
  action == email_calendar_assistant::Action::"send_email",
  resource
)
when {
  context has parameters &&
  !(context.parameters.to like "*@company.com")
};

// Forbid emails with suspicious subjects
@id("forbid-suspicious-subjects")
@description("Block emails with potentially sensitive content in subject")
forbid(
  principal,
  action == email_calendar_assistant::Action::"send_email",
  resource
)
when {
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
