from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class CookieProviderError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class CookieBudgetExhaustedError(CookieProviderError):
    """Дневной потолок покупок исчерпан (§27.8): дальше не покупаем, а останавливаемся."""


class CookieBundle(BaseModel):
    """Прогретая анонимная сессия Авито под конкретный ip (§27.5).

    Это сессия незалогиненного посетителя: она годится только для парсинга и
    никогда не подмешивается к сессии аккаунта (§27.11).
    """

    id: int | None = None
    cookies: dict[str, str] = Field(default_factory=dict)
    user_agent: str = ""
    impersonate: str = "chrome"
    headers: dict[str, str] = Field(default_factory=dict)
    mobile: bool = False
    obtained_at: datetime
    # proxy_url carries credentials, so it never goes to a log or a list response
    proxy_url: str | None = None

    @property
    def empty(self) -> bool:
        return not self.cookies


@runtime_checkable
class CookieProvider(Protocol):
    async def get(self) -> CookieBundle: ...

    async def refresh(self) -> CookieBundle | None: ...

    async def invalidate(self) -> None: ...
