# ADK Agent Examples

Agent examples using Google ADK with Sondera SDK integration.

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
export GOOGLE_API_KEY=...

# Login into Sondera Platform.
sondera auth login

# Run investment chatbot
uv run python -m adk_examples.investment_chatbot

# Run payment agent
uv run python -m adk_examples.payment_agent

# Run email/calendar assistant
uv run python -m adk_examples.email_calendar_assistant
```

## Sondera Integration

All examples use `SonderaHarnessPlugin` for policy evaluation and trajectory tracking.
