// ============================================================
// Investment Chatbot — Cedar Policy Example
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
// These policies work both with the local CedarPolicyHarness
// (Python SDK) and the remote server harness.
//
// ============================================================

// ============================================================
// PERMIT: Baseline access
// ============================================================

// Allow all user and model prompts (conversation flow)
@id("allow-prompts")
permit(principal, action == investment_chatbot::Action::"Prompt", resource);

// Allow all tool outputs (post-execution observation)
@id("allow-tool-output")
permit(principal, action == investment_chatbot::Action::"ToolOutput", resource);

// ============================================================
// PERMIT: Tool allowlist
// ============================================================
// Each tool the agent may invoke must be explicitly permitted.
// Unlisted tools are denied by default — this is intentional.

// Allow read-only market data tools (no customer PII)
@id("allow-market-data")
permit(
  principal,
  action == investment_chatbot::Action::"PreToolUse",
  resource
)
when {
  context.tool == "get_stock_quote" ||
  context.tool == "get_market_news"
};

// Allow reading portfolio data
@id("allow-portfolio")
permit(
  principal,
  action == investment_chatbot::Action::"PreToolUse",
  resource
)
when { context.tool == "get_portfolio" };

// Allow reading account info
@id("allow-account-info")
permit(
  principal,
  action == investment_chatbot::Action::"PreToolUse",
  resource
)
when { context.tool == "get_account_info" };

// Allow trade recommendations (restricted by forbid rules below)
@id("allow-trade-recommendation")
permit(
  principal,
  action == investment_chatbot::Action::"PreToolUse",
  resource
)
when { context.tool == "make_trade_recommendation" };

// Allow notifications (restricted by forbid rules below)
@id("allow-notification")
permit(
  principal,
  action == investment_chatbot::Action::"PreToolUse",
  resource
)
when { context.tool == "send_notification" };

// ============================================================
// FORBID: PII and sensitive data controls
// ============================================================

// Block notifications that leak sensitive financial identifiers
@id("forbid-pii-in-notification-body")
@description("Block notifications containing PII like SSNs or account numbers in the message body")
forbid(
  principal,
  action == investment_chatbot::Action::"PreToolUse",
  resource
)
when {
  context.tool == "send_notification" &&
  context has parameters &&
  (context.parameters.message like "*account number*" ||
   context.parameters.message like "*Account Number*" ||
   context.parameters.message like "*social security*" ||
   context.parameters.message like "*Social Security*" ||
   context.parameters.message like "*ssn*" ||
   context.parameters.message like "*SSN*")
};

// Block notifications that leak sensitive data in the subject line
@id("forbid-pii-in-notification-subject")
@description("Block notifications containing PII in the subject line")
forbid(
  principal,
  action == investment_chatbot::Action::"PreToolUse",
  resource
)
when {
  context.tool == "send_notification" &&
  context has parameters &&
  (context.parameters.subject like "*account number*" ||
   context.parameters.subject like "*Account Number*" ||
   context.parameters.subject like "*social security*" ||
   context.parameters.subject like "*Social Security*" ||
   context.parameters.subject like "*SSN*" ||
   context.parameters.subject like "*ssn*")
};

// ============================================================
// FORBID: Trade recommendation guardrails
// ============================================================

// Block unusually large trade recommendations (> 1000 shares)
// NOTE: Typed parameter comparison (context.parameters.shares) is a
// local-only extension. For server-compatible numeric guards, consider
// server-side custom context or use context.input on the remote harness.
@id("forbid-large-trades")
@description("Block trade recommendations exceeding 1000 shares to prevent outsized risk")
forbid(
  principal,
  action == investment_chatbot::Action::"PreToolUse",
  resource
)
when {
  context.tool == "make_trade_recommendation" &&
  context has parameters &&
  context.parameters.shares > 1000
};

// Block trade recommendations with invalid actions (only "buy" and "sell" allowed)
@id("forbid-invalid-trade-action")
@description("Only buy and sell are valid trade actions")
forbid(
  principal,
  action == investment_chatbot::Action::"PreToolUse",
  resource
)
when {
  context.tool == "make_trade_recommendation" &&
  context has parameters &&
  !(context.parameters.action == "buy" || context.parameters.action == "sell")
};

// ============================================================
// FORBID: Rate limiting
// ============================================================

// Halt all tool actions after 100 trajectory steps to prevent runaway agents.
// Fires on ToolOutput events where resource is the Trajectory entity
// (Tool entities used by PreToolUse do not carry step_count).
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
