from typing import TYPE_CHECKING

from app.config import get_settings

if TYPE_CHECKING:
    from app.clients.cookies.base import CookieProvider


def get_cookie_provider() -> "CookieProvider":
    provider = get_settings().cookie_provider

    if provider == "spfa":
        from app.clients.cookies.spfa import SpfaCookieProvider

        return SpfaCookieProvider()

    if provider == "fake":
        from app.clients.cookies.fake import FakeCookieProvider

        return FakeCookieProvider()

    from app.clients.cookies.none import NoCookieProvider

    return NoCookieProvider()
