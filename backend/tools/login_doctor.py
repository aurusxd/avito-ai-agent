import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

from app.clients.avito.playwright_auth import (
    LOGIN_BUTTON,
    LOGIN_INPUT,
    OPEN_LOGIN_SCRIPT,
    PASSWORD_INPUT,
    SUBMIT_BUTTON,
    PlaywrightAvitoAuthClient,
    describe,
)
from app.config import get_settings
from app.domain.proxy import mask_proxy_url, proxy_settings

SHOT = Path("data/login-doctor.png")


async def main(proxy_url: str | None) -> None:
    settings = get_settings()
    client = PlaywrightAvitoAuthClient(settings)

    print(f"headless : {settings.avito_headless}")
    print(f"proxy    : {mask_proxy_url(proxy_url) if proxy_url else 'direct'}")
    print(f"base url : {settings.avito_base_url}")
    if settings.avito_headless:
        print("WARNING  : avito detects headless browsers, set AVITO_HEADLESS=false")

    proxy = proxy_settings(proxy_url) if proxy_url else None
    if proxy_url and proxy is None:
        print("FAIL     : proxy url is malformed, expected http://user:pass@host:port")
        return

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=settings.avito_headless,
            args=["--disable-blink-features=AutomationControlled"],
            proxy=proxy,
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="ru-RU",
            timezone_id=settings.timezone,
        )
        page = await context.new_page()

        try:
            await page.goto(
                settings.avito_base_url,
                wait_until="commit",
                timeout=settings.parser_nav_timeout_ms,
            )
        except Exception as error:
            print(f"FAIL     : could not open avito, {describe(error)}")
            await browser.close()
            return

        try:
            await page.wait_for_selector(
                LOGIN_BUTTON, state="visible", timeout=settings.login_wait_ms
            )
        except Exception as error:
            print(f"FAIL     : the page never finished loading, {describe(error)}")
            await page.screenshot(path=str(SHOT))
            await browser.close()
            return

        await page.evaluate(OPEN_LOGIN_SCRIPT, LOGIN_BUTTON)

        try:
            await page.wait_for_selector(
                LOGIN_INPUT, state="visible", timeout=settings.login_wait_ms
            )
        except Exception as error:
            print(f"FAIL     : the login form never opened, {describe(error)}")
            await page.screenshot(path=str(SHOT))
            await browser.close()
            return

        for name, selector in (
            ("login button", LOGIN_BUTTON),
            ("login input", LOGIN_INPUT),
            ("password input", PASSWORD_INPUT),
            ("submit button", SUBMIT_BUTTON),
        ):
            found = await page.query_selector(selector)
            print(f"{name:<14}: {'found' if found else 'MISSING'}")

        probe = await client._probe(page)
        print(f"popup text    : {(probe.get('text') or '')[:200]}")
        print(f"extra inputs  : {probe.get('inputs')}")

        SHOT.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(SHOT))
        print(f"screenshot    : {SHOT}")
        print("OK       : the login form is reachable, no credentials were typed")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
