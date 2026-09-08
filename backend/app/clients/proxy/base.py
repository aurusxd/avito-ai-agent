from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

ProxyTypeLiteral = Literal["mobile", "residential", "datacenter"]
SessionTypeLiteral = Literal["nosession", "session", "hardsession"]
ProtocolLiteral = Literal["http", "socks5"]

LIFETIME_MAX_MINUTES = 10_080


class ProxyProviderError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ProxyBalance(BaseModel):
    proxy_type: ProxyTypeLiteral
    network: Literal["core", "extended"]
    remaining_mb: float = Field(ge=0)
    traffic_ready: bool = False


class ProxyGenerateRequest(BaseModel):
    proxy_type: ProxyTypeLiteral = "residential"
    country: str = Field(default="RU", min_length=2, max_length=2)
    city: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    isp: str | None = Field(default=None, max_length=120)
    session_type: SessionTypeLiteral = "session"
    lifetime_minutes: int = Field(default=LIFETIME_MAX_MINUTES, ge=1, le=LIFETIME_MAX_MINUTES)
    quantity: int = Field(default=1, ge=1, le=1000)
    protocol: ProtocolLiteral = "http"


class GeneratedProxy(BaseModel):
    # url carries credentials, so it never goes to a log or a list response
    url: str = Field(min_length=1)
    masked_url: str = Field(min_length=1)
    session_id: str | None = None


@runtime_checkable
class ProxyProvider(Protocol):
    async def balances(self) -> list[ProxyBalance]: ...

    async def generate(self, request: ProxyGenerateRequest) -> list[GeneratedProxy]: ...

    async def options(
        self, proxy_type: ProxyTypeLiteral, field: str, country: str | None = None
    ) -> list[str]: ...
