import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.clients.cookies.base import (
    CookieBudgetExhaustedError,
    CookieProvider,
    CookieProviderError,
)
from app.clients.cookies.fake import FakeCookieProvider
from app.clients.cookies.none import NoCookieProvider
from app.clients.cookies.spfa import SpfaCookieProvider
from app.config import Settings

PROXY = "http://user:se%3Acret@res.lteboost.com:1000"

BOUGHT = {
    "success": True,
    "results": {
        "id": 187853,
        "cookies": {"srv_id": "first", "pow_solved": "1"},
        "user_agent": "Mozilla/5.0 (Linux; Android 13) Mobile Safari/537.36",
        "fingerprint": {
            "client": "curl_cffi",
            "impersonate": "chrome131_android",
            "headers": {
                "sec-ch-ua-mobile": "?1",
                "user-agent": "Mozilla/5.0 (Linux; Android 13) Mobile Safari/537.36",
            },
        },
        "mobile": True,
    },
}


class Recorder:
    """Отдаёт заготовленные ответы и запоминает, куда и с чем ходили."""

    def __init__(self, responses: dict[str, list[httpx.Response]]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append((path, json.loads(request.content or b"{}")))
        queue = self.responses.get(path)
        if not queue:
            return httpx.Response(503, json={"success": False})
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def paths(self) -> list[str]:
        return [path for path, _ in self.calls]


def build(
    tmp_path: Path,
    responses: dict[str, list[httpx.Response]],
    *,
    proxy: str = PROXY,
    cooldown: int = 600,
    daily_cap: int = 12,
) -> tuple[SpfaCookieProvider, Recorder]:
    recorder = Recorder(responses)
    settings = Settings(
        spfa_api_key="test-key",
        spfa_base_url="https://spfa.pro/api",
        spfa_purchase_cooldown_seconds=cooldown,
        spfa_max_purchases_per_day=daily_cap,
        spfa_cookie_storage_path=str(tmp_path / "cookies.json"),
        parser_proxy_url=proxy,
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(recorder.handler))
    return SpfaCookieProvider(settings=settings, client=client), recorder


def test_providers_satisfy_the_protocol() -> None:
    assert isinstance(NoCookieProvider(), CookieProvider)
    assert isinstance(FakeCookieProvider(), CookieProvider)


async def test_purchase_reads_cookies_and_fingerprint(tmp_path: Path) -> None:
    provider, _ = build(tmp_path, {"/api/cookies/mobile/": [httpx.Response(200, json=BOUGHT)]})

    bundle = await provider.get()

    assert bundle.id == 187853
    assert bundle.cookies == {"srv_id": "first", "pow_solved": "1"}
    assert bundle.impersonate == "chrome131_android"
    assert bundle.headers["sec-ch-ua-mobile"] == "?1"
    assert bundle.mobile is True
    assert bundle.empty is False


async def test_purchase_sends_the_decoded_proxy_line(tmp_path: Path) -> None:
    provider, recorder = build(
        tmp_path, {"/api/cookies/mobile/": [httpx.Response(200, json=BOUGHT)]}
    )

    await provider.get()

    _, payload = recorder.calls[0]
    # сервис ждёт login:password@host:port и не принимает percent-encoding
    assert payload["proxy"] == "user:se:cret@res.lteboost.com:1000"
    assert payload["api_key"] == "test-key"


async def test_cached_bundle_is_reused_without_buying_again(tmp_path: Path) -> None:
    provider, recorder = build(
        tmp_path, {"/api/cookies/mobile/": [httpx.Response(200, json=BOUGHT)]}
    )

    first = await provider.get()
    second = await provider.get()

    assert first == second
    assert recorder.paths() == ["/api/cookies/mobile/"]


async def test_bundle_survives_a_restart(tmp_path: Path) -> None:
    provider, _ = build(tmp_path, {"/api/cookies/mobile/": [httpx.Response(200, json=BOUGHT)]})
    bought = await provider.get()

    # перезапуск контейнера не должен сжигать уже купленную куку
    restarted, recorder = build(tmp_path, {})
    restored = await restarted.get()

    assert restored.id == bought.id
    assert restored.cookies == bought.cookies
    assert recorder.calls == []


async def test_refresh_updates_cookies_without_a_purchase(tmp_path: Path) -> None:
    unblocked = {"success": True, "results": {"id": 187853, "cookies": {"srv_id": "second"}}}
    provider, recorder = build(
        tmp_path,
        {
            "/api/cookies/mobile/": [httpx.Response(200, json=BOUGHT)],
            "/api/unblock/": [httpx.Response(202, json=unblocked)],
        },
    )
    await provider.get()

    refreshed = await provider.refresh()

    assert refreshed is not None
    assert refreshed.cookies["srv_id"] == "second"
    assert recorder.paths().count("/api/cookies/mobile/") == 1


async def test_refresh_without_a_bundle_does_nothing(tmp_path: Path) -> None:
    provider, recorder = build(tmp_path, {})

    assert await provider.refresh() is None
    assert recorder.calls == []


async def test_dead_cookie_is_dropped(tmp_path: Path) -> None:
    provider, _ = build(
        tmp_path,
        {
            "/api/cookies/mobile/": [httpx.Response(200, json=BOUGHT)],
            "/api/unblock/": [httpx.Response(410, json={"success": False})],
        },
    )
    await provider.get()

    assert await provider.refresh() is None
    # кука выброшена, следующий get() пойдёт покупать
    with pytest.raises(CookieBudgetExhaustedError):
        await provider.get()


async def test_refresh_keeps_the_bundle_when_the_service_returns_no_cookies(
    tmp_path: Path,
) -> None:
    provider, _ = build(
        tmp_path,
        {
            "/api/cookies/mobile/": [httpx.Response(200, json=BOUGHT)],
            "/api/unblock/": [httpx.Response(202, json={"success": True})],
        },
    )
    bought = await provider.get()

    refreshed = await provider.refresh()

    assert refreshed is not None
    assert refreshed.cookies == bought.cookies


async def test_cooldown_blocks_the_second_purchase(tmp_path: Path) -> None:
    provider, _ = build(
        tmp_path, {"/api/cookies/mobile/": [httpx.Response(200, json=BOUGHT)]}, cooldown=600
    )
    await provider.get()
    await provider.invalidate()

    with pytest.raises(CookieBudgetExhaustedError, match="cooldown"):
        await provider.get()


async def test_daily_cap_stops_buying(tmp_path: Path) -> None:
    provider, _ = build(
        tmp_path,
        {"/api/cookies/mobile/": [httpx.Response(200, json=BOUGHT)]},
        cooldown=0,
        daily_cap=1,
    )
    await provider.get()
    await provider.invalidate()

    with pytest.raises(CookieBudgetExhaustedError, match="daily cap"):
        await provider.get()


async def test_daily_cap_survives_a_restart(tmp_path: Path) -> None:
    provider, _ = build(
        tmp_path,
        {"/api/cookies/mobile/": [httpx.Response(200, json=BOUGHT)]},
        cooldown=0,
        daily_cap=1,
    )
    await provider.get()

    # счётчик покупок лежит на диске, иначе рестарт обнулял бы потолок
    restarted, _ = build(
        tmp_path,
        {"/api/cookies/mobile/": [httpx.Response(200, json=BOUGHT)]},
        cooldown=0,
        daily_cap=1,
    )
    await restarted.invalidate()

    with pytest.raises(CookieBudgetExhaustedError, match="daily cap"):
        await restarted.get()


async def test_purchase_without_a_proxy_is_refused(tmp_path: Path) -> None:
    provider, recorder = build(tmp_path, {}, proxy="")

    with pytest.raises(CookieProviderError, match="parser proxy"):
        await provider.get()
    assert recorder.calls == []


async def test_missing_api_key_is_reported(tmp_path: Path) -> None:
    settings = Settings(
        spfa_api_key="",
        spfa_cookie_storage_path=str(tmp_path / "cookies.json"),
        parser_proxy_url=PROXY,
    )
    recorder = Recorder({})
    provider = SpfaCookieProvider(
        settings=settings,
        client=httpx.AsyncClient(transport=httpx.MockTransport(recorder.handler)),
    )

    with pytest.raises(CookieProviderError, match="SPFA_API_KEY"):
        await provider.get()


async def test_refused_purchase_raises(tmp_path: Path) -> None:
    provider, _ = build(
        tmp_path, {"/api/cookies/mobile/": [httpx.Response(403, json={"success": False})]}
    )

    with pytest.raises(CookieProviderError, match="403"):
        await provider.get()


async def test_empty_cookie_payload_raises(tmp_path: Path) -> None:
    provider, _ = build(
        tmp_path,
        {"/api/cookies/mobile/": [httpx.Response(200, json={"success": True, "results": {}})]},
    )

    with pytest.raises(CookieProviderError, match="no cookies"):
        await provider.get()


async def test_balance_is_read(tmp_path: Path) -> None:
    provider, _ = build(
        tmp_path, {"/api/balance/": [httpx.Response(200, json={"success": True, "balance": 44.0})]}
    )

    assert await provider.balance() == pytest.approx(44.0)
