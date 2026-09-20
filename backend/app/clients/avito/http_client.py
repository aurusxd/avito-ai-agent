import asyncio
import random
import re
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from curl_cffi import requests as curl_requests
from loguru import logger

from app.clients.avito.api_url import AvitoApiUrlResolver
from app.clients.avito.base import (
    AvitoAccountRef,
    AvitoBlockedError,
    IncomingReplyDTO,
    ParserResult,
    SendResult,
)
from app.clients.avito.playwright_client import (
    PlaywrightAvitoClient,
    absolute_listing_url,
    build_category_url,
    parse_region,
)
from app.clients.cookies.base import (
    CookieBudgetExhaustedError,
    CookieBundle,
    CookieProvider,
    CookieProviderError,
)
from app.clients.cookies.factory import get_cookie_provider
from app.config import Settings, get_settings
from app.domain.rotation import BlockKindLiteral
from app.domain.schemas import CategoryDTO, ListingDTO, SellerDTO

if TYPE_CHECKING:
    from app.clients.avito.base import AvitoClient

# коды, которыми Авито закрывает http-транспорт (§27.9)
BLOCK_STATUSES: dict[int, BlockKindLiteral] = {
    403: "forbidden",
    429: "rate_limited",
    439: "forbidden",
}
SELLER_KEY_PATTERN = re.compile(r"/(?:brands|user)/([^/?#]+)")
DEFAULT_REGION = "Россия"


def api_page_url(api_url: str, page: int) -> str:
    """Пагинация JSON-выдачи идёт параметром `page`; `p` здесь не работает (§27.2)."""
    parts = urlsplit(api_url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in {"p", "page"}
    ]
    if page > 1:
        query.append(("page", str(page)))
    return urlunsplit(parts._replace(query=urlencode(query)))


def extract_items(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    catalog = payload.get("catalog")
    items = catalog.get("items") if isinstance(catalog, dict) else None
    if not isinstance(items, list):
        items = payload.get("items")
    if not isinstance(items, list):
        return []
    # строки без id это не объявления, а служебные блоки выдачи (§27.3)
    return [item for item in items if isinstance(item, dict) and item.get("id")]


def seller_profile(item: dict[str, Any]) -> dict[str, Any] | None:
    iva = item.get("iva")
    steps = iva.get("UserInfoStep") if isinstance(iva, dict) else None
    if not isinstance(steps, list):
        return None
    for step in steps:
        if not isinstance(step, dict):
            continue
        payload = step.get("payload")
        profile = payload.get("profile") if isinstance(payload, dict) else None
        if isinstance(profile, dict) and profile.get("link"):
            return profile
    return None


def seller_key_from_link(link: str | None) -> str | None:
    if not link:
        return None
    match = SELLER_KEY_PATTERN.search(link)
    return match.group(1) if match else None


def item_price(item: dict[str, Any]) -> int | None:
    price = item.get("priceDetailed")
    value = price.get("value") if isinstance(price, dict) else None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(value) if value >= 0 else None


def item_region(item: dict[str, Any], fallback: str) -> str:
    address = item.get("addressDetailed")
    location = address.get("locationName") if isinstance(address, dict) else None
    if not location:
        node = item.get("location")
        location = node.get("name") if isinstance(node, dict) else None
    return parse_region(location if isinstance(location, str) else None) or fallback


def item_to_listing(base_url: str, item: dict[str, Any], fallback_region: str) -> ListingDTO | None:
    listing_id, title, path = item.get("id"), item.get("title"), item.get("urlPath")
    if not listing_id or not isinstance(title, str) or not title or not isinstance(path, str):
        return None
    return ListingDTO(
        avito_listing_id=str(listing_id),
        title=title,
        url=absolute_listing_url(base_url, path),
        region=item_region(item, fallback_region),
        price=item_price(item),
    )


def build_results(
    base_url: str, items: list[dict[str, Any]], fallback_region: str
) -> list[ParserResult]:
    """Продавец приходит вместе с выдачей, заход на профиль не нужен (§27.3)."""
    sellers: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()

    for item in items:
        profile = seller_profile(item)
        if profile is None:
            continue
        key = seller_key_from_link(str(profile.get("link")))
        listing = item_to_listing(base_url, item, fallback_region)
        if key is None or listing is None or listing.avito_listing_id in seen:
            continue
        seen.add(listing.avito_listing_id)

        bucket = sellers.setdefault(
            key,
            {
                "name": str(profile.get("title") or "").strip() or key,
                "profile_url": absolute_listing_url(base_url, str(profile.get("link"))),
                "listings": [],
            },
        )
        cast("list[ListingDTO]", bucket["listings"]).append(listing)

    results: list[ParserResult] = []
    for key, bucket in sellers.items():
        listings = cast("list[ListingDTO]", bucket["listings"])
        results.append(
            ParserResult(
                seller=SellerDTO(
                    avito_seller_id=key,
                    name=str(bucket["name"]),
                    profile_url=str(bucket["profile_url"]),
                    # §27.4: в выдаче счётчика профиля нет, считаем по собранным страницам
                    listings_count=len(listings),
                    region=listings[0].region if listings else fallback_region,
                ),
                listings=listings,
            )
        )
    return results


class HttpAvitoClient:
    """Парсинг по JSON-выдаче через curl_cffi с прогретой сессией (§27).

    Отправку и чтение ответов не трогает: они идут под сессией аккаунта и
    остаются на Playwright (§27.11).
    """

    def __init__(
        self,
        settings: Settings | None = None,
        cookies: CookieProvider | None = None,
        resolver: AvitoApiUrlResolver | None = None,
        fallback: "AvitoClient | None" = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.cookies = cookies or get_cookie_provider()
        self.resolver = resolver or AvitoApiUrlResolver(self.settings)
        self.fallback = fallback or PlaywrightAvitoClient(self.settings)

    async def parse_category(self, category: CategoryDTO) -> list[ParserResult]:
        category_url = build_category_url(self.settings.avito_base_url, category.avito_url_or_slug)
        api_url = await self.resolver.resolve(category_url)

        items: list[dict[str, Any]] = []
        for page in range(1, self.settings.parser_max_pages + 1):
            if page > 1:
                await self._sleep()
            payload = await self._fetch(api_page_url(api_url, page))
            page_items = extract_items(payload)
            logger.info("api page {page}: {count} items", page=page, count=len(page_items))
            if not page_items:
                break
            items.extend(page_items)

        results = build_results(self.settings.avito_base_url, items, category.region)
        limit = self.settings.parser_max_sellers_per_run
        return results[:limit] if limit else results

    async def send_message(
        self, account: AvitoAccountRef, seller: SellerDTO, text: str
    ) -> SendResult:
        return await self.fallback.send_message(account, seller, text)

    async def fetch_replies(
        self, account: AvitoAccountRef, limit: int = 50
    ) -> list[IncomingReplyDTO]:
        return await self.fallback.fetch_replies(account, limit)

    async def _fetch(self, url: str) -> object:
        bundle = await self._bundle()
        status, payload = await self._get(url, bundle)
        if status not in BLOCK_STATUSES:
            return payload

        block_kind = BLOCK_STATUSES[status]
        logger.warning("avito returned {status} on the api url", status=status)

        # 1. разблокировка бесплатна, поэтому всегда первая (§27.9)
        refreshed = await self.cookies.refresh()
        if refreshed is not None:
            status, payload = await self._get(url, refreshed)
            if status not in BLOCK_STATUSES:
                return payload
            block_kind = BLOCK_STATUSES[status]

        # 2. не помогло — новая кука, если кулдаун и суточный потолок позволяют
        try:
            await self.cookies.invalidate()
            bought = await self.cookies.get()
        except CookieBudgetExhaustedError as error:
            raise AvitoBlockedError(str(error), block_kind) from error
        except CookieProviderError as error:
            raise AvitoBlockedError(f"cookies unavailable: {error}", block_kind) from error

        status, payload = await self._get(url, bought)
        if status in BLOCK_STATUSES:
            raise AvitoBlockedError(
                f"avito closed this transport: {BLOCK_STATUSES[status]}", BLOCK_STATUSES[status]
            )
        return payload

    async def _bundle(self) -> CookieBundle:
        try:
            return await self.cookies.get()
        except CookieBudgetExhaustedError as error:
            raise AvitoBlockedError(str(error), "rate_limited") from error
        except CookieProviderError as error:
            raise AvitoBlockedError(f"cookies unavailable: {error}", "unavailable") from error

    async def _get(self, url: str, bundle: CookieBundle) -> tuple[int, object]:
        return await asyncio.to_thread(self._get_sync, url, bundle)

    def _get_sync(self, url: str, bundle: CookieBundle) -> tuple[int, object]:
        proxy = bundle.proxy_url or self.settings.parser_proxy_url
        session = curl_requests.Session(impersonate=bundle.impersonate or "chrome")
        try:
            if bundle.headers:
                session.headers.update(bundle.headers)
            if bundle.user_agent:
                session.headers["user-agent"] = bundle.user_agent
            if bundle.cookies:
                session.cookies.update(bundle.cookies)
            if proxy:
                session.proxies = {"http": proxy, "https": proxy}

            response = session.get(url, timeout=self.settings.parser_nav_timeout_ms / 1000)
            if response.status_code in BLOCK_STATUSES:
                return response.status_code, None
            try:
                return response.status_code, response.json()
            except ValueError:
                return response.status_code, None
        except curl_requests.RequestsError as error:
            raise AvitoBlockedError(
                f"api request failed: {type(error).__name__}", "unavailable"
            ) from error
        finally:
            session.close()

    async def _sleep(self) -> None:
        low = self.settings.parser_delay_min_seconds
        high = max(low, self.settings.parser_delay_max_seconds)
        await asyncio.sleep(random.uniform(low, high))
