from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_PATH = Path("~/.sondera/env").expanduser()


class Settings(BaseSettings):
    sondera_harness_endpoint: str = "harness.sondera.ai"
    sondera_api_token: str | None = None
    sondera_harness_client_secure: bool = True
    sondera_api_key_header: str = "authorization"

    # AI Assist - LiteLLM model format (e.g. gemini/, openai/, anthropic/,
    # ollama/, vllm/).  LiteLLM reads provider-specific env vars automatically
    # (GEMINI_API_KEY, OPENAI_API_KEY, etc.) so ai_api_key is optional.
    ai_model: str = "gemini/gemini-2.5-pro"
    ai_model_fast: str = "gemini/gemini-3.0-flash"
    ai_api_key: str | None = None  # Overrides provider-specific env vars
    ai_api_base: str | None = None  # Custom endpoint (vLLM, Ollama, etc.)
    ai_harness_enabled: bool = False  # Record AI conversations as trajectories

    # Screensaver idle timeout in seconds (0 = never)
    screensaver_timeout: int = 300

    model_config = SettingsConfigDict(
        env_file=(
            _ENV_PATH,
            ".env",
        ),
        extra="ignore",
    )

    @property
    def active_api_key(self) -> str | None:
        """Return the API key for AI features."""
        return self.ai_api_key

    @property
    def active_model_ask(self) -> str:
        """Return the ask model (LiteLLM format)."""
        return self.ai_model

    @property
    def active_model_fast(self) -> str:
        """Return the fast model (LiteLLM format)."""
        return self.ai_model_fast

    @property
    def active_endpoint(self) -> str | None:
        """Return the custom API base URL, if set."""
        return self.ai_api_base

    @property
    def ai_provider_name(self) -> str:
        """Extract the provider prefix from the model string (e.g. 'gemini')."""
        return self.ai_model.split("/", 1)[0]

    @property
    def is_gemini(self) -> bool:
        """True if current model uses Gemini provider."""
        return self.ai_provider_name == "gemini"


SETTINGS = Settings()


def reload_settings() -> Settings:
    """Reload settings from env files and return the new instance."""
    global SETTINGS  # noqa: PLW0603
    SETTINGS = Settings()
    return SETTINGS
