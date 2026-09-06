import random
from typing import Any, cast

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
from app.config import Settings, get_settings
from app.domain.proxy import mask_proxy_url, proxy_settings

LOGIN_BUTTON = '[data-marker="header/login-button"]'
AUTH_POPUP = '[data-marker="auth-app/popup"]'
LOGIN_INPUT = '[data-marker="login-form/login/input"]'
PASSWORD_INPUT = '[data-marker="login-form/password/input"]'
SUBMIT_BUTTON = '[data-marker="login-form/submit"]'
PROFILE_MENU = '[data-marker="header/menu-profile"]'

CODE_INPUT_CANDIDATES = (
    '[data-marker="login-form/code/input"]',
    'input[autocomplete="one-time-code"]',
    'input[inputmode="numeric"]',
    'input[name="code"]',
)

CAPTCHA_MARKERS = ("подтвердите, что вы не робот", "captcha", "я не робот")
CREDENTIAL_ERROR_MARKERS = (
    "неверный логин или пароль",
    "неправильный логин или пароль",
    "проверьте логин",
    "неверный пароль",
)
BLOCKED_MARKERS = ("доступ ограничен", "слишком много попыток", "временно заблокирован")

OPEN_LOGIN_SCRIPT = """
(selector) => {
  const button = document.querySelector(selector);
  if (button) button.click();
  return Boolean(button);
}
"""


class PlaywrightAvitoAuthClient:
    provider = "playwright"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def start(self, login: str, password: str, proxy_url: str | None = None) -> LoginStep:
        proxy = proxy_settings(proxy_url) or proxy_settings(self.settings.avito_proxy_server)
        logger.info(
            "login attempt for {login} via {proxy}",
            login=login,
            proxy=mask_proxy_url(proxy_url) if proxy_url else "direct",
        )

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.settings.avito_headless,
            args=["--disable-blink-features=AutomationControlled"],
            proxy=cast("ProxySettings | None", proxy),
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="ru-RU",
            timezone_id=self.settings.timezone,
        )
        self._page = await self._context.new_page()
        page = self._page

        await page.goto(
            self.settings.avito_base_url,
            wait_until="domcontentloaded",
            timeout=self.settings.parser_nav_timeout_ms,
        )

        try:
            await page.wait_for_selector(
                LOGIN_BUTTON, state="visible", timeout=self.settings.login_wait_ms
            )
        except Exception:
            if await page.query_selector(PROFILE_MENU) is not None:
                return LoginStep(status="saving", hint="already signed in")
            return await self._classify("avito did not show the login form")

        await page.evaluate(OPEN_LOGIN_SCRIPT, LOGIN_BUTTON)

        try:
            await page.wait_for_selector(
                LOGIN_INPUT, state="visible", timeout=self.settings.login_wait_ms
            )
        except Exception:
            return await self._classify("the login form never opened")

        await self._type(page, LOGIN_INPUT, login)
        await self._type(page, PASSWORD_INPUT, password)
        await page.click(SUBMIT_BUTTON)
        await page.wait_for_timeout(self.settings.login_settle_ms)

        return await self._classify("avito rejected the sign in")

    async def submit_code(self, code: str) -> LoginStep:
        page = self._require_page()

        field = await self._code_field(page)
        if field is None:
            return await self._classify("the code field disappeared")

        await field.fill("")
        await field.press_sequentially(code, delay=random.uniform(60, 140))
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(self.settings.login_settle_ms)

        return await self._classify("avito did not accept the code")

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

    async def _type(self, page: Page, selector: str, value: str) -> None:
        field = page.locator(selector)
        await field.click()
        await field.fill("")
        await field.press_sequentially(
            value,
            delay=random.uniform(
                self.settings.outreach_type_delay_min_ms,
                max(
                    self.settings.outreach_type_delay_min_ms,
                    self.settings.outreach_type_delay_max_ms,
                ),
            ),
        )

    async def _code_field(self, page: Page) -> Any:
        for selector in CODE_INPUT_CANDIDATES:
            field = await page.query_selector(selector)
            if field is not None and await field.is_visible():
                logger.debug("code field matched {selector}", selector=selector)
                return field
        return None

    async def _classify(self, failure_hint: str) -> LoginStep:
        page = self._require_page()
        text = (await page.content()).lower()

        if any(marker in text for marker in CAPTCHA_MARKERS):
            return LoginStep(
                status="captcha_required",
                hint="avito asks for a captcha, a human has to finish this step",
            )

        if await page.query_selector(PROFILE_MENU) is not None:
            return LoginStep(status="saving", hint=None)

        if await self._code_field(page) is not None:
            return LoginStep(status="code_required", hint="enter the code avito sent by sms")

        if any(marker in text for marker in CREDENTIAL_ERROR_MARKERS):
            return LoginStep(status="failed", hint="avito rejected the login or password")

        if any(marker in text for marker in BLOCKED_MARKERS):
            return LoginStep(status="failed", hint="avito blocked this sign in attempt")

        if await page.query_selector(LOGIN_BUTTON) is None:
            return LoginStep(status="saving", hint=None)

        return LoginStep(status="failed", hint=failure_hint)
