from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.domain.auth_session import LoginStatusLiteral
from app.domain.rotation import BlockKindLiteral
from app.domain.schemas import CategoryDTO, ListingDTO, MessageStatusLiteral, SellerDTO


class ParserResult(BaseModel):
    seller: SellerDTO
    listings: list[ListingDTO] = Field(default_factory=list)


class SendResult(BaseModel):
    status: MessageStatusLiteral
    sent_at: datetime
    error: str | None = None
    block_kind: BlockKindLiteral = "none"
    retry_after_seconds: int | None = Field(default=None, ge=0)

    @property
    def transport_blocked(self) -> bool:
        return self.block_kind != "none"


class AvitoBlockedError(RuntimeError):
    block_kind: BlockKindLiteral
    retry_after_seconds: int | None

    def __init__(
        self,
        message: str,
        block_kind: BlockKindLiteral = "forbidden",
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.block_kind = block_kind
        self.retry_after_seconds = retry_after_seconds


class IncomingReplyDTO(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    avito_seller_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    received_at: datetime
    chat_url: str | None = None


class AvitoAccountRef(BaseModel):
    id: int = Field(ge=1)
    login: str = Field(min_length=1)
    session_storage_path: str = Field(min_length=1)
    proxy_url: str | None = None


@runtime_checkable
class AvitoClient(Protocol):
    async def parse_category(self, category: CategoryDTO) -> list[ParserResult]: ...

    async def send_message(
        self, account: AvitoAccountRef, seller: SellerDTO, text: str
    ) -> SendResult: ...

    async def fetch_replies(
        self, account: AvitoAccountRef, limit: int = 50
    ) -> list[IncomingReplyDTO]: ...


class LoginStep(BaseModel):
    status: LoginStatusLiteral
    hint: str | None = None


@runtime_checkable
class AvitoAuthClient(Protocol):
    async def start(self, login: str, password: str, proxy_url: str | None = None) -> LoginStep: ...

    async def resume(self, login: str, password: str) -> LoginStep: ...

    async def submit_code(self, code: str) -> LoginStep: ...

    async def storage_state(self) -> dict[str, object]: ...

    async def screenshot(self) -> bytes | None: ...

    async def close(self) -> None: ...
