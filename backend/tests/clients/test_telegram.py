from datetime import UTC, datetime

import pytest
from aiogram.exceptions import TelegramBadRequest
from pydantic import ValidationError

from app.clients.telegram.aiogram_notifier import AiogramNotifier, build_lead_message
from app.clients.telegram.base import LeadNotification, Notifier, NotifierUnavailableError
from app.clients.telegram.fake import FakeNotifier
from app.config import Settings
from app.domain.schemas import MessageDTO

NOTIFICATION = LeadNotification(
    seller_name="Артём",
    listing_url="https://www.avito.ru/moskva/seed-listing-1",
    conversation_history=[
        MessageDTO(
            role="bot",
            text="Здравствуйте! Баня актуальна?",
            stage=1,
            sent_at=datetime(2026, 9, 6, 9, 0, tzinfo=UTC),
        ),
        MessageDTO(
            role="seller",
            text="Да, интересно",
            sent_at=datetime(2026, 9, 6, 9, 30, tzinfo=UTC),
        ),
    ],
    stage_reached=1,
)


class StubBot:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def send_message(self, **kwargs: object) -> None:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error


def settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "telegram_bot_token": "123:secret-token",
        "telegram_operator_chat_id": "-100500",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_both_notifiers_satisfy_the_protocol() -> None:
    assert isinstance(FakeNotifier(), Notifier)
    assert isinstance(AiogramNotifier(settings()), Notifier)


def test_lead_message_carries_seller_listing_and_history() -> None:
    text = build_lead_message(NOTIFICATION)

    assert "Артём" in text
    assert "https://www.avito.ru/moskva/seed-listing-1" in text
    assert "Здравствуйте! Баня актуальна?" in text
    assert "Да, интересно" in text
    assert "Продавец:" in text


def test_lead_message_escapes_html_in_seller_text() -> None:
    notification = NOTIFICATION.model_copy(
        update={
            "seller_name": "<b>Артём</b>",
            "conversation_history": [
                MessageDTO(
                    role="seller",
                    text="<script>alert(1)</script>",
                    sent_at=datetime(2026, 9, 6, 9, 30, tzinfo=UTC),
                )
            ],
        }
    )

    text = build_lead_message(notification)

    assert "<b>Артём</b>" not in text
    assert "&lt;b&gt;Артём&lt;/b&gt;" in text
    assert "<script>" not in text


async def test_aiogram_notifier_sends_to_the_operator_chat() -> None:
    bot = StubBot()
    notifier = AiogramNotifier(settings(), bot=bot)  # type: ignore[arg-type]

    await notifier.send_lead(NOTIFICATION)

    assert len(bot.calls) == 1
    assert bot.calls[0]["chat_id"] == "-100500"
    assert "Артём" in str(bot.calls[0]["text"])


async def test_missing_token_is_reported_as_unavailable() -> None:
    notifier = AiogramNotifier(settings(telegram_bot_token=""))

    with pytest.raises(NotifierUnavailableError):
        await notifier.send_lead(NOTIFICATION)


async def test_missing_chat_id_is_reported_as_unavailable() -> None:
    notifier = AiogramNotifier(settings(telegram_operator_chat_id=""))

    with pytest.raises(NotifierUnavailableError):
        await notifier.send_lead(NOTIFICATION)


async def test_telegram_error_is_reported_as_unavailable() -> None:
    bot = StubBot(error=TelegramBadRequest(method=None, message="chat not found"))  # type: ignore[arg-type]
    notifier = AiogramNotifier(settings(), bot=bot)  # type: ignore[arg-type]

    with pytest.raises(NotifierUnavailableError) as error:
        await notifier.send_lead(NOTIFICATION)

    assert error.value.provider == "aiogram"


async def test_network_error_is_reported_as_unavailable() -> None:
    bot = StubBot(error=OSError("connection reset"))
    notifier = AiogramNotifier(settings(), bot=bot)  # type: ignore[arg-type]

    with pytest.raises(NotifierUnavailableError):
        await notifier.send_lead(NOTIFICATION)


async def test_token_never_leaks_into_the_error() -> None:
    notifier = AiogramNotifier(settings(telegram_operator_chat_id=""))

    with pytest.raises(NotifierUnavailableError) as error:
        await notifier.send_lead(NOTIFICATION)

    assert "secret-token" not in str(error.value)


async def test_garbage_notification_is_rejected() -> None:
    bot = StubBot()
    notifier = AiogramNotifier(settings(), bot=bot)  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        await notifier.send_lead({"seller_name": "Артём"})  # type: ignore[arg-type]

    assert bot.calls == []


async def test_fake_notifier_rejects_an_empty_history() -> None:
    with pytest.raises(ValidationError):
        await FakeNotifier().send_lead(
            {
                "seller_name": "Артём",
                "listing_url": "https://www.avito.ru/x",
                "conversation_history": [],
                "stage_reached": 1,
            }  # type: ignore[arg-type]
        )
