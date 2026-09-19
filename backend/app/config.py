import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent


def _env_files() -> tuple[Path, ...] | None:
    # the test suite opts out so that a developer .env cannot change results
    if os.getenv("APP_SKIP_ENV_FILE") == "1":
        return None
    return (REPO_ROOT / ".env", BACKEND_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(),
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

    ai_client: Literal["fake", "deepseek", "openai", "chain"] = "fake"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    ai_timeout_seconds: float = Field(default=30.0, ge=1.0)
    ai_max_retries: int = Field(default=2, ge=0, le=5)
    ai_retry_backoff_seconds: float = Field(default=1.5, ge=0.0)
    ai_temperature: float = Field(default=1.0, ge=0.0, le=2.0)
    ai_max_tokens: int = Field(default=300, ge=32)
    ai_max_variation_length: int = Field(default=500, ge=32)
    ai_sentiment_threshold: float = Field(default=0.6, ge=0.0, le=1.0)

    telegram_client: Literal["fake", "aiogram"] = "fake"
    telegram_timeout_seconds: float = Field(default=15.0, ge=1.0)
    leads_poll_seconds: int = Field(default=60, ge=10, le=600)
    leads_history_limit: int = Field(default=20, ge=1, le=200)
    inbox_poll_seconds: int = Field(default=300, ge=30, le=3600)
    inbox_poll_limit: int = Field(default=20, ge=1, le=200)

    auth_client: Literal["fake", "playwright"] = "fake"
    browser_no_sandbox: bool = False
    browser_disable_dev_shm: bool = False
    login_wait_ms: int = Field(default=60_000, ge=1_000)
    login_ip_check_attempts: int = Field(default=2, ge=0, le=5)
    vnc_enabled: bool = False
    vnc_public_url: str = ""

    proxy_provider: Literal["fake", "lteboost"] = "fake"
    proxy_api_key: str = ""
    proxy_api_base_url: str = "https://gb.lteboost.com/api/client/v1"
    proxy_api_timeout_seconds: float = Field(default=30.0, ge=1.0)
    proxy_default_country: str = "RU"
    proxy_default_type: Literal["mobile", "residential", "datacenter"] = "residential"
    proxy_default_lifetime_minutes: int = Field(default=10_080, ge=1, le=10_080)
    login_settle_ms: int = Field(default=6_000, ge=0)
    login_session_ttl_seconds: int = Field(default=600, ge=60, le=3_600)
    sessions_dir: str = "data/sessions"

    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:4173"]
    panel_api_token: str = "dev-panel-token"


@lru_cache
def get_settings() -> Settings:
    return Settings()
