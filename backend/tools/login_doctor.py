import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

from app.clients.avito.browser import explain_launch_failure, launch_args
from app.clients.avito.playwright_auth import (
    LOGGED_OUT_SELECTOR,
    PROFILE_MENU,
    describe,
)
from app.config import get_settings
from app.domain.proxy import mask_proxy_url, proxy_settings

SHOT = Path("data/login-doctor.png")
IP_ECHO = "https://api.ipify.org?format=json"
BLOCK_MARKERS = ("доступ ограничен", "проблема с ip", "слишком много запросов")


async def main(proxy_url: str | None) -> None:
    settings = get_settings()

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
        try:
            browser = await playwright.chromium.launch(
                headless=settings.avito_headless,
                args=launch_args(settings),
                proxy=proxy,
            )
        except Exception as error:
            raw = f"{type(error).__name__}: {error}"
            print(f"FAIL     : {explain_launch_failure(raw) or describe(error, limit=400)}")
            return

        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="ru-RU",
            timezone_id=settings.timezone,
        )
        page = await context.new_page()

        try:
            await page.goto(IP_ECHO, wait_until="commit", timeout=60_000)
            print(f"exit ip  : {(await page.inner_text('body')).strip()[:60]}")
        except Exception as error:
            print(f"exit ip  : unavailable, {describe(error)}")

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
                f"{PROFILE_MENU}, {LOGGED_OUT_SELECTOR}",
                state="visible",
                timeout=settings.login_wait_ms,
            )
        except Exception:
            print("WARNING  : neither the profile menu nor the login button appeared")

        body = (await page.inner_text("body")).lower()
        blocked = [marker for marker in BLOCK_MARKERS if marker in body]

        print(f"title    : {await page.title()}")
        print(f"signed in: {await page.query_selector(PROFILE_MENU) is not None}")
        print(f"blocked  : {blocked or 'no'}")

        SHOT.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(SHOT))
        print(f"screenshot: {SHOT}")

        if not blocked and await page.query_selector(LOGGED_OUT_SELECTOR) is not None:
            print("OK       : avito opened over this transport, ready for a manual sign in")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
