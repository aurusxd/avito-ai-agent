from datetime import UTC, datetime
from typing import Any

import pytest

from app.clients.avito.api_url import AvitoApiUrlError
from app.clients.avito.base import (
    AvitoAccountRef,
    AvitoBlockedError,
    IncomingReplyDTO,
    SendResult,
)
from app.clients.avito.http_client import HttpAvitoClient
from app.clients.cookies.base import (
    CookieBudgetExhaustedError,
    CookieBundle,
    CookieProviderError,
)
from app.clients.cookies.fake import FakeCookieProvider
from app.config import Settings
from app.domain.schemas import CategoryDTO, SellerDTO
from tests.clients.test_avito_api_parsing import item

API_URL = "https://www.avito.ru/web/1/js/items?categoryId=19"

CATEGORY = CategoryDTO(
    id=1,
    name="Бани",
    avito_url_or_slug="all/remont_i_stroitelstvo/banya-ASgBAgICAkRYlrI68I4O2o_OAQ",
    region="Россия",
    min_listings_per_seller=3,
)


def page(*items: dict[str, Any]) -> dict[str, Any]:
    return {"catalog": {"items": list(items)}}


class StubResolver:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def resolve(self, category_url: str) -> str:
        self.calls.append(category_url)
        return API_URL


class StubFallback:
    """Отправка и чтение ответов остаются в браузере (§27.11)."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.fetched: list[int] = []

    async def parse_category(self, category: CategoryDTO) -> list[Any]:
        raise AssertionError("http transport must not fall back for parsing")

    async def send_message(
        self, account: AvitoAccountRef, seller: SellerDTO, text: str
    ) -> SendResult:
        self.sent.append(text)
        return SendResult(status="sent", sent_at=datetime.now(UTC))

    async def fetch_replies(
        self, account: AvitoAccountRef, limit: int = 50
    ) -> list[IncomingReplyDTO]:
        self.fetched.append(limit)
        return []


class BrokeProvider:
    """Потолок расходов исчерпан: покупать больше нельзя (§27.8)."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    async def get(self) -> CookieBundle:
        raise self.error

    async def refresh(self) -> CookieBundle | None:
        return None

    async def invalidate(self) -> None:
        return None


class ScriptedClient(HttpAvitoClient):
    def __init__(self, script: list[tuple[int, object]], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.script = script
        self.requests: list[str] = []

    async def _get(self, url: str, bundle: CookieBundle) -> tuple[int, object]:
        self.requests.append(url)
        return self.script.pop(0) if len(self.script) > 1 else self.script[0]


def build(
    script: list[tuple[int, object]],
    *,
    cookies: Any = None,
    fallback: StubFallback | None = None,
    max_pages: int = 2,
    max_sellers: int = 0,
) -> ScriptedClient:
    settings = Settings(
        avito_base_url="https://www.avito.ru",
        parser_max_pages=max_pages,
        parser_max_sellers_per_run=max_sellers,
        parser_delay_min_seconds=0.0,
        parser_delay_max_seconds=0.0,
    )
    return ScriptedClient(
        script,
        settings=settings,
        cookies=cookies or FakeCookieProvider(),
        resolver=StubResolver(),  # type: ignore[arg-type]
        fallback=fallback or StubFallback(),  # type: ignore[arg-type]
    )


async def test_parse_category_walks_pages_and_groups_sellers() -> None:
    client = build(
        [
            (200, page(item(1), item(2))),
            (200, page(item(3, seller_link="/user/abc/profile", seller_title="Алексей"))),
        ]
    )

    results = await client.parse_category(CATEGORY)

    assert {row.seller.avito_seller_id for row in results} == {"i302005374", "abc"}
    assert client.requests[1].endswith("&page=2")


async def test_parse_category_stops_on_an_empty_page() -> None:
    client = build([(200, page(item(1))), (200, page())], max_pages=2)

    results = await client.parse_category(CATEGORY)

    assert len(results) == 1
    assert len(client.requests) == 2


async def test_parse_category_respects_the_seller_limit() -> None:
    client = build(
        [
            (
                200,
                page(
                    item(1),
                    item(2, seller_link="/user/abc/profile", seller_title="Алексей"),
                ),
            )
        ],
        max_pages=1,
        max_sellers=1,
    )

    assert len(await client.parse_category(CATEGORY)) == 1


async def test_a_block_is_retried_after_a_free_unblock() -> None:
    cookies = FakeCookieProvider()
    client = build([(403, None), (200, page(item(1)))], cookies=cookies, max_pages=1)

    results = await client.parse_category(CATEGORY)

    assert len(results) == 1
    assert cookies.refreshes == 1
    # разблокировка бесплатна и помогла, поэтому покупки не было (§27.9)
    assert cookies.purchases == 1


async def test_a_block_buys_new_cookies_when_unblock_fails() -> None:
    cookies = FakeCookieProvider(refreshable=False)
    client = build([(403, None), (200, page(item(1)))], cookies=cookies, max_pages=1)

    results = await client.parse_category(CATEGORY)

    assert len(results) == 1
    assert cookies.purchases == 2


@pytest.mark.parametrize(
    ("status", "expected"), [(403, "forbidden"), (429, "rate_limited"), (439, "forbidden")]
)
async def test_a_permanent_block_is_reported(status: int, expected: str) -> None:
    client = build([(status, None)], cookies=FakeCookieProvider(refreshable=False), max_pages=1)

    with pytest.raises(AvitoBlockedError) as error:
        await client.parse_category(CATEGORY)

    assert error.value.block_kind == expected


async def test_an_exhausted_budget_is_a_block_not_a_crash() -> None:
    client = build(
        [(200, page(item(1)))],
        cookies=BrokeProvider(CookieBudgetExhaustedError("spfa daily cap reached")),
        max_pages=1,
    )

    with pytest.raises(AvitoBlockedError, match="daily cap"):
        await client.parse_category(CATEGORY)


async def test_a_broken_provider_is_a_block_not_a_crash() -> None:
    client = build(
        [(200, page(item(1)))],
        cookies=BrokeProvider(CookieProviderError("SPFA_API_KEY is not set")),
        max_pages=1,
    )

    with pytest.raises(AvitoBlockedError) as error:
        await client.parse_category(CATEGORY)

    assert error.value.block_kind == "unavailable"


async def test_sending_and_reading_go_to_the_browser() -> None:
    fallback = StubFallback()
    client = build([(200, page())], fallback=fallback, max_pages=1)
    account = AvitoAccountRef(id=1, login="demo", session_storage_path="data/demo.json")
    seller = SellerDTO(
        avito_seller_id="i302005374",
        name="СтройБлок",
        profile_url="https://www.avito.ru/brands/i302005374",
        listings_count=3,
        region="Россия",
    )

    result = await client.send_message(account, seller, "привет")
    await client.fetch_replies(account, 7)

    assert result.status == "sent"
    assert fallback.sent == ["привет"]
    assert fallback.fetched == [7]


class DeadResolver:
    async def resolve(self, category_url: str) -> str:
        raise AvitoApiUrlError("api url conversion returned 502", 502)


async def test_a_dead_url_converter_is_a_block_not_a_crash() -> None:
    # §26.2: оператор должен увидеть закрытый транспорт, а не 500
    client = build([(200, page(item(1)))], max_pages=1)
    client.resolver = DeadResolver()  # type: ignore[assignment]

    with pytest.raises(AvitoBlockedError) as error:
        await client.parse_category(CATEGORY)

    assert error.value.block_kind == "unavailable"
    assert "502" in str(error.value)
