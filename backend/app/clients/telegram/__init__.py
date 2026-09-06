from typing import TYPE_CHECKING

from app.config import get_settings

if TYPE_CHECKING:
    from app.clients.telegram.base import Notifier


def get_notifier() -> "Notifier":
    if get_settings().telegram_client == "aiogram":
        from app.clients.telegram.aiogram_notifier import AiogramNotifier

        return AiogramNotifier()

    from app.clients.telegram.fake import FakeNotifier

    return FakeNotifier()
