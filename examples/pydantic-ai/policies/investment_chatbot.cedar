// ============================================================
// PERMIT: Baseline access
// ============================================================

// Allow all user and model prompts (conversation flow)
@id("allow-prompts")
permit(principal, action == investment_chatbot::Action::"Prompt", resource);

// Allow read-only market data tools (no customer PII)
@id("allow-market-data")
permit(
  principal,
  action in [
    investment_chatbot::Action::"get_stock_quote",
    investment_chatbot::Action::"get_market_news"
  ],
  resource
);

// Allow reading portfolio data
@id("allow-portfolio")
permit(principal, action == investment_chatbot::Action::"get_portfolio", resource);

// Allow reading account info
@id("allow-account-info")
permit(principal, action == investment_chatbot::Action::"get_account_info", resource);

// Allow trade recommendations (restricted by forbid rules below)
@id("allow-trade-recommendation")
permit(principal, action == investment_chatbot::Action::"make_trade_recommendation", resource);

// Allow notifications (restricted by forbid rules below)
@id("allow-notification")
permit(principal, action == investment_chatbot::Action::"send_notification", resource);

// ============================================================
// FORBID: PII and sensitive data controls
// ============================================================

// Block notifications that leak sensitive financial identifiers
@id("forbid-pii-in-notification-body")
@description("Block notifications containing PII like SSNs or account numbers in the message body")
forbid(
  principal,
  action == investment_chatbot::Action::"send_notification",
  resource
)
when {
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
  action == investment_chatbot::Action::"send_notification",
  resource
)
when {
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
@id("forbid-large-trades")
@description("Block trade recommendations exceeding 1000 shares to prevent outsized risk")
forbid(
  principal,
  action == investment_chatbot::Action::"make_trade_recommendation",
  resource
)
when {
  context has parameters &&
  context.parameters.shares > 1000
};

// Block trade recommendations with invalid actions (only "buy" and "sell" allowed)
@id("forbid-invalid-trade-action")
@description("Only buy and sell are valid trade actions")
forbid(
  principal,
  action == investment_chatbot::Action::"make_trade_recommendation",
  resource
)
when {
  context has parameters &&
  !(context.parameters.action == "buy" || context.parameters.action == "sell")
};

// ============================================================
// FORBID: Rate limiting
// ============================================================

// Halt all tool actions after 100 trajectory steps to prevent runaway agents
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
