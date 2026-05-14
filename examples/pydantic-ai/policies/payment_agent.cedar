// ============================================================
// Payment Agent — Cedar Policy Example
// ============================================================
//
// Demonstrates an allowlist approach to agent governance using
// the server-aligned PreToolUse / ToolOutput / Prompt action model.
//
// Key pattern: each tool is explicitly permitted via a
// `context.tool == "..."` guard on the PreToolUse action. Tools
// not listed here are denied by default (no blanket permit).
// This is the recommended posture for production deployments.
//
// ============================================================

// ============================================================
// PERMIT: Baseline access
// ============================================================

// Allow all user and model prompts (conversation flow)
@id("allow-prompts")
permit(principal, action == payment_agent::Action::"Prompt", resource);

// Allow all tool outputs (post-execution observation)
@id("allow-tool-output")
permit(principal, action == payment_agent::Action::"ToolOutput", resource);

// ============================================================
// PERMIT: Tool allowlist
// ============================================================

// Allow read-only customer data lookups
@id("allow-customer-lookups")
permit(
  principal,
  action == payment_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "get_customer_profile" ||
  context.tool == "get_transactions"
};

// Allow refunds (restricted by forbid rules below)
@id("allow-refund")
permit(
  principal,
  action == payment_agent::Action::"PreToolUse",
  resource
)
when { context.tool == "initiate_refund" };

// Allow emails (restricted by forbid rules below)
@id("allow-send-email")
permit(
  principal,
  action == payment_agent::Action::"PreToolUse",
  resource
)
when { context.tool == "send_email" };

// ============================================================
// FORBID: Refund guardrails
// ============================================================

// Block refunds over $10,000
// NOTE: Typed parameter comparison (context.parameters.amount) is a
// local-only extension — not available on the remote server harness.
@id("forbid-large-refund")
@description("Block refunds exceeding $10,000 to prevent unauthorized large payouts")
forbid(
  principal,
  action == payment_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "initiate_refund" &&
  context has parameters &&
  context.parameters.amount > 10000
};

// Block zero or negative refund amounts
@id("forbid-invalid-refund-amount")
@description("Block refunds with zero or negative amounts")
forbid(
  principal,
  action == payment_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "initiate_refund" &&
  context has parameters &&
  context.parameters.amount <= 0
};

// ============================================================
// FORBID: PII and sensitive data controls
// ============================================================

// Block emails containing credit card or financial account data in body
@id("forbid-pii-in-email-body")
@description("Block emails that may contain credit card or financial account data in the body")
forbid(
  principal,
  action == payment_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "send_email" &&
  context has parameters &&
  (context.parameters.body like "*credit card*" ||
   context.parameters.body like "*Credit Card*" ||
   context.parameters.body like "*card number*" ||
   context.parameters.body like "*Card Number*" ||
   context.parameters.body like "*cc_number*" ||
   context.parameters.body like "*CVV*" ||
   context.parameters.body like "*cvv*" ||
   context.parameters.body like "*social security*" ||
   context.parameters.body like "*Social Security*" ||
   context.parameters.body like "*SSN*" ||
   context.parameters.body like "*ssn*" ||
   context.parameters.body like "*account number*" ||
   context.parameters.body like "*Account Number*")
};

// Block emails containing sensitive data in the subject line
@id("forbid-pii-in-email-subject")
@description("Block emails that may contain sensitive data in the subject line")
forbid(
  principal,
  action == payment_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "send_email" &&
  context has parameters &&
  (context.parameters.subject like "*credit card*" ||
   context.parameters.subject like "*Credit Card*" ||
   context.parameters.subject like "*card number*" ||
   context.parameters.subject like "*Card Number*" ||
   context.parameters.subject like "*SSN*" ||
   context.parameters.subject like "*ssn*" ||
   context.parameters.subject like "*social security*" ||
   context.parameters.subject like "*Social Security*" ||
   context.parameters.subject like "*account number*" ||
   context.parameters.subject like "*Account Number*")
};

// ============================================================
// FORBID: Rate limiting
// ============================================================

// Halt all actions after 100 trajectory steps to prevent runaway agents
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
