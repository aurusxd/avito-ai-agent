import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from loguru import logger

from app.clients.cookies.base import (
    CookieBudgetExhaustedError,
    CookieBundle,
    CookieProviderError,
)
from app.config import Settings, get_settings
from app.domain.proxy import mask_proxy_url, proxy_auth_line

# коды, после которых кука уже не оживёт: покупаем новую, а не ждём
DEAD_COOKIE_STATUSES = (404, 410)


class SpfaCookieProvider:
    """Покупает и оживляет анонимные cookies Авито под наш прокси (§27.6).

    Кука привязана к ip, поэтому провайдер знает прокси парсера и передаёт его
    сервису. Прокси аккаунта сюда не попадает никогда (§27.7).
    """

    provider = "spfa"

    def __init__(
        self,
        settings: Settings | None = None,
        proxy_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.spfa_base_url.rstrip("/")
        self.proxy_url = proxy_url if proxy_url is not None else self.settings.parser_proxy_url
        self.timezone = ZoneInfo(self.settings.timezone)
        self.storage_path = Path(self.settings.spfa_cookie_storage_path)
        self._client = client

        self._bundle: CookieBundle | None = None
        self._last_purchase_at: datetime | None = None
        self._purchase_day: date | None = None
        self._purchases_today = 0
        self._load()

    async def get(self) -> CookieBundle:
        if self._bundle is not None and not self._bundle.empty:
            return self._bundle
        return await self.purchase()

    async def refresh(self) -> CookieBundle | None:
        """Разблокировка: бесплатна, поэтому всегда пробуется раньше покупки (§27.9)."""
        bundle = self._bundle
        if bundle is None or bundle.id is None:
            return None

        payload: dict[str, Any] = {"id": bundle.id, "api_key": self._api_key()}
        line = proxy_auth_line(self.proxy_url)
        if line:
            payload["proxy"] = line

        try:
            response = await self._request("POST", "/unblock/", payload)
        except CookieProviderError as error:
            logger.warning("spfa unblock failed: {error}", error=error)
            return None

        if response.status_code in DEAD_COOKIE_STATUSES:
            logger.info(
                "spfa cookie {id} is gone ({status})", id=bundle.id, status=response.status_code
            )
            await self.invalidate()
            return None

        if response.status_code not in (200, 202):
            logger.warning("spfa unblock returned {status}", status=response.status_code)
            return None

        cookies = self._results(response).get("cookies")
        if not isinstance(cookies, dict) or not cookies:
            # сервис принял задачу, но новых значений не отдал: старые ещё живы
            return bundle

        self._bundle = bundle.model_copy(
            update={"cookies": {str(k): str(v) for k, v in cookies.items()}}
        )
        self._save()
        logger.info("spfa cookie {id} refreshed", id=bundle.id)
        return self._bundle

    async def purchase(self) -> CookieBundle:
        self._guard_budget()

        line = proxy_auth_line(self.proxy_url)
        if not line:
            raise CookieProviderError(
                "spfa needs an authenticated parser proxy (login:password@host:port)"
            )

        response = await self._request(
            "POST", "/cookies/mobile/", {"api_key": self._api_key(), "proxy": line}
        )
        if response.status_code != 200:
            raise CookieProviderError(
                f"spfa refused to sell cookies ({response.status_code})", response.status_code
            )

        results = self._results(response)
        cookies = results.get("cookies")
        if not isinstance(cookies, dict) or not cookies:
            raise CookieProviderError("spfa returned no cookies")

        fingerprint = results.get("fingerprint")
        fingerprint = fingerprint if isinstance(fingerprint, dict) else {}
        headers = fingerprint.get("headers")
        headers = headers if isinstance(headers, dict) else {}
        user_agent = str(results.get("user_agent") or headers.get("user-agent") or "")

        bundle = CookieBundle(
            id=results.get("id") if isinstance(results.get("id"), int) else None,
            cookies={str(key): str(value) for key, value in cookies.items()},
            user_agent=user_agent,
            impersonate=str(fingerprint.get("impersonate") or "chrome"),
            headers={str(key): str(value) for key, value in headers.items()},
            mobile=bool(results.get("mobile", False)),
            obtained_at=datetime.now(UTC),
            proxy_url=self.proxy_url or None,
        )

        self._bundle = bundle
        self._count_purchase()
        self._save()
        logger.info(
            "spfa cookies bought: id={id} mobile={mobile} proxy={proxy}",
            id=bundle.id,
            mobile=bundle.mobile,
            proxy=mask_proxy_url(self.proxy_url),
        )
        return bundle

    async def invalidate(self) -> None:
        self._bundle = None
        self._save()

    async def balance(self) -> float:
        response = await self._request("POST", "/balance/", {"api_key": self._api_key()})
        if response.status_code != 200:
            raise CookieProviderError(
                f"spfa balance unavailable ({response.status_code})", response.status_code
            )
        value = self._payload(response).get("balance")
        return float(value) if isinstance(value, int | float) else 0.0

    def _api_key(self) -> str:
        key = self.settings.spfa_api_key
        if not key:
            raise CookieProviderError("SPFA_API_KEY is not set")
        return key

    def _guard_budget(self) -> None:
        today = datetime.now(self.timezone).date()
        if self._purchase_day != today:
            self._purchase_day = today
            self._purchases_today = 0

        if self._purchases_today >= self.settings.spfa_max_purchases_per_day:
            raise CookieBudgetExhaustedError(
                f"spfa daily cap reached ({self._purchases_today} purchases)"
            )

        if self._last_purchase_at is None:
            return
        elapsed = (datetime.now(UTC) - self._last_purchase_at).total_seconds()
        cooldown = self.settings.spfa_purchase_cooldown_seconds
        if elapsed < cooldown:
            raise CookieBudgetExhaustedError(
                f"spfa purchase cooldown: {int(cooldown - elapsed)}s left"
            )

    def _count_purchase(self) -> None:
        self._last_purchase_at = datetime.now(UTC)
        self._purchase_day = datetime.now(self.timezone).date()
        self._purchases_today += 1

    async def _request(self, method: str, path: str, payload: dict[str, Any]) -> httpx.Response:
        url = f"{self.base_url}{path}"
        try:
            if self._client is not None:
                return await self._client.request(method, url, json=payload)
            async with httpx.AsyncClient(timeout=self.settings.spfa_timeout_seconds) as client:
                return await client.request(method, url, json=payload)
        except httpx.HTTPError as error:
            # тело ответа может содержать api key, поэтому наружу идёт только тип ошибки
            raise CookieProviderError(f"spfa request failed: {type(error).__name__}") from error

    @staticmethod
    def _payload(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _results(self, response: httpx.Response) -> dict[str, Any]:
        results = self._payload(response).get("results")
        return results if isinstance(results, dict) else {}

    def _load(self) -> None:
        if not self.storage_path.exists():
            return
        try:
            raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            logger.warning("spfa cookie storage unreadable: {error}", error=error)
            return
        if not isinstance(raw, dict):
            return

        bundle = raw.get("bundle")
        if isinstance(bundle, dict):
            try:
                self._bundle = CookieBundle.model_validate(bundle)
            except ValueError as error:
                logger.warning("stored spfa bundle rejected: {error}", error=error)

        last_purchase = raw.get("last_purchase_at")
        if isinstance(last_purchase, str):
            try:
                self._last_purchase_at = datetime.fromisoformat(last_purchase)
            except ValueError:
                self._last_purchase_at = None

        day = raw.get("purchase_day")
        if isinstance(day, str):
            try:
                self._purchase_day = date.fromisoformat(day)
            except ValueError:
                self._purchase_day = None

        count = raw.get("purchases_today")
        self._purchases_today = count if isinstance(count, int) and count >= 0 else 0

    def _save(self) -> None:
        payload = {
            "bundle": self._bundle.model_dump(mode="json") if self._bundle else None,
            "last_purchase_at": (
                self._last_purchase_at.isoformat() if self._last_purchase_at else None
            ),
            "purchase_day": self._purchase_day.isoformat() if self._purchase_day else None,
            "purchases_today": self._purchases_today,
        }
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.storage_path.with_suffix(self.storage_path.suffix + ".tmp")
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temp_path.replace(self.storage_path)
        except OSError as error:
            logger.warning("spfa cookie storage not written: {error}", error=error)
