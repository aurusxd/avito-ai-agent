from loguru import logger

from app.clients.proxy.base import (
    ProxyGenerateRequest,
    ProxyProvider,
    ProxyProviderError,
    ProxyTypeLiteral,
)
from app.config import Settings
from app.domain.schemas import ProxyBalanceRead, ProxyIssueRequest, ProxyIssueResult
from app.errors import AppError

MB_IN_GB = 1024.0


class ProxyService:
    def __init__(self, provider: ProxyProvider, settings: Settings) -> None:
        self.provider = provider
        self.settings = settings

    async def balances(self) -> list[ProxyBalanceRead]:
        rows = await self._call(self.provider.balances())
        return [
            ProxyBalanceRead(
                proxy_type=row.proxy_type,
                network=row.network,
                remaining_mb=row.remaining_mb,
                remaining_gb=round(row.remaining_mb / MB_IN_GB, 3),
                traffic_ready=row.traffic_ready,
            )
            for row in rows
        ]

    async def issue(self, request: ProxyIssueRequest) -> ProxyIssueResult:
        payload = ProxyIssueRequest.model_validate(request)
        generate = ProxyGenerateRequest(
            proxy_type=payload.proxy_type or self.settings.proxy_default_type,  # type: ignore[arg-type]
            country=payload.country or self.settings.proxy_default_country,
            city=payload.city,
            isp=payload.isp,
            session_type="session",
            lifetime_minutes=payload.lifetime_minutes
            or self.settings.proxy_default_lifetime_minutes,
            quantity=1,
        )

        generated = await self._call(self.provider.generate(generate))
        proxy = generated[0]

        logger.info(
            "issued a sticky proxy {masked} for {minutes} min",
            masked=proxy.masked_url,
            minutes=generate.lifetime_minutes,
        )

        return ProxyIssueResult(
            url=proxy.url,
            masked_url=proxy.masked_url,
            session_id=proxy.session_id,
            lifetime_minutes=generate.lifetime_minutes,
            country=generate.country,
            city=generate.city,
        )

    async def options(self, field: str, country: str | None = None) -> list[str]:
        proxy_type: ProxyTypeLiteral = self.settings.proxy_default_type
        return await self._call(self.provider.options(proxy_type, field, country))

    async def _call[T](self, awaitable):
        try:
            return await awaitable
        except ProxyProviderError as error:
            raise AppError(str(error)) from error
