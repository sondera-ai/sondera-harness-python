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

All examples use `SonderaProvider` for policy evaluation and trajectory tracking.
`provider.govern(agent, ...)` registers four native pydantic-ai hooks on the agent
(`run`, `before_model_request`, `after_model_request`, `tool_execute`) so that the
harness sees every prompt, response, and tool call. Tool denials raise
`SkipToolExecution` (or `ModelRetry` if `Strategy.STEER` is configured).
