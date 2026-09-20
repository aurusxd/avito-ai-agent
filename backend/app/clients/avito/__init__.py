from typing import TYPE_CHECKING

from app.config import get_settings

if TYPE_CHECKING:
    from app.clients.avito.base import AvitoClient


def get_avito_client() -> "AvitoClient":
    settings = get_settings()

    if settings.avito_client == "playwright":
        from app.clients.avito.playwright_client import PlaywrightAvitoClient

        browser = PlaywrightAvitoClient()
        if settings.avito_parser_transport == "browser":
            return browser

        # §27: парсинг уходит на http, отправка и чтение ответов остаются в браузере
        from app.clients.avito.http_client import HttpAvitoClient

        return HttpAvitoClient(settings=settings, fallback=browser)

    from app.clients.avito.fake import FakeAvitoClient

    return FakeAvitoClient()
