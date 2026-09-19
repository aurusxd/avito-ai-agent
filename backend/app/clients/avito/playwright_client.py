import asyncio
import hashlib
import random
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode, urljoin, urlparse, urlunparse

from loguru import logger
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    ProxySettings,
    async_playwright,
)
from playwright.async_api import (
    Error as PlaywrightError,
)

from app.clients.avito.base import (
    AvitoAccountRef,
    AvitoBlockedError,
    IncomingReplyDTO,
    ParserResult,
    SendResult,
)
from app.clients.avito.browser import launch_args
from app.config import BACKEND_ROOT, Settings, get_settings
from app.domain.proxy import ProxyCredentials, proxy_settings
from app.domain.rotation import BlockKindLiteral
from app.domain.schemas import CategoryDTO, ListingDTO, SellerDTO

ITEM_SELECTOR = '[data-marker="item"]'
NEXT_PAGE_SELECTOR = '[data-marker="pagination-button/nextPage"]'
ACTIVE_TAB_SELECTOR = '[data-marker="extended_profile_tabs/tab(active)"]'
ICEBREAKER_TEXTAREA = '[data-marker="icebreakers/textarea"]'
ICEBREAKER_SEND = '[data-marker="icebreakers/send-message"]'
VPN_CHECK_SELECTOR = '[data-marker="vpn-check-retry-button"]'
PROFILE_LINK_SELECTOR = '[data-marker="item-title"]'
LOGGED_OUT_SELECTOR = '[data-marker="header/login-button"]'

MESSENGER_PATH = "/profile/messenger"
CHANNELS_LIST_SELECTOR = '[data-marker="channels/list"]'
CHANNEL_SELECTOR = '[data-marker="channels/channel"]'
MESSAGE_SELECTOR = '[data-marker="message"]'
# left bubbles are the interlocutor's, right bubbles are ours; captured live
INBOUND_BUBBLE_CLASS = "message-base-module-left"

CAPTCHA_MARKERS = ("подтвердите, что вы не робот", "captcha")
FORBIDDEN_MARKERS = (
    "доступ ограничен",
    "проблема с ip",
    "возможно, у вас включён vpn",
    "возможно, у вас включен vpn",
)
BLOCK_MARKERS = CAPTCHA_MARKERS + FORBIDDEN_MARKERS
PROFILE_TITLE_SUFFIX = re.compile(r"\s+[-–—]\s+официальная страница")
GENERIC_TITLE = re.compile(r"^Авито")

CARDS_SCRIPT = """
() => [...document.querySelectorAll('[data-marker="item"]')].map((it) => {
  const title = it.querySelector('[data-marker="item-title"]');
  const priceMeta = it.querySelector('meta[itemprop="price"]');
  const location = it.querySelector('[data-marker="item-location"]');
  const sellerLink = it.querySelector('a[href*="/brands/"]');
  return {
    itemId: it.getAttribute('data-item-id'),
    title: title ? title.textContent.trim() : null,
    href: title ? title.getAttribute('href') : null,
    price: priceMeta ? priceMeta.getAttribute('content') : null,
    location: location ? location.textContent.trim() : null,
    sellerHref: sellerLink ? sellerLink.getAttribute('href') : null,
  };
})
"""

PROFILE_SCRIPT = """
() => {
  const tab = document.querySelector('[data-marker="extended_profile_tabs/tab(active)"]');
  const nameMarker = document.querySelector('[data-marker^="name "]');
  const ogTitle = document.querySelector('meta[property="og:title"]');
  return {
    url: location.href,
    markerName: nameMarker ? nameMarker.textContent.trim() : null,
    ogTitle: ogTitle ? ogTitle.getAttribute('content') : null,
    docTitle: document.title,
    activeText: tab ? tab.textContent.trim() : null,
    profileItemCount: document.querySelectorAll('[data-marker="item"]').length,
  };
}
"""

# the channel row exposes data-id but not always an <a href>; the chat url is
# built from the id: /profile/messenger/channel/<data-id> (captured live)
CHANNELS_SCRIPT = """
() => [...document.querySelectorAll('[data-marker="channels/channel"]')]
  .map((el) => el.getAttribute('data-id'))
  .filter(Boolean)
"""

CHANNEL_SCRIPT = """
(inboundClass) => {
  const userLink = document.querySelector('a[href*="/user/"]');
  let sellerId = null;
  if (userLink) {
    const match = userLink.getAttribute('href').match(/\\/user\\/([0-9a-z]+)/i);
    if (match) sellerId = match[1];
  }
  const inbound = [...document.querySelectorAll('[data-marker="message"]')]
    .filter((el) => (el.className || '').includes(inboundClass))
    .map((el) => {
      const text = el.querySelector('[data-marker="messageText"]');
      return (text ? text.textContent : el.textContent || '').trim();
    })
    .filter(Boolean);
  return { sellerId, inbound };
}
"""


def _parse_pairs(query: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for chunk in query.split("&"):
        if not chunk:
            continue
        key, _, value = chunk.partition("=")
        pairs.append((key, value))
    return pairs


def build_category_url(base_url: str, slug_or_url: str, page_number: int = 1) -> str:
    target = (
        slug_or_url
        if slug_or_url.startswith("http")
        else urljoin(base_url + "/", slug_or_url.lstrip("/"))
    )
    parts = urlparse(target)
    query = [(key, value) for key, value in _parse_pairs(parts.query) if key != "p"]
    if page_number > 1:
        query.append(("p", str(page_number)))
    return urlunparse(parts._replace(query=urlencode(query, safe="%+")))


def absolute_listing_url(base_url: str, href: str) -> str:
    absolute = href if href.startswith("http") else urljoin(base_url + "/", href.lstrip("/"))
    return urlunparse(urlparse(absolute)._replace(query="", fragment=""))


def extract_seller_key(href: str | None) -> str | None:
    if not href:
        return None
    match = re.search(r"/brands/([^/?#]+)", href)
    return match.group(1) if match else None


def parse_price(raw: str | None) -> int | None:
    if not raw:
        return None
    digits = re.sub(r"[^0-9]", "", raw)
    return int(digits) if digits else None


def parse_active_count(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"(\d[\d\s ]*)$", text.strip())
    if not match:
        return None
    return int(re.sub(r"[^0-9]", "", match.group(1)))


def strip_profile_title_suffix(title: str | None) -> str | None:
    if not title:
        return None
    parts = PROFILE_TITLE_SUFFIX.split(title)
    if len(parts) == 1 and GENERIC_TITLE.match(title.strip()):
        return None
    head = parts[0].strip()
    if len(head) > 1 and head[0] == head[-1] and head[0] in "\"«»'":
        head = head[1:-1].strip()
    return head or None


def parse_seller_name(profile: dict[str, Any], fallback: str) -> str:
    marker_name = (profile.get("markerName") or "").strip()
    if marker_name:
        return marker_name
    for key in ("ogTitle", "docTitle"):
        name = strip_profile_title_suffix(profile.get(key))
        if name:
            return name
    return fallback


def parse_listings_count(profile: dict[str, Any]) -> int | None:
    from_tab = parse_active_count(profile.get("activeText"))
    if from_tab is not None:
        return from_tab
    on_page = profile.get("profileItemCount")
    return int(on_page) if isinstance(on_page, int) and on_page > 0 else None


def parse_region(location: str | None) -> str:
    if not location:
        return ""
    head = location.split(",")[0]
    return re.split(r"[·•]", head)[0].strip()


def card_to_listing(base_url: str, card: dict[str, Any]) -> ListingDTO | None:
    listing_id, title, href = card.get("itemId"), card.get("title"), card.get("href")
    if not listing_id or not title or not href:
        return None
    return ListingDTO(
        avito_listing_id=str(listing_id),
        title=title,
        url=absolute_listing_url(base_url, href),
        region=parse_region(card.get("location")) or "Россия",
        price=parse_price(card.get("price")),
    )


def group_cards_by_seller(
    base_url: str, cards: list[dict[str, Any]]
) -> dict[str, list[ListingDTO]]:
    grouped: dict[str, list[ListingDTO]] = {}
    seen: set[str] = set()
    for card in cards:
        seller_key = extract_seller_key(card.get("sellerHref"))
        listing = card_to_listing(base_url, card)
        if seller_key is None or listing is None:
            continue
        if listing.avito_listing_id in seen:
            continue
        seen.add(listing.avito_listing_id)
        grouped.setdefault(seller_key, []).append(listing)
    return grouped


class PlaywrightAvitoClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def parse_category(self, category: CategoryDTO) -> list[ParserResult]:
        validated = CategoryDTO.model_validate(category)

        proxy: ProxySettings | None = (
            {"server": self.settings.avito_proxy_server}
            if self.settings.avito_proxy_server
            else None
        )

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=self.settings.avito_headless,
                args=launch_args(self.settings),
                proxy=proxy,
            )
            try:
                context = await self._new_context(browser)
                page = await context.new_page()
                cards = await self._collect_cards(page, validated)
                return await self._build_results(page, validated, cards)
            finally:
                await browser.close()

    async def send_message(
        self, account: AvitoAccountRef, seller: SellerDTO, text: str
    ) -> SendResult:
        validated_account = AvitoAccountRef.model_validate(account)
        validated_seller = SellerDTO.model_validate(seller)
        if not text.strip():
            raise ValueError("message text must not be empty")

        proxy = proxy_settings(validated_account.proxy_url) or self._settings_proxy()

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=self.settings.avito_headless,
                args=launch_args(self.settings),
                proxy=cast("ProxySettings | None", proxy),
            )
            try:
                context = await browser.new_context(
                    storage_state=validated_account.session_storage_path,
                    viewport={"width": 1440, "height": 900},
                    locale="ru-RU",
                    timezone_id="Europe/Moscow",
                )
                page = await context.new_page()
                return await self._write_to_seller(page, validated_seller, text)
            finally:
                await browser.close()

    async def _write_to_seller(self, page: Page, seller: SellerDTO, text: str) -> SendResult:
        await self._goto(page, seller.profile_url)
        await self._require_session(page, seller)

        listing_url = await self._first_listing_url(page)
        if listing_url is None:
            return SendResult(
                status="failed",
                sent_at=datetime.now(UTC),
                error=f"seller {seller.avito_seller_id} has no listing to write from",
            )

        await self._sleep()
        await self._goto(page, listing_url)

        if await page.query_selector(ICEBREAKER_TEXTAREA) is None:
            return SendResult(
                status="failed",
                sent_at=datetime.now(UTC),
                error=f"no message composer on {listing_url}",
            )

        await self._type_like_human(page, text)
        await page.click(ICEBREAKER_SEND)
        await page.wait_for_timeout(self.settings.outreach_settle_ms)

        block_kind = await self._detect_block(page, None)
        if block_kind is not None:
            raise AvitoBlockedError(f"avito returned {block_kind} while sending", block_kind)

        logger.info("message sent to seller {seller}", seller=seller.avito_seller_id)
        return SendResult(status="sent", sent_at=datetime.now(UTC))

    async def _require_session(self, page: Page, seller: SellerDTO) -> None:
        if await page.query_selector(LOGGED_OUT_SELECTOR) is not None:
            raise AvitoBlockedError(
                f"session expired before writing to {seller.avito_seller_id}",
                "auth_required",
            )

    async def _first_listing_url(self, page: Page) -> str | None:
        link = await page.query_selector(PROFILE_LINK_SELECTOR)
        href = await link.get_attribute("href") if link else None
        return absolute_listing_url(self.settings.avito_base_url, href) if href else None

    async def _type_like_human(self, page: Page, text: str) -> None:
        low = self.settings.outreach_type_delay_min_ms
        high = max(low, self.settings.outreach_type_delay_max_ms)
        composer = page.locator(ICEBREAKER_TEXTAREA)
        await composer.click()

        if await composer.input_value():
            await composer.press("Control+a")
            await composer.press("Delete")

        await composer.press_sequentially(text, delay=random.uniform(low, high))
        await page.wait_for_timeout(random.randint(400, 1_200))

    def _settings_proxy(self) -> ProxyCredentials | None:
        return proxy_settings(self.settings.avito_proxy_server)

    def _storage_state_path(self) -> str | None:
        # the catalogue is public, so a missing session file must not stop a
        # crawl: playwright raises FileNotFoundError on a path that is not there
        raw = self.settings.avito_storage_state_path
        if not raw:
            return None
        path = Path(raw)
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        if not path.is_file():
            logger.info("no session file at {path}, parsing anonymously", path=raw)
            return None
        return str(path)

    async def _new_context(self, browser: Browser) -> BrowserContext:
        return await browser.new_context(
            storage_state=self._storage_state_path(),
            viewport={"width": 1440, "height": 900},
            locale="ru-RU",
            timezone_id="Europe/Moscow",
        )

    async def _collect_cards(self, page: Page, category: CategoryDTO) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        for page_number in range(1, self.settings.parser_max_pages + 1):
            url = build_category_url(
                self.settings.avito_base_url, category.avito_url_or_slug, page_number
            )
            await self._goto(page, url)
            await page.wait_for_selector(ITEM_SELECTOR, timeout=self.settings.parser_nav_timeout_ms)
            page_cards: list[dict[str, Any]] = await page.evaluate(CARDS_SCRIPT)
            logger.info(
                "category page {page} parsed: {count} cards",
                page=page_number,
                count=len(page_cards),
            )
            cards.extend(page_cards)
            if await page.query_selector(NEXT_PAGE_SELECTOR) is None:
                break
            await self._sleep()
        return cards

    async def _build_results(
        self, page: Page, category: CategoryDTO, cards: list[dict[str, Any]]
    ) -> list[ParserResult]:
        base_url = self.settings.avito_base_url
        grouped = group_cards_by_seller(base_url, cards)

        limit = self.settings.parser_max_sellers_per_run
        candidates = list(grouped.items())
        if limit:
            candidates = candidates[:limit]

        results: list[ParserResult] = []
        for seller_key, listings in candidates:
            profile = await self._read_profile(page, seller_key)
            listings_count = profile["listings_count"] or len(listings)
            if listings_count < category.min_listings_per_seller:
                logger.debug(
                    "seller {key} skipped: {count} listings", key=seller_key, count=listings_count
                )
                continue
            results.append(
                ParserResult(
                    seller=SellerDTO(
                        avito_seller_id=seller_key,
                        name=profile["name"],
                        profile_url=f"{base_url}/brands/{seller_key}",
                        listings_count=listings_count,
                        region=listings[0].region or category.region,
                    ),
                    listings=listings,
                )
            )
            await self._sleep()
        return results

    async def _read_profile(self, page: Page, seller_key: str) -> dict[str, Any]:
        await self._goto(page, f"{self.settings.avito_base_url}/brands/{seller_key}")
        try:
            await page.wait_for_selector(ACTIVE_TAB_SELECTOR, timeout=8_000)
        except Exception:
            logger.warning("profile {key} has no active-listings tab", key=seller_key)
        if self.settings.parser_profile_settle_ms:
            await page.wait_for_timeout(self.settings.parser_profile_settle_ms)
        profile: dict[str, Any] = await page.evaluate(PROFILE_SCRIPT)
        return {
            "name": parse_seller_name(profile, seller_key),
            "listings_count": parse_listings_count(profile),
        }

    async def _goto(self, page: Page, url: str) -> None:
        attempts = self.settings.parser_nav_retries + 1
        status: int | None = None
        for attempt in range(1, attempts + 1):
            try:
                response = await page.goto(
                    url, wait_until="domcontentloaded", timeout=self.settings.parser_nav_timeout_ms
                )
                status = response.status if response else None
                break
            except PlaywrightError as error:
                if attempt == attempts:
                    raise
                logger.warning(
                    "navigation to {url} failed ({attempt}/{attempts}): {error}",
                    url=url,
                    attempt=attempt,
                    attempts=attempts,
                    error=error,
                )
                await asyncio.sleep(self.settings.parser_retry_backoff_seconds * attempt)

        if self.settings.avito_block_check_delay_ms:
            await page.wait_for_timeout(self.settings.avito_block_check_delay_ms)

        block_kind = await self._detect_block(page, status)
        if block_kind is not None:
            raise AvitoBlockedError(f"avito returned {block_kind} on {url}", block_kind)

    async def _detect_block(self, page: Page, status: int | None) -> BlockKindLiteral | None:
        if status == 429:
            return "rate_limited"
        if status == 403:
            return "forbidden"
        if await page.query_selector(VPN_CHECK_SELECTOR) is not None:
            return "forbidden"

        haystack = f"{await page.title()} {await page.inner_text('body')}".lower()
        if any(marker in haystack for marker in CAPTCHA_MARKERS):
            return "captcha"
        if any(marker in haystack for marker in FORBIDDEN_MARKERS):
            return "forbidden"
        return None

    async def _sleep(self) -> None:
        low = self.settings.parser_delay_min_seconds
        high = max(low, self.settings.parser_delay_max_seconds)
        await asyncio.sleep(random.uniform(low, high))

    async def fetch_replies(
        self, account: AvitoAccountRef, limit: int = 50
    ) -> list[IncomingReplyDTO]:
        validated = AvitoAccountRef.model_validate(account)
        proxy = proxy_settings(validated.proxy_url) or self._settings_proxy()

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=self.settings.avito_headless,
                args=launch_args(self.settings),
                proxy=cast("ProxySettings | None", proxy),
            )
            try:
                context = await browser.new_context(
                    storage_state=validated.session_storage_path,
                    viewport={"width": 1440, "height": 900},
                    locale="ru-RU",
                    timezone_id="Europe/Moscow",
                )
                page = await context.new_page()
                return await self._collect_replies(page, limit)
            finally:
                await browser.close()

    async def _collect_replies(self, page: Page, limit: int) -> list[IncomingReplyDTO]:
        await self._goto(page, urljoin(self.settings.avito_base_url, MESSENGER_PATH))

        try:
            await page.wait_for_selector(
                f"{CHANNEL_SELECTOR}, {LOGGED_OUT_SELECTOR}",
                timeout=self.settings.parser_nav_timeout_ms,
            )
        except PlaywrightError:
            logger.debug("messenger showed neither a channel row nor the login button")

        if await page.query_selector(LOGGED_OUT_SELECTOR) is not None:
            raise AvitoBlockedError("session expired while reading the inbox", "auth_required")

        if await page.query_selector(CHANNEL_SELECTOR) is None:
            return []

        await page.wait_for_timeout(self.settings.parser_profile_settle_ms)
        channel_ids: list[str] = await page.evaluate(CHANNELS_SCRIPT)

        replies: list[IncomingReplyDTO] = []
        seen: set[str] = set()
        for channel_id in channel_ids[:limit]:
            await self._sleep()
            try:
                reply = await self._read_channel(page, channel_id)
            except AvitoBlockedError:
                raise
            except PlaywrightError as error:
                logger.debug("skipped a channel that failed to load: {error}", error=error)
                continue

            if reply is None or reply.external_id in seen:
                continue
            seen.add(reply.external_id)
            replies.append(reply)
            if len(replies) >= limit:
                break

        return replies

    async def _read_channel(self, page: Page, channel_id: str) -> IncomingReplyDTO | None:
        chat_url = urljoin(self.settings.avito_base_url, f"{MESSENGER_PATH}/channel/{channel_id}")
        await self._goto(page, chat_url)

        try:
            await page.wait_for_selector(
                MESSAGE_SELECTOR, timeout=self.settings.parser_nav_timeout_ms
            )
        except PlaywrightError:
            return None

        await page.wait_for_timeout(self.settings.parser_profile_settle_ms)
        data: dict[str, Any] = await page.evaluate(CHANNEL_SCRIPT, INBOUND_BUBBLE_CLASS)

        seller_id = data.get("sellerId")
        inbound = [text for text in (data.get("inbound") or []) if text]
        if not seller_id or not inbound:
            return None

        # avito exposes no per-message id in the dom, so the dedup key is the
        # channel id plus a hash of the latest inbound text (see tech.md 20.4)
        text = inbound[-1]
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
        return IncomingReplyDTO(
            external_id=f"{channel_id}:{digest}",
            avito_seller_id=str(seller_id),
            text=text,
            received_at=datetime.now(UTC),
            chat_url=chat_url,
        )
