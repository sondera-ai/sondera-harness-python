# LangGraph Agent Examples

Agent examples using LangGraph with Sondera SDK integration.

## Installation

```bash
uv sync --group google  # Or: --group openai, --group anthropic, --group ollama, --group all
```

## Examples

- **investment_chatbot**: Investment advisory chatbot with portfolio and market tools
- **payment_agent**: Payment processing customer service agent
- **life_sciences_agent**: Clinical trial recruitment agent

## Running Examples

```bash
# Set API keys
export GOOGLE_API_KEY=...
# Or: export OPENAI_API_KEY=..., ANTHROPIC_API_KEY=...

# Login into Sondera Platform.
sondera auth login

# Run investment chatbot
uv run python -m langgraph_examples.investment_chatbot

# Run with different provider
uv run python -m langgraph_examples.investment_chatbot --provider openai
```

## Sondera Integration

All examples use `SonderaHarnessMiddleware` for policy evaluation and trajectory tracking.
