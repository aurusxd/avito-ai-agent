from app.clients.avito.base import LoginStep

BROKEN_PROXY = "http://broken"


class FakeAvitoAuthClient:
    provider = "fake"

    def __init__(self, signs_in_after: int = 1) -> None:
        # how many checks it takes before the fake operator is signed in
        self.signs_in_after = signs_in_after
        self.checks = 0
        self.proxy_url: str | None = None
        self.opened = False
        self.closed = False

    async def open(self, proxy_url: str | None = None) -> LoginStep:
        self.proxy_url = proxy_url
        if proxy_url == BROKEN_PROXY:
            return LoginStep(status="failed", hint="could not open avito over the proxy")
        self.opened = True
        return LoginStep(
            status="waiting_for_operator",
            hint="sign in to avito in the window below, then press the button",
        )

    async def check(self) -> LoginStep:
        self.checks += 1
        if self.checks < self.signs_in_after:
            return LoginStep(
                status="waiting_for_operator",
                hint="avito still shows the sign in button, finish the login in the window",
            )
        return LoginStep(status="saving", hint=None)

    async def storage_state(self) -> dict[str, object]:
        return {
            "cookies": [{"name": "sessid", "value": "fake", "domain": ".avito.ru"}],
            "origins": [],
        }

    async def screenshot(self) -> bytes | None:
        return b"fake-png"

    async def close(self) -> None:
        self.closed = True
