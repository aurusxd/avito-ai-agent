from functools import lru_cache
from pathlib import Path

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

    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:4173"]
    panel_api_token: str = "dev-panel-token"


@lru_cache
def get_settings() -> Settings:
    return Settings()
