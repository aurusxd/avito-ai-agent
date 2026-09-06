from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

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
    def __init__(
        self,
        message: str,
        block_kind: BlockKindLiteral = "forbidden",
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.block_kind = block_kind
        self.retry_after_seconds = retry_after_seconds


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
