from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.clients.ai.base import AIAnalysisRequest, AIClient, AIVariationRequest
from app.clients.ai.fake import FakeAIClient
from app.clients.avito.base import AvitoAccountRef, AvitoClient
from app.clients.avito.fake import FakeAvitoClient
from app.clients.telegram.base import LeadNotification, Notifier
from app.clients.telegram.fake import FakeNotifier
from app.db.seed import SEED_PARSER_RESULTS
from app.domain.schemas import CategoryDTO, MessageDTO, SellerDTO

CATEGORY = CategoryDTO(
    id=1,
    name="Бани",
    avito_url_or_slug="rossiya/bani",
    region="Россия",
    min_listings_per_seller=3,
)

ACCOUNT = AvitoAccountRef(id=1, login="demo", session_storage_path="data/demo.storage.json")


def test_fakes_satisfy_protocols() -> None:
    assert isinstance(FakeAIClient(), AIClient)
    assert isinstance(FakeAvitoClient(), AvitoClient)
    assert isinstance(FakeNotifier(), Notifier)


async def test_fake_ai_rewrite_fills_placeholders() -> None:
    client = FakeAIClient()

    response = await client.rewrite(
        AIVariationRequest(
            template_text="{name}, ваш «{product}» в «{category}»?",
            seller_name="Артём",
            product="баня-бочка",
            category="Бани",
        )
    )

    assert response.unique_text == "Артём, ваш «баня-бочка» в «Бани»?"


async def test_fake_ai_rejects_garbage_payload() -> None:
    client = FakeAIClient()

    with pytest.raises(ValidationError):
        await client.rewrite({"template_text": "", "seller_name": 1})  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        await client.analyze_reply({"reply_text": ""})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("Да, интересно, расскажите", "interested"),
        ("Нет, не пишите мне", "negative"),
        ("Здравствуйте", "neutral"),
    ],
)
async def test_fake_ai_analyzes_sentiment(reply: str, expected: str) -> None:
    client = FakeAIClient()

    response = await client.analyze_reply(AIAnalysisRequest(reply_text=reply))

    assert response.sentiment == expected
    assert 0.0 <= response.confidence <= 1.0


async def test_fake_ai_error_path_recovers_after_retry() -> None:
    client = FakeAIClient(failure=TimeoutError("upstream timeout"), fail_times=1)
    request = AIAnalysisRequest(reply_text="Да, интересно")

    with pytest.raises(TimeoutError):
        await client.analyze_reply(request)

    assert (await client.analyze_reply(request)).sentiment == "interested"


async def test_fake_avito_returns_seed_data_filtered_by_min_listings() -> None:
    client = FakeAvitoClient()

    results = await client.parse_category(CATEGORY)

    assert len(results) == 2
    assert all(result.seller.listings_count >= 3 for result in results)
    assert {result.seller.avito_seller_id for result in results} < {
        result.seller.avito_seller_id for result in SEED_PARSER_RESULTS
    }


async def test_fake_avito_rejects_garbage_category() -> None:
    client = FakeAvitoClient()

    with pytest.raises(ValidationError):
        await client.parse_category({"name": "Бани"})  # type: ignore[arg-type]


async def test_fake_avito_send_message_reports_failure() -> None:
    seller = SEED_PARSER_RESULTS[0].seller
    client = FakeAvitoClient(failure=RuntimeError("http 500"), fail_times=1)

    failed = await client.send_message(ACCOUNT, seller, "привет")
    assert failed.status == "failed"
    assert failed.error == "http 500"
    assert client.sent == []

    sent = await client.send_message(ACCOUNT, seller, "привет")
    assert sent.status == "sent"
    assert client.sent == [(1, seller.avito_seller_id, "привет")]


async def test_fake_avito_rejects_empty_message() -> None:
    client = FakeAvitoClient()

    with pytest.raises(ValueError):
        await client.send_message(ACCOUNT, SEED_PARSER_RESULTS[0].seller, "   ")


async def test_fake_notifier_accepts_valid_lead() -> None:
    notifier = FakeNotifier()
    notification = LeadNotification(
        seller_name="Артём",
        listing_url="https://www.avito.ru/moskva/seed-listing-1",
        conversation_history=[
            MessageDTO(role="bot", text="Здравствуйте", stage=1, sent_at=datetime.now(UTC)),
            MessageDTO(role="seller", text="Да, интересно", sent_at=datetime.now(UTC)),
        ],
        stage_reached=1,
    )

    await notifier.send_lead(notification)

    assert notifier.sent == [notification]


async def test_fake_notifier_rejects_empty_history() -> None:
    notifier = FakeNotifier()

    with pytest.raises(ValidationError):
        await notifier.send_lead(
            {
                "seller_name": "Артём",
                "listing_url": "https://www.avito.ru/x",
                "conversation_history": [],
                "stage_reached": 1,
            }  # type: ignore[arg-type]
        )


def test_seller_dto_rejects_negative_listings_count() -> None:
    with pytest.raises(ValidationError):
        SellerDTO(
            avito_seller_id="x",
            name="x",
            profile_url="https://x",
            listings_count=-1,
            region="x",
        )
