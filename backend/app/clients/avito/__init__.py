from typing import TYPE_CHECKING

from app.config import get_settings

if TYPE_CHECKING:
    from app.clients.avito.base import AvitoClient


def get_avito_client() -> "AvitoClient":
    settings = get_settings()
    if settings.avito_client == "playwright":
        from app.clients.avito.playwright_client import PlaywrightAvitoClient

        return PlaywrightAvitoClient()

    from app.clients.avito.fake import FakeAvitoClient

    if settings.demo_mode:
        # the showcase parser and inbox return believable, real-looking data
        from app.db.demo_seed import DEMO_INCOMING_REPLIES, DEMO_PARSER_RESULTS

        return FakeAvitoClient(results=DEMO_PARSER_RESULTS, replies=DEMO_INCOMING_REPLIES)

    return FakeAvitoClient()
