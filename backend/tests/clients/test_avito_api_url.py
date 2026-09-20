from pathlib import Path

import httpx
import pytest

from app.clients.avito.api_url import AvitoApiUrlError, AvitoApiUrlResolver
from app.config import Settings

CATEGORY_URL = "https://www.avito.ru/all/remont_i_stroitelstvo/banya-ASgBAgICAkRYlrI68I4O2o_OAQ"
API_URL = "https://www.avito.ru/web/1/js/items?categoryId=19&locationId=621540"


class Counter:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return self.response


def build(tmp_path: Path, response: httpx.Response) -> tuple[AvitoApiUrlResolver, Counter]:
    counter = Counter(response)
    settings = Settings(parser_api_url_cache_path=str(tmp_path / "api_urls.json"))
    resolver = AvitoApiUrlResolver(
        settings=settings,
        client=httpx.AsyncClient(transport=httpx.MockTransport(counter.handler)),
    )
    return resolver, counter


async def test_resolve_returns_the_api_url(tmp_path: Path) -> None:
    resolver, _ = build(tmp_path, httpx.Response(200, json={"success": True, "api_url": API_URL}))

    assert await resolver.resolve(CATEGORY_URL) == API_URL


async def test_resolve_is_cached_in_memory(tmp_path: Path) -> None:
    resolver, counter = build(
        tmp_path, httpx.Response(200, json={"success": True, "api_url": API_URL})
    )

    await resolver.resolve(CATEGORY_URL)
    await resolver.resolve(CATEGORY_URL)

    assert counter.calls == 1


async def test_cache_survives_a_restart(tmp_path: Path) -> None:
    resolver, _ = build(tmp_path, httpx.Response(200, json={"success": True, "api_url": API_URL}))
    await resolver.resolve(CATEGORY_URL)

    # конвертация ограничена двумя запросами в минуту, поэтому кеш вечный (§27.2)
    restarted, counter = build(tmp_path, httpx.Response(503))

    assert await restarted.resolve(CATEGORY_URL) == API_URL
    assert counter.calls == 0


async def test_rate_limit_is_reported(tmp_path: Path) -> None:
    resolver, _ = build(tmp_path, httpx.Response(429, json={"success": False}))

    with pytest.raises(AvitoApiUrlError) as error:
        await resolver.resolve(CATEGORY_URL)

    assert error.value.status_code == 429


async def test_unsuccessful_payload_is_rejected(tmp_path: Path) -> None:
    resolver, _ = build(tmp_path, httpx.Response(200, json={"success": False}))

    with pytest.raises(AvitoApiUrlError, match="no api_url"):
        await resolver.resolve(CATEGORY_URL)


async def test_non_json_answer_is_rejected(tmp_path: Path) -> None:
    resolver, _ = build(tmp_path, httpx.Response(200, text="<html>nope</html>"))

    with pytest.raises(AvitoApiUrlError, match="no json"):
        await resolver.resolve(CATEGORY_URL)


async def test_broken_cache_file_does_not_break_resolving(tmp_path: Path) -> None:
    cache = tmp_path / "api_urls.json"
    cache.write_text("{not json", encoding="utf-8")
    resolver, _ = build(tmp_path, httpx.Response(200, json={"success": True, "api_url": API_URL}))

    assert await resolver.resolve(CATEGORY_URL) == API_URL
