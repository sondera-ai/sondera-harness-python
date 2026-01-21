# Strands Agent Examples

Agent examples using AWS Strands Agent SDK with Sondera SDK integration.

## Installation

```bash
uv sync
```

## Examples

- **investment_chatbot**: Investment advisory chatbot with portfolio and market tools
- **payment_agent**: Payment processing customer service agent
- **email_calendar_assistant**: Email and calendar management assistant

## Running Examples

```bash
# Set API keys
export AWS_REGION=us-east-1
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...

# Login into Sondera Platform.
sondera auth login

# Run investment chatbot
uv run python -m strands_examples.investment_chatbot

# Run payment agent
uv run python -m strands_examples.payment_agent

# Run email/calendar assistant
uv run python -m strands_examples.email_calendar_assistant
```

## Sondera Integration

All examples use `SonderaHarnessHook` for policy evaluation and trajectory tracking.
