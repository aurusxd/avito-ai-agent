import pytest

from app.clients.avito.base import AvitoBlockedError
from app.clients.avito.playwright_client import (
    LOGGED_OUT_SELECTOR,
    VPN_CHECK_SELECTOR,
    PlaywrightAvitoClient,
)
from app.domain.schemas import SellerDTO


class StubPage:
    def __init__(self, title: str = "", body: str = "", present: set[str] | None = None) -> None:
        self._title = title
        self._body = body
        self._present = present or set()

    async def title(self) -> str:
        return self._title

    async def inner_text(self, selector: str) -> str:
        return self._body

    async def query_selector(self, selector: str) -> object | None:
        return object() if selector in self._present else None


def detect(page: StubPage, status: int | None = None):
    client = PlaywrightAvitoClient()
    return client._detect_block(page, status)  # type: ignore[arg-type]


async def test_clean_page_is_not_a_block() -> None:
    page = StubPage(title="Баня под ключ (123)", body="Перевозная мобильная баня")

    assert await detect(page) is None


@pytest.mark.parametrize(
    ("status", "expected"),
    [(429, "rate_limited"), (403, "forbidden"), (200, None), (None, None)],
)
async def test_http_status_maps_to_block_kind(status: int | None, expected: str | None) -> None:
    assert await detect(StubPage(title="ok", body="ok"), status) == expected


async def test_vpn_interstitial_is_detected_by_marker() -> None:
    page = StubPage(title="Авито", body="", present={VPN_CHECK_SELECTOR})

    assert await detect(page) == "forbidden"


async def test_vpn_interstitial_is_detected_by_text() -> None:
    page = StubPage(title="Авито", body="Возможно, у вас включён VPN. Пожалуйста, отключите его.")

    assert await detect(page) == "forbidden"


async def test_captcha_page_is_detected() -> None:
    page = StubPage(title="Авито", body="Подтвердите, что вы не робот")

    assert await detect(page) == "captcha"


async def test_access_denied_page_is_forbidden() -> None:
    page = StubPage(title="Доступ ограничен", body="проблема с IP")

    assert await detect(page) == "forbidden"


async def test_captcha_wins_over_forbidden_when_both_present() -> None:
    page = StubPage(title="Доступ ограничен", body="Подтвердите, что вы не робот")

    assert await detect(page) == "captcha"


SELLER = SellerDTO(
    avito_seller_id="seed-seller-1",
    name="Артём",
    profile_url="https://www.avito.ru/brands/seed-seller-1",
    listings_count=4,
    region="Москва",
)


async def test_login_button_means_the_session_expired() -> None:
    page = StubPage(present={LOGGED_OUT_SELECTOR})
    client = PlaywrightAvitoClient()

    with pytest.raises(AvitoBlockedError) as raised:
        await client._require_session(page, SELLER)  # type: ignore[arg-type]

    assert raised.value.block_kind == "auth_required"


async def test_logged_in_page_passes_the_session_check() -> None:
    client = PlaywrightAvitoClient()

    await client._require_session(StubPage(), SELLER)  # type: ignore[arg-type]
