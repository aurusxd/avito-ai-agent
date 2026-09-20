import json
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from app.config import Settings, get_settings


class AvitoApiUrlError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AvitoApiUrlResolver:
    """Превращает ссылку категории в ссылку JSON-выдачи (§27.2).

    Конвертация бесплатна, но ограничена двумя запросами в минуту с ip, поэтому
    результат кешируется на диск навсегда: параметры поиска категории не меняются.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.endpoint = f"{self.settings.spfa_base_url.rstrip('/')}/avito-url/"
        self.cache_path = Path(self.settings.parser_api_url_cache_path)
        self._client = client
        self._cache = self._load()

    async def resolve(self, category_url: str) -> str:
        cached = self._cache.get(category_url)
        if cached:
            return cached

        try:
            response = await self._post({"url": category_url})
        except httpx.HTTPError as error:
            raise AvitoApiUrlError(f"api url request failed: {type(error).__name__}") from error

        if response.status_code != 200:
            raise AvitoApiUrlError(
                f"api url conversion returned {response.status_code}", response.status_code
            )

        payload: dict[str, Any]
        try:
            raw = response.json()
        except ValueError as error:
            raise AvitoApiUrlError("api url conversion returned no json") from error
        payload = raw if isinstance(raw, dict) else {}

        api_url = payload.get("api_url")
        if not payload.get("success") or not isinstance(api_url, str) or not api_url:
            raise AvitoApiUrlError("api url conversion returned no api_url")

        self._cache[category_url] = api_url
        self._save()
        logger.info("category url converted to api url: {url}", url=category_url)
        return api_url

    async def _post(self, payload: dict[str, Any]) -> httpx.Response:
        if self._client is not None:
            return await self._client.post(self.endpoint, json=payload)
        async with httpx.AsyncClient(timeout=self.settings.spfa_timeout_seconds) as client:
            return await client.post(self.endpoint, json=payload)

    def _load(self) -> dict[str, str]:
        if not self.cache_path.exists():
            return {}
        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            logger.warning("api url cache unreadable: {error}", error=error)
            return {}
        if not isinstance(raw, dict):
            return {}
        return {str(key): str(value) for key, value in raw.items() if key and value}

    def _save(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
            temp_path.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temp_path.replace(self.cache_path)
        except OSError as error:
            logger.warning("api url cache not written: {error}", error=error)
