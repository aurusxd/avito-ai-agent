from typing import TYPE_CHECKING

from app.config import get_settings

if TYPE_CHECKING:
    from app.clients.avito.base import AvitoAuthClient


def get_auth_client() -> "AvitoAuthClient":
    settings = get_settings()
    if settings.auth_client == "playwright":
        from app.clients.avito.playwright_auth import PlaywrightAvitoAuthClient

        return PlaywrightAvitoAuthClient()

    from app.clients.avito.fake_auth import FakeAvitoAuthClient

    return FakeAvitoAuthClient(auto_sign_in=settings.demo_mode)
