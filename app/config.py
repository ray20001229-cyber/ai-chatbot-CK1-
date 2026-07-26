from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "AI 客服助手 MVP"
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ai_customer_service"
    openai_api_key: str = Field(default="", repr=False)
    openai_model: str = "gpt-4.1-mini"
    openai_base_url: str | None = None
    reminder_scan_interval_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
