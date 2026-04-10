# Pydantic AI Agent Examples

Agent examples using Pydantic AI with Sondera SDK integration.

## Installation

```bash
uv sync --group google  # Or: --group openai, --group anthropic, --group all
```

## Examples

- **investment_chatbot**: Investment advisory chatbot with portfolio and market tools
- **payment_agent**: Payment processing customer service agent with refund guardrails
- **life_sciences_agent**: Clinical trial recruitment pipeline with EHR screening
- **coding_assistant**: Coding assistant with file ops, shell execution, and search
- **quickstart**: Minimal single-tool example

## Running Examples

```bash
# Set API keys
export GOOGLE_API_KEY=...
# Or: export OPENAI_API_KEY=..., ANTHROPIC_API_KEY=...

# Login into Sondera Platform
sondera auth login

# Run investment chatbot
uv run python -m pydantic_ai_examples.investment_chatbot

# Run with different provider
uv run python -m pydantic_ai_examples.investment_chatbot --provider openai

# Run with local Cedar policy evaluation
uv run python -m pydantic_ai_examples.investment_chatbot --cedar

# Run with enforcement (block on policy violation)
uv run python -m pydantic_ai_examples.investment_chatbot --enforce
```

## Sondera Integration

All examples use `PydanticAIProvider` and `GovernedAgent` for policy evaluation and trajectory tracking.
Tool calls are adjudicated through `SonderaGovernedToolset`, which wraps each tool with pre- and post-execution policy checks.
