from typing import Any

from app.clients.avito.http_client import (
    api_page_url,
    build_results,
    extract_items,
    item_price,
    item_region,
    item_to_listing,
    seller_key_from_link,
    seller_profile,
)

BASE = "https://www.avito.ru"
API_URL = (
    "https://www.avito.ru/web/1/js/items?categoryId=19&localPriority=0&locationId=621540"
    "&presentationType=serp&sort=default"
)


def item(
    listing_id: int | None,
    title: str = "Каркасная баня",
    *,
    seller_link: str | None = "/brands/i302005374?src=search_seller_info&iid=8091549847",
    seller_title: str = "СтройБлок",
    price: int | None = 450000,
    location: str = "Нижний Новгород, Советский район",
) -> dict[str, Any]:
    """Карточка в форме живого ответа выдачи (§27.3)."""
    payload: dict[str, Any] = {
        "id": listing_id,
        "title": title,
        "urlPath": f"/nizhniy_novgorod/remont_i_stroitelstvo/karkasnaya_banya_{listing_id}"
        "?context=H4sIAAAAAAAA_wE_AMD_",
        "addressDetailed": {"locationName": location},
        "category": {"id": 19, "name": "Ремонт и строительство", "slug": "remont_i_stroitelstvo"},
    }
    if price is not None:
        payload["priceDetailed"] = {"value": price, "string": str(price)}
    if seller_link is not None:
        payload["iva"] = {
            "UserInfoStep": [
                {
                    "componentData": {"component": "seller-info"},
                    "payload": {
                        "rating": {"score": 4.9, "summary": "109 отзывов"},
                        "profile": {"title": seller_title, "link": seller_link},
                    },
                }
            ]
        }
    return payload


def test_api_page_url_keeps_first_page_untouched() -> None:
    assert api_page_url(API_URL, 1) == API_URL


def test_api_page_url_adds_page_parameter() -> None:
    assert api_page_url(API_URL, 3).endswith("&page=3")


def test_api_page_url_replaces_web_page_parameter() -> None:
    # `p` работает на web-странице и не работает в выдаче (§27.2)
    assert api_page_url(f"{API_URL}&p=7", 2).endswith("&page=2")
    assert "p=7" not in api_page_url(f"{API_URL}&p=7", 2)


def test_api_page_url_replaces_existing_page() -> None:
    assert api_page_url(f"{API_URL}&page=5", 2).endswith("&page=2")


def test_extract_items_reads_catalog() -> None:
    payload = {"catalog": {"items": [item(1), item(2)]}}

    assert [row["id"] for row in extract_items(payload)] == [1, 2]


def test_extract_items_drops_rows_without_id() -> None:
    # в живом ответе такие строки есть, это служебные блоки выдачи
    payload = {"catalog": {"items": [item(None), item(8091549847), {"type": "advert"}]}}

    assert [row["id"] for row in extract_items(payload)] == [8091549847]


def test_extract_items_survives_unexpected_shapes() -> None:
    assert extract_items(None) == []
    assert extract_items({"catalog": {}}) == []
    assert extract_items({"items": "nope"}) == []


def test_seller_profile_read_from_user_info_step() -> None:
    profile = seller_profile(item(1))

    assert profile is not None
    assert profile["title"] == "СтройБлок"


def test_seller_profile_absent_when_step_is_missing() -> None:
    assert seller_profile(item(1, seller_link=None)) is None


def test_seller_key_supports_both_profile_shapes() -> None:
    assert seller_key_from_link("/brands/i302005374?src=search") == "i302005374"
    assert seller_key_from_link("/user/d18fd7689a4be218aa52996dd1d30658/profile") == (
        "d18fd7689a4be218aa52996dd1d30658"
    )
    assert seller_key_from_link(None) is None
    assert seller_key_from_link("/company/x") is None


def test_item_price_reads_price_detailed() -> None:
    assert item_price(item(1, price=450000)) == 450000
    assert item_price(item(1, price=None)) is None
    assert item_price({"priceDetailed": {"value": "нет"}}) is None


def test_item_region_takes_the_head_of_the_address() -> None:
    assert item_region(item(1, location="Нижний Новгород, Советский район"), "Россия") == (
        "Нижний Новгород"
    )
    assert item_region({"location": {"name": "Тверь"}}, "Россия") == "Тверь"
    assert item_region({}, "Россия") == "Россия"


def test_item_to_listing_strips_the_context_query() -> None:
    listing = item_to_listing(BASE, item(8091549847), "Россия")

    assert listing is not None
    assert listing.avito_listing_id == "8091549847"
    assert "context" not in listing.url
    assert listing.url.startswith(f"{BASE}/nizhniy_novgorod/")
    assert listing.price == 450000


def test_item_to_listing_needs_id_title_and_path() -> None:
    assert item_to_listing(BASE, {"id": 1, "title": "x"}, "Россия") is None
    assert item_to_listing(BASE, {"id": 1, "urlPath": "/x"}, "Россия") is None


def test_build_results_groups_listings_under_one_seller() -> None:
    items = [item(1), item(2), item(3)]

    results = build_results(BASE, items, "Россия")

    assert len(results) == 1
    result = results[0]
    assert result.seller.avito_seller_id == "i302005374"
    assert result.seller.name == "СтройБлок"
    assert result.seller.profile_url == f"{BASE}/brands/i302005374"
    # §27.4: счётчика профиля в выдаче нет, считаем по собранным страницам
    assert result.seller.listings_count == 3
    assert len(result.listings) == 3


def test_build_results_skips_cards_without_a_profile() -> None:
    items = [item(1), item(2, seller_link=None)]

    results = build_results(BASE, items, "Россия")

    assert len(results) == 1
    assert results[0].seller.listings_count == 1


def test_build_results_is_idempotent_on_repeated_listings() -> None:
    # одно объявление может прийти дважды при перелистывании
    items = [item(1), item(1), item(2)]

    results = build_results(BASE, items, "Россия")

    assert results[0].seller.listings_count == 2


def test_build_results_falls_back_to_the_seller_key_as_a_name() -> None:
    items = [item(1, seller_title="  ")]

    assert build_results(BASE, items, "Россия")[0].seller.name == "i302005374"


def test_build_results_separates_sellers() -> None:
    items = [item(1), item(2, seller_link="/user/abc123/profile", seller_title="Алексей")]

    results = build_results(BASE, items, "Россия")

    assert {row.seller.avito_seller_id for row in results} == {"i302005374", "abc123"}
