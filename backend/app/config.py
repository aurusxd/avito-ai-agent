from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "avito-bot"
    debug: bool = False
    log_level: str = "INFO"
    timezone: str = "Europe/Moscow"

    database_url: str = "sqlite+aiosqlite:///./data/avito.db"

    deepseek_api_key: str = ""
    openai_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_operator_chat_id: str = ""

    delay_min_minutes: int = Field(default=5, ge=1)
    delay_max_minutes: int = Field(default=15, ge=1)
    daily_message_limit: int = Field(default=15, ge=1)
    account_rotation_size: int = Field(default=3, ge=1, le=3)

    schedule_window_start: int = Field(default=9, ge=0, le=23)
    schedule_window_end: int = Field(default=21, ge=1, le=24)

    avito_client: Literal["fake", "playwright"] = "fake"
    avito_base_url: str = "https://www.avito.ru"
    avito_storage_state_path: str = "state.json"
    avito_headless: bool = True
    avito_proxy_server: str = ""
    parser_max_pages: int = Field(default=1, ge=1, le=50)
    parser_max_sellers_per_run: int = Field(default=0, ge=0)
    parser_delay_min_seconds: float = Field(default=2.0, ge=0.0)
    parser_delay_max_seconds: float = Field(default=5.0, ge=0.0)
    parser_nav_timeout_ms: int = Field(default=60_000, ge=1_000)
    outreach_type_delay_min_ms: int = Field(default=40, ge=0)
    outreach_type_delay_max_ms: int = Field(default=140, ge=0)
    outreach_settle_ms: int = Field(default=2_500, ge=0)
    avito_block_check_delay_ms: int = Field(default=1_500, ge=0)
    parser_nav_retries: int = Field(default=2, ge=0, le=10)
    parser_profile_settle_ms: int = Field(default=1_500, ge=0)
    parser_retry_backoff_seconds: float = Field(default=3.0, ge=0.0)

    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:4173"]
    panel_api_token: str = "dev-panel-token"


@lru_cache
def get_settings() -> Settings:
    return Settings()
