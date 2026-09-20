from datetime import UTC, datetime

from app.clients.cookies.base import CookieBundle


class NoCookieProvider:
    """Ходим без прогретой сессии.

    Это путь отката и режим для тестов: Авито в таком виде отдаёт 403 (§27.1),
    но клиент должен уметь работать и без провайдера.
    """

    async def get(self) -> CookieBundle:
        return CookieBundle(obtained_at=datetime.now(UTC))

    async def purchase(self) -> CookieBundle:
        return await self.get()

    async def refresh(self) -> CookieBundle | None:
        return None

    async def invalidate(self) -> None:
        return None
