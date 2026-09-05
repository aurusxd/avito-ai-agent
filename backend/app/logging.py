import sys
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from loguru import Record

from app.config import get_settings

_SECRET_KEYS = ("token", "password", "cookie", "api_key", "storage_state", "authorization")

_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)


def _redact(record: "Record") -> None:
    extra = record["extra"]
    for key in list(extra):
        if any(marker in key.lower() for marker in _SECRET_KEYS):
            extra[key] = "***"


def setup_logging() -> None:
    settings = get_settings()
    logger.remove()
    logger.configure(patcher=_redact)
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format=_FORMAT,
        backtrace=settings.debug,
        diagnose=False,
        enqueue=True,
    )
