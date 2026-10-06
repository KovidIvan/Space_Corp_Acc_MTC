"""Application settings loaded from environment variables."""

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the local assistant."""

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    profile: Literal["cpu_light", "gpu_mid"] = "cpu_light"
    offline_mode: bool = True
    nlu_mode: Literal["llm", "rules"] = "llm"
    llm_base_url: str = "http://127.0.0.1:11434"
    llm_model: str = "qwen2.5:3b-instruct"
    max_concurrent_calls: int = Field(default=1, ge=1)
    notice_detail: Literal["minimal", "names"] = "minimal"
    public_base_url: str = "http://127.0.0.1:8000"
    database_url: str = "sqlite:///./data/callagent.db"
    data_encryption_key: SecretStr | None = None
    session_secret: SecretStr | None = None
    telegram_bot_token: SecretStr | None = None


settings = Settings()
