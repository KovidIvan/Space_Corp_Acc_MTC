"""Application settings loaded from environment variables."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the local assistant."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

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
    owner_name: str | None = None
    owner_company: str | None = None
    owner_password: SecretStr | None = None
    telegram_bot_token: SecretStr | None = None

    @field_validator("owner_name", "owner_company", mode="before")
    @classmethod
    def strip_strings(cls, v: str | None) -> str | None:
        """Strip whitespace from string settings."""
        if isinstance(v, str):
            return v.strip() or None
        return v

    @field_validator("data_encryption_key", "session_secret", "owner_password", "telegram_bot_token", mode="before")
    @classmethod
    def strip_secret_strings(cls, v: SecretStr | None) -> SecretStr | None:
        """Strip whitespace from secret string settings and convert to SecretStr."""
        if isinstance(v, str):
            stripped = v.strip()
            return SecretStr(stripped) if stripped else None
        if isinstance(v, SecretStr):
            return v
        return v

    @property
    def dashboard_configured(self) -> bool:
        """Whether all secrets and owner details required by the dashboard are set."""
        return all(
            (
                self.owner_name,
                self.owner_company,
                self.owner_password and self.owner_password.get_secret_value(),
                self.session_secret and self.session_secret.get_secret_value(),
                self.data_encryption_key and self.data_encryption_key.get_secret_value(),
            )
        )


settings = Settings()
