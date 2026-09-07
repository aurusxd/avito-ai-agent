from typing import cast

from loguru import logger
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    ProxySettings,
    async_playwright,
)

from app.clients.avito.base import LoginStep
from app.clients.avito.browser import explain_launch_failure, launch_args
from app.config import Settings, get_settings
from app.domain.proxy import mask_proxy_url, proxy_settings

LOGGED_OUT_SELECTOR = '[data-marker="header/login-button"]'
PROFILE_MENU = '[data-marker="header/menu-profile"]'


def scrub(message: str, secret: str) -> str:
    cleaned = message.replace(secret, "***") if secret else message
    return " ".join(cleaned.split())


def describe(error: BaseException, secret: str = "", limit: int = 220) -> str:
    return scrub(f"{type(error).__name__}: {error}", secret)[:limit]


class PlaywrightAvitoAuthClient:
    """Opens a browser for a person to sign in by hand and keeps the session.

    Nothing about the sign in is automated: no credentials are typed, no captcha
    is answered, no sms code is read. The operator does all of it over noVNC and
    this client only reports whether the browser ended up signed in.
    """

    provider = "playwright"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def open(self, proxy_url: str | None = None) -> LoginStep:
        requested = proxy_url or self.settings.avito_proxy_server
        proxy = proxy_settings(proxy_url) or proxy_settings(self.settings.avito_proxy_server)
        if requested and proxy is None:
            return LoginStep(
                status="failed",
                hint="proxy url is malformed, expected http://user:pass@host:port",
            )

        logger.info(
            "opening a browser for a manual sign in via {proxy}",
            proxy=mask_proxy_url(requested) if requested else "direct",
        )
        if self.settings.avito_headless:
            logger.warning("AVITO_HEADLESS is true, nobody can sign in without a visible browser")

        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.settings.avito_headless,
                args=launch_args(self.settings),
                proxy=cast("ProxySettings | None", proxy),
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1440, "height": 900},
                locale="ru-RU",
                timezone_id=self.settings.timezone,
            )
            self._page = await self._context.new_page()
        except Exception as error:
            raw = f"{type(error).__name__}: {error}"
            logger.warning("browser did not start: {reason}", reason=raw[:600])
            explained = explain_launch_failure(raw)
            return LoginStep(
                status="failed",
                hint=(
                    f"browser did not start: {explained}"
                    if explained
                    else f"browser did not start, {describe(error, limit=400)}"
                ),
            )

        try:
            await self._page.goto(
                self.settings.avito_base_url,
                wait_until="commit",
                timeout=self.settings.parser_nav_timeout_ms,
            )
        except Exception as error:
            logger.warning("could not open avito: {reason}", reason=describe(error))
            transport = mask_proxy_url(requested) if requested else "direct connection"
            return LoginStep(
                status="failed",
                hint=f"could not open avito over {transport}, {describe(error)}",
            )

        return LoginStep(
            status="waiting_for_operator",
            hint="sign in to avito in the window below, then press the button",
        )

    async def check(self) -> LoginStep:
        page = self._require_page()

        try:
            await page.goto(
                f"{self.settings.avito_base_url.rstrip('/')}/profile",
                wait_until="commit",
                timeout=self.settings.parser_nav_timeout_ms,
            )
        except Exception as error:
            logger.debug("profile check navigation failed: {reason}", reason=describe(error))

        try:
            await page.wait_for_selector(
                f"{PROFILE_MENU}, {LOGGED_OUT_SELECTOR}",
                state="visible",
                timeout=self.settings.login_wait_ms,
            )
        except Exception:
            logger.debug("neither the profile menu nor the login button showed up")

        if await page.query_selector(PROFILE_MENU) is not None:
            return LoginStep(status="saving", hint=None)

        return LoginStep(
            status="waiting_for_operator",
            hint="avito still shows the sign in button, finish the login in the window",
        )

    async def storage_state(self) -> dict[str, object]:
        if self._context is None:
            raise RuntimeError("login session is not started")
        return cast(dict[str, object], await self._context.storage_state())

    async def screenshot(self) -> bytes | None:
        if self._page is None:
            return None
        try:
            return await self._page.screenshot(full_page=False)
        except Exception:
            return None

    async def close(self) -> None:
        for closer in (self._context, self._browser):
            if closer is not None:
                try:
                    await closer.close()
                except Exception:
                    logger.debug("login browser was already closed")
        if self._playwright is not None:
            await self._playwright.stop()
        self._context = None
        self._browser = None
        self._page = None
        self._playwright = None

    def _require_page(self) -> Page:
        if self._page is None:
            raise RuntimeError("login session is not started")
        return self._page
