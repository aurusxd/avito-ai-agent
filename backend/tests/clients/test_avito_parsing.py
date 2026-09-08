import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.clients.avito.playwright_client import (
    PlaywrightAvitoClient,
    absolute_listing_url,
    build_category_url,
    card_to_listing,
    extract_seller_key,
    group_cards_by_seller,
    parse_active_count,
    parse_listings_count,
    parse_price,
    parse_region,
    parse_seller_name,
    strip_profile_title_suffix,
)
from app.config import get_settings

BASE = "https://www.avito.ru"

BANI_SLUG = "all/remont_i_stroitelstvo/gotovye_stroeniya_i_sruby/banya-ASgBAgICAkRYlrI68I4O2o_OAQ"

CARD = {
    "itemId": "7816571444",
    "title": "Перевозная мобильная баня 5,9х4,8 м под ключ",
    "href": "/moskva/predlozheniya_uslug/perevoznaya_mobilnaya_banya_7816571444?context=H4sIAAAA",
    "price": "641000",
    "location": "Москва",
    "sellerHref": "/brands/c73f82caea9710b718c6f9d9c3d23262?src=search_seller_info&iid=7816571444",
}


def test_build_category_url_from_slug() -> None:
    assert build_category_url(BASE, BANI_SLUG) == f"{BASE}/{BANI_SLUG}"


def test_build_category_url_adds_page_and_keeps_query() -> None:
    slug = "all/doma_dachi_kottedzhi?q=%D0%B4%D0%BE%D0%BC"

    assert (
        build_category_url(BASE, slug, 3)
        == f"{BASE}/all/doma_dachi_kottedzhi?q=%D0%B4%D0%BE%D0%BC&p=3"
    )


def test_build_category_url_replaces_existing_page() -> None:
    assert build_category_url(BASE, "all/x?p=7", 2) == f"{BASE}/all/x?p=2"


def test_build_category_url_accepts_absolute_url() -> None:
    assert build_category_url(BASE, f"{BASE}/all/x") == f"{BASE}/all/x"


def test_absolute_listing_url_strips_tracking_query() -> None:
    assert absolute_listing_url(BASE, CARD["href"]) == (
        f"{BASE}/moskva/predlozheniya_uslug/perevoznaya_mobilnaya_banya_7816571444"
    )


@pytest.mark.parametrize(
    ("href", "expected"),
    [
        (
            "/brands/c73f82caea9710b718c6f9d9c3d23262?src=search_seller_info",
            "c73f82caea9710b718c6f9d9c3d23262",
        ),
        ("/brands/i207777391?src=search_seller_info&iid=1", "i207777391"),
        ("/brands/1-an?src=x", "1-an"),
        ("/brands/abc/all?sellerId=zzz", "abc"),
        ("/moskva/predlozheniya_uslug/item_1", None),
        (None, None),
    ],
)
def test_extract_seller_key(href: str | None, expected: str | None) -> None:
    assert extract_seller_key(href) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("641000", 641000),
        ("641 000 ₽", 641000),
        ("от 50 000 ₽", 50000),
        ("", None),
        (None, None),
        ("Цена договорная", None),
    ],
)
def test_parse_price(raw: str | None, expected: int | None) -> None:
    assert parse_price(raw) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Активные11", 11),
        ("Активные3", 3),
        ("Активные 1 254", 1254),
        ("Активные", None),
        (None, None),
    ],
)
def test_parse_active_count(text: str | None, expected: int | None) -> None:
    assert parse_active_count(text) == expected


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("Москва", "Москва"),
        ("Донецкий городской совет, Донецк· выезжает по городу", "Донецкий городской совет"),
        (
            "Ленинградская обл., Ломоносовский р-н, Лаголовское сельское поселение",
            "Ленинградская обл.",
        ),
        ("", ""),
        (None, ""),
    ],
)
def test_parse_region(location: str | None, expected: str) -> None:
    assert parse_region(location) == expected


def test_card_to_listing_maps_live_card() -> None:
    listing = card_to_listing(BASE, CARD)

    assert listing is not None
    assert listing.avito_listing_id == "7816571444"
    assert listing.price == 641000
    assert listing.region == "Москва"
    assert "?" not in listing.url


@pytest.mark.parametrize("missing", ["itemId", "title", "href"])
def test_card_to_listing_rejects_incomplete_card(missing: str) -> None:
    broken = {**CARD, missing: None}

    assert card_to_listing(BASE, broken) is None


def test_group_cards_by_seller_deduplicates_listings() -> None:
    other = {**CARD, "itemId": "999", "sellerHref": "/brands/other?src=x"}
    grouped = group_cards_by_seller(BASE, [CARD, dict(CARD), other])

    assert set(grouped) == {"c73f82caea9710b718c6f9d9c3d23262", "other"}
    assert len(grouped["c73f82caea9710b718c6f9d9c3d23262"]) == 1


def test_group_cards_by_seller_skips_cards_without_seller() -> None:
    assert group_cards_by_seller(BASE, [{**CARD, "sellerHref": None}]) == {}


@given(page=st.integers(min_value=1, max_value=200))
def test_build_category_url_page_roundtrip(page: int) -> None:
    url = build_category_url(BASE, BANI_SLUG, page)

    assert url.startswith(f"{BASE}/{BANI_SLUG}")
    assert ("p=" in url) == (page > 1)
    if page > 1:
        assert url.endswith(f"p={page}")


@given(amount=st.integers(min_value=0, max_value=10**9))
def test_parse_price_reads_formatted_amounts(amount: int) -> None:
    formatted = f"{amount:,}".replace(",", " ") + " ₽"

    assert parse_price(formatted) == amount


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("ООО ВИРА - официальная страница во всех регионах", "ООО ВИРА"),
        ("Ваша баня - официальная страница во всех регионах", "Ваша баня"),
        ('"Русская баня" - официальная страница во всех регионах', "Русская баня"),
        ("Наталья - официальная страница во всех регионах, отзывы на Авито", "Наталья"),
        ("Просто заголовок", "Просто заголовок"),
        ("", None),
        (None, None),
    ],
)
def test_strip_profile_title_suffix(title: str | None, expected: str | None) -> None:
    assert strip_profile_title_suffix(title) == expected


def test_parse_seller_name_prefers_name_marker() -> None:
    profile = {
        "markerName": "Наталья",
        "ogTitle": "Что-то другое - официальная страница",
        "docTitle": "Ещё другое",
    }

    assert parse_seller_name(profile, "i207777391") == "Наталья"


def test_parse_seller_name_falls_back_to_og_title() -> None:
    profile = {"markerName": None, "ogTitle": "ООО ВИРА - официальная страница", "docTitle": None}

    assert parse_seller_name(profile, "metalllider") == "ООО ВИРА"


def test_parse_seller_name_falls_back_to_doc_title() -> None:
    profile = {"markerName": "", "ogTitle": None, "docTitle": "Ваша баня - официальная страница"}

    assert parse_seller_name(profile, "key") == "Ваша баня"


def test_parse_seller_name_falls_back_to_seller_key() -> None:
    empty = {"markerName": None, "ogTitle": None, "docTitle": None}

    assert parse_seller_name(empty, "key") == "key"


def test_parse_seller_name_never_returns_section_heading() -> None:
    profile = {
        "markerName": None,
        "ogTitle": "ООО ВИРА - официальная страница",
        "docTitle": "Адрес",
    }

    assert parse_seller_name(profile, "metalllider") != "Адрес"


def test_strip_profile_title_suffix_rejects_generic_avito_title() -> None:
    assert strip_profile_title_suffix("Авито — Объявления на сайте Авито") is None


def test_parse_seller_name_ignores_generic_avito_title() -> None:
    profile = {
        "markerName": None,
        "ogTitle": "Авито — Объявления на сайте Авито",
        "docTitle": "Авито",
    }

    assert parse_seller_name(profile, "i20706068") == "i20706068"


def test_parse_seller_name_keeps_company_with_inner_quotes() -> None:
    title = 'Компания "Хозяин Бани" - официальная страница во всех регионах, отзывы на Авито'

    assert parse_seller_name({"ogTitle": title}, "hozyain-bani") == 'Компания "Хозяин Бани"'


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        ({"activeText": "Активные43", "profileItemCount": 5}, 43),
        ({"activeText": None, "profileItemCount": 12}, 12),
        ({"activeText": None, "profileItemCount": 0}, None),
        ({}, None),
    ],
)
def test_parse_listings_count(profile: dict[str, object], expected: int | None) -> None:
    assert parse_listings_count(profile) == expected


def test_missing_session_file_means_an_anonymous_context(tmp_path) -> None:
    client = PlaywrightAvitoClient(
        get_settings().model_copy(update={"avito_storage_state_path": "does-not-exist.json"})
    )

    assert client._storage_state_path() is None


def test_empty_session_setting_means_an_anonymous_context() -> None:
    client = PlaywrightAvitoClient(
        get_settings().model_copy(update={"avito_storage_state_path": ""})
    )

    assert client._storage_state_path() is None


def test_existing_session_file_is_used(tmp_path) -> None:
    state = tmp_path / "state.json"
    state.write_text("{}", encoding="utf-8")

    client = PlaywrightAvitoClient(
        get_settings().model_copy(update={"avito_storage_state_path": str(state)})
    )

    assert client._storage_state_path() == str(state)
