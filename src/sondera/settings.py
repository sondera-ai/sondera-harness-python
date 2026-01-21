from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    sondera_harness_endpoint: str = "harness.sondera.ai"
    sondera_api_token: str | None = None
    sondera_harness_client_secure: bool = True

    model_config = SettingsConfigDict(
        env_file=(
            Path("~/.sondera/env").expanduser(),
            ".env",
        ),
        extra="ignore",
    )


SETTINGS = Settings()
