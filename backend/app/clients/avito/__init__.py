from typing import TYPE_CHECKING

from app.config import get_settings

if TYPE_CHECKING:
    from app.clients.avito.base import AvitoClient


def get_avito_client() -> "AvitoClient":
    if get_settings().avito_client == "playwright":
        from app.clients.avito.playwright_client import PlaywrightAvitoClient

        return PlaywrightAvitoClient()

    from app.clients.avito.fake import FakeAvitoClient

    return FakeAvitoClient()
