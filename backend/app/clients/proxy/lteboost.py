from typing import Any

import httpx
from loguru import logger

from app.clients.proxy.base import (
    GeneratedProxy,
    ProxyBalance,
    ProxyGenerateRequest,
    ProxyProviderError,
    ProxyTypeLiteral,
)
from app.config import Settings, get_settings
from app.domain.proxy import line_to_url, mask_proxy_url, session_id_from_line

NETWORKS = ("core", "extended")


class LteboostProxyProvider:
    """Client for the lteboost cabinet api.

    Response shapes were taken from the live api, not from the docs page: the
    balance is a nested dict per proxy type, and generated lines carry their
    sticky options inside the password.
    """

    provider = "lteboost"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.proxy_api_base_url.rstrip("/")

    async def balances(self) -> list[ProxyBalance]:
        payload = await self._request("GET", "/balance")
        rows: list[ProxyBalance] = []

        for proxy_type, values in (payload.get("balances") or {}).items():
            if proxy_type not in ("mobile", "residential", "datacenter"):
                continue
            for network in NETWORKS:
                megabytes = values.get(f"{network}_mb")
                if megabytes is None:
                    continue
                rows.append(
                    ProxyBalance(
                        proxy_type=proxy_type,
                        network=network,
                        remaining_mb=float(megabytes),
                        traffic_ready=bool(values.get("traffic_ready", False)),
                    )
                )
        return rows

    async def generate(self, request: ProxyGenerateRequest) -> list[GeneratedProxy]:
        payload = ProxyGenerateRequest.model_validate(request)
        body: dict[str, Any] = {
            "proxy_type": payload.proxy_type,
            "country": payload.country,
            "session_type": payload.session_type,
            "lifetime": payload.lifetime_minutes,
            "quantity": payload.quantity,
            "protocol": payload.protocol,
            "format": "ip:port:login:pass",
        }
        for field in ("city", "region", "isp"):
            value = getattr(payload, field)
            if value:
                body[field] = value

        response = await self._request("POST", "/proxies/generate", json=body)
        lines = response.get("proxies") or []
        if not lines:
            raise ProxyProviderError("the provider returned no proxies for these filters")

        generated: list[GeneratedProxy] = []
        for line in lines:
            url = line_to_url(str(line), payload.protocol)
            if url is None:
                logger.warning("provider returned a line that is not host:port:login:pass")
                continue
            generated.append(
                GeneratedProxy(
                    url=url,
                    masked_url=mask_proxy_url(url) or "",
                    session_id=session_id_from_line(str(line)),
                )
            )

        if not generated:
            raise ProxyProviderError("could not read any proxy line the provider returned")
        return generated

    async def options(
        self, proxy_type: ProxyTypeLiteral, field: str, country: str | None = None
    ) -> list[str]:
        params: dict[str, str] = {"proxy_type": proxy_type, "field": field}
        if country:
            params["country"] = country
        payload = await self._request("GET", "/proxy-options", params=params)
        return [str(option) for option in payload.get("options") or []]

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.settings.proxy_api_key:
            raise ProxyProviderError("PROXY_API_KEY is empty, the provider api is not configured")

        headers = {"Authorization": f"Bearer {self.settings.proxy_api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self.settings.proxy_api_timeout_seconds) as client:
                response = await client.request(
                    method, f"{self.base_url}{path}", headers=headers, params=params, json=json
                )
        except httpx.HTTPError as error:
            raise ProxyProviderError(
                f"proxy provider is unreachable: {type(error).__name__}"
            ) from error

        if response.status_code >= 400:
            # the body can echo the key back, so only the status goes out
            logger.warning(
                "proxy provider answered {status} on {path}",
                status=response.status_code,
                path=path,
            )
            raise ProxyProviderError(
                f"proxy provider answered {response.status_code}", response.status_code
            )

        try:
            payload = response.json()
        except ValueError as error:
            raise ProxyProviderError("proxy provider returned a non json body") from error

        if not isinstance(payload, dict):
            raise ProxyProviderError("proxy provider returned an unexpected body")
        return payload
