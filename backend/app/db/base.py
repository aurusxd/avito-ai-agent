from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import BACKEND_ROOT, get_settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir(url: str) -> None:
    marker = ":///"
    if not url.startswith("sqlite") or marker not in url:
        return
    raw_path = url.split(marker, 1)[1]
    if not raw_path or raw_path == ":memory:":
        return
    path = Path(raw_path)
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)


def build_engine(url: str | None = None):
    resolved = url or get_settings().database_url
    _ensure_sqlite_dir(resolved)
    return create_async_engine(resolved, echo=False, future=True)


engine = build_engine()
session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
