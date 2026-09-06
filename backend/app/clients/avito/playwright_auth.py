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

CODE_MARKERS = ("код", "sms", "смс", "one-time", "подтверждени")

PROBE_SCRIPT = """
(selectors) => {
  const popup = document.querySelector(selectors.popup) || document.body;
  const known = [
    ...document.querySelectorAll(selectors.login),
    ...document.querySelectorAll(selectors.password),
  ];
  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const inputs = [...popup.querySelectorAll('input')]
    .filter((el) => visible(el) && !known.includes(el) && el.type !== 'checkbox')
    .map((el) => ({
      marker: el.getAttribute('data-marker'),
      name: el.getAttribute('name'),
      type: el.getAttribute('type'),
      inputmode: el.getAttribute('inputmode'),
      autocomplete: el.getAttribute('autocomplete'),
      maxlength: el.getAttribute('maxlength'),
    }));
  return {
    text: (popup.innerText || '').trim().slice(0, 400),
    inputs,
    passwordVisible: [...document.querySelectorAll(selectors.password)].some(visible),
    submitVisible: [...document.querySelectorAll(selectors.submit)].some(visible),
  };
}
"""

CAPTCHA_MARKERS = ("подтвердите, что вы не робот", "captcha", "я не робот")
CREDENTIAL_ERROR_MARKERS = (
    "неверный логин или пароль",
    "неправильный логин или пароль",
    "проверьте логин",
    "неверный пароль",
)
BLOCKED_MARKERS = ("доступ ограничен", "слишком много попыток", "временно заблокирован")


def scrub(message: str, secret: str) -> str:
    cleaned = message.replace(secret, "***") if secret else message
    return " ".join(cleaned.split())


def describe(error: BaseException, secret: str = "", limit: int = 220) -> str:
    text = scrub(f"{type(error).__name__}: {error}", secret)
    return text[:limit]


def _short(value: str, limit: int = 160) -> str:
    collapsed = " ".join(value.split())
    return collapsed[:limit] if collapsed else "empty popup"


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
        requested = proxy_url or self.settings.avito_proxy_server
        proxy = proxy_settings(proxy_url) or proxy_settings(self.settings.avito_proxy_server)
        if requested and proxy is None:
            return LoginStep(
                status="failed",
                hint="proxy url is malformed, expected http://user:pass@host:port",
            )

        logger.info(
            "login attempt for {login} via {proxy}",
            login=login,
            proxy=mask_proxy_url(requested) if requested else "direct",
        )
        if self.settings.avito_headless:
            logger.warning(
                "AVITO_HEADLESS is true, avito detects headless browsers and will block the login"
            )

        try:
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
        except Exception as error:
            logger.warning("browser did not start: {reason}", reason=describe(error))
            return LoginStep(
                status="failed", hint=f"browser did not start, {describe(error, password)}"
            )

        page = self._page

        try:
            await page.goto(
                self.settings.avito_base_url,
                wait_until="commit",
                timeout=self.settings.parser_nav_timeout_ms,
            )
        except Exception as error:
            logger.warning("login navigation failed: {reason}", reason=describe(error))
            transport = mask_proxy_url(requested) if requested else "direct connection"
            return LoginStep(
                status="failed",
                hint=f"could not open avito over {transport}, {describe(error, password)}",
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

        try:
            await self._type(page, LOGIN_INPUT, login)
            await self._type(page, PASSWORD_INPUT, password)
            await self._submit(page)
        except Exception as error:
            logger.warning("filling the login form failed: {reason}", reason=describe(error))
            return LoginStep(
                status="failed",
                hint=f"could not fill the login form, {describe(error, password)}",
            )

        await page.wait_for_timeout(self.settings.login_settle_ms)

        return await self._classify("avito rejected the sign in")

    async def _submit(self, page: Page) -> None:
        try:
            await page.click(SUBMIT_BUTTON, timeout=self.settings.login_wait_ms)
        except Exception as error:
            logger.debug(
                "submit click intercepted, falling back to js: {reason}", reason=describe(error)
            )
            await page.evaluate(OPEN_LOGIN_SCRIPT, SUBMIT_BUTTON)

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
        await field.wait_for(state="visible", timeout=self.settings.login_wait_ms)
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

    async def _probe(self, page: Page) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await page.evaluate(
                PROBE_SCRIPT,
                {
                    "popup": AUTH_POPUP,
                    "login": LOGIN_INPUT,
                    "password": PASSWORD_INPUT,
                    "submit": SUBMIT_BUTTON,
                },
            ),
        )

    def _code_selector(self, probe: dict[str, Any]) -> str | None:
        text = str(probe.get("text", "")).lower()
        mentions_code = any(marker in text for marker in CODE_MARKERS)

        for field in probe.get("inputs", []):
            marker = field.get("marker") or ""
            if "code" in marker:
                return f'[data-marker="{marker}"]'
            if field.get("autocomplete") == "one-time-code":
                return 'input[autocomplete="one-time-code"]'
            if field.get("name") == "code":
                return 'input[name="code"]'

        if not mentions_code:
            return None

        for field in probe.get("inputs", []):
            if field.get("name"):
                return f'input[name="{field["name"]}"]'
            if field.get("marker"):
                return f'[data-marker="{field["marker"]}"]'
        return None

    async def _code_field(self, page: Page) -> Any:
        selector = self._code_selector(await self._probe(page))
        if selector is None:
            return None
        field = await page.query_selector(selector)
        if field is None or not await field.is_visible():
            return None
        logger.debug("code field matched {selector}", selector=selector)
        return field

    async def _classify(self, failure_hint: str) -> LoginStep:
        page = self._require_page()
        text = (await page.content()).lower()
        probe = await self._probe(page)
        popup_text = str(probe.get("text", ""))

        logger.debug(
            "login probe: submit={submit} password={password} inputs={inputs}",
            submit=probe.get("submitVisible"),
            password=probe.get("passwordVisible"),
            inputs=probe.get("inputs"),
        )

        if any(marker in text for marker in CAPTCHA_MARKERS):
            return LoginStep(
                status="captcha_required",
                hint="avito asks for a captcha, a human has to finish this step",
            )

        if await page.query_selector(PROFILE_MENU) is not None:
            return LoginStep(status="saving", hint=None)

        lowered_popup = popup_text.lower()
        if any(marker in lowered_popup for marker in CREDENTIAL_ERROR_MARKERS) or any(
            marker in text for marker in CREDENTIAL_ERROR_MARKERS
        ):
            return LoginStep(status="failed", hint="avito rejected the login or password")

        if any(marker in text for marker in BLOCKED_MARKERS):
            return LoginStep(status="failed", hint="avito blocked this sign in attempt")

        if probe.get("passwordVisible") or probe.get("submitVisible"):
            return LoginStep(
                status="failed",
                hint=f"still on the login form, avito shows: {_short(popup_text)}",
            )

        if self._code_selector(probe) is not None:
            return LoginStep(status="code_required", hint="enter the code avito sent by sms")

        if await page.query_selector(LOGIN_BUTTON) is None:
            return LoginStep(status="saving", hint=None)

        return LoginStep(
            status="failed",
            hint=f"{failure_hint}: {_short(popup_text)}" if popup_text else failure_hint,
        )
