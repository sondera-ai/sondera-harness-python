"""LLM provider utilities shared across examples."""

from typing import Literal

Provider = Literal["openai", "anthropic", "google", "ollama"]

try:
    from langchain_openai import ChatOpenAI  # type: ignore[import-not-found]
except ImportError:
    ChatOpenAI = None

try:
    from langchain_anthropic import ChatAnthropic  # type: ignore[import-not-found]
except ImportError:
    ChatAnthropic = None

try:
    from langchain_google_genai import (  # type: ignore[import-not-found]
        ChatGoogleGenerativeAI,
    )
except ImportError:
    ChatGoogleGenerativeAI = None

try:
    from langchain_community.chat_models import (  # type: ignore[import-not-found]
        ChatOllama,
    )
except ImportError:
    ChatOllama = None

DEFAULT_MODELS: dict[Provider, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-7-sonnet-20250219",
    "google": "gemini-2.5-flash",
    "ollama": "llama3.1",
}


def make_model(provider: Provider, model: str | None = None, temperature: float = 0.2):
    """Create a LangChain chat model for the requested provider.

    Args:
        provider: LLM provider (openai, anthropic, google, ollama)
        model: Model name (uses default if None)
        temperature: Sampling temperature

    Returns:
        LangChain chat model instance
    """
    name = model or DEFAULT_MODELS[provider]

    if provider == "openai":
        if ChatOpenAI is None:
            raise ImportError("Install langchain-openai to use the OpenAI provider.")
        return ChatOpenAI(model=name, temperature=temperature)
    if provider == "anthropic":
        if ChatAnthropic is None:
            raise ImportError(
                "Install langchain-anthropic to use the Anthropic provider."
            )
        return ChatAnthropic(model=name, temperature=temperature)
    if provider == "google":
        if ChatGoogleGenerativeAI is None:
            raise ImportError(
                "Install langchain-google-genai to use the Gemini provider."
            )
        return ChatGoogleGenerativeAI(model=name, temperature=temperature)
    if provider == "ollama":
        if ChatOllama is None:
            raise ImportError("Install langchain-community to use the Ollama provider.")
        return ChatOllama(model=name, temperature=temperature)

    raise ValueError(f"Unsupported provider: {provider}")
