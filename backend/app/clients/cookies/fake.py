from datetime import UTC, datetime

from app.clients.cookies.base import CookieBundle

FAKE_COOKIES = {"srv_id": "fake-srv-id", "ft": "fake-ft", "pow_solved": "1"}
FAKE_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 13; SM-A528B) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
)


class FakeCookieProvider:
    """Сид-набор без сети. Считает вызовы, чтобы тесты видели покупки и разблокировки."""

    def __init__(self, *, refreshable: bool = True) -> None:
        self.refreshable = refreshable
        self.purchases = 0
        self.refreshes = 0
        self._bundle: CookieBundle | None = None

    async def get(self) -> CookieBundle:
        if self._bundle is None:
            self.purchases += 1
            self._bundle = CookieBundle(
                id=self.purchases,
                cookies=dict(FAKE_COOKIES),
                user_agent=FAKE_USER_AGENT,
                impersonate="chrome131_android",
                headers={"user-agent": FAKE_USER_AGENT},
                mobile=True,
                obtained_at=datetime.now(UTC),
            )
        return self._bundle

    async def refresh(self) -> CookieBundle | None:
        if self._bundle is None or not self.refreshable:
            return None
        self.refreshes += 1
        self._bundle = self._bundle.model_copy(
            update={"cookies": {**self._bundle.cookies, "srv_id": f"refreshed-{self.refreshes}"}}
        )
        return self._bundle

    async def invalidate(self) -> None:
        self._bundle = None
