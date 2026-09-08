from app.clients.proxy.base import (
    GeneratedProxy,
    ProxyBalance,
    ProxyGenerateRequest,
    ProxyProviderError,
    ProxyTypeLiteral,
)
from app.domain.proxy import line_to_url, mask_proxy_url, session_id_from_line

SEED_BALANCES = [
    ProxyBalance(proxy_type="residential", network="core", remaining_mb=1000.0, traffic_ready=True),
    ProxyBalance(proxy_type="mobile", network="core", remaining_mb=0.0, traffic_ready=False),
]

SEED_OPTIONS = {
    "country": ["RU", "KZ", "BY"],
    "city": ["Moscow", "St Petersburg", "Novosibirsk"],
}


class FakeProxyProvider:
    provider = "fake"

    def __init__(self, failure: Exception | None = None, fail_times: int = 0) -> None:
        self.failure = failure
        self.fail_times = fail_times
        self.requests: list[ProxyGenerateRequest] = []

    def _maybe_fail(self) -> None:
        if self.failure is not None and self.fail_times > 0:
            self.fail_times -= 1
            raise self.failure

    async def balances(self) -> list[ProxyBalance]:
        self._maybe_fail()
        return list(SEED_BALANCES)

    async def generate(self, request: ProxyGenerateRequest) -> list[GeneratedProxy]:
        payload = ProxyGenerateRequest.model_validate(request)
        self.requests.append(payload)
        self._maybe_fail()

        if payload.country == "ZZ":
            raise ProxyProviderError("the provider returned no proxies for these filters")

        generated: list[GeneratedProxy] = []
        for index in range(payload.quantity):
            password = (
                f"seedpass_country-{payload.country}"
                f"_lifetime-{payload.lifetime_minutes}_session-fake{index}"
            )
            line = f"res.example.com:1000:seed_login:{password}"
            url = line_to_url(line, payload.protocol)
            assert url is not None
            generated.append(
                GeneratedProxy(
                    url=url,
                    masked_url=mask_proxy_url(url) or "",
                    session_id=session_id_from_line(line),
                )
            )
        return generated

    async def options(
        self, proxy_type: ProxyTypeLiteral, field: str, country: str | None = None
    ) -> list[str]:
        self._maybe_fail()
        return list(SEED_OPTIONS.get(field, []))
