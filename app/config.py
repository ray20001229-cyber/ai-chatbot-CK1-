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
    redis_url: str = "redis://localhost:6379/0"
    webhook_shared_secret: str = Field(default="", repr=False)
    upload_dir: str = "data/uploads"
    max_upload_bytes: int = 10 * 1024 * 1024
    email_imap_enabled: bool = False
    email_imap_host: str = ""
    email_imap_port: int = 993
    email_imap_username: str = ""
    email_imap_password: str = Field(default="", repr=False)
    email_imap_folder: str = "INBOX"
    email_poll_interval_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
