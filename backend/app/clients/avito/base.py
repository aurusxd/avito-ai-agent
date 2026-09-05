from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.domain.schemas import CategoryDTO, ListingDTO, MessageStatusLiteral, SellerDTO


class ParserResult(BaseModel):
    seller: SellerDTO
    listings: list[ListingDTO] = Field(default_factory=list)


class SendResult(BaseModel):
    status: MessageStatusLiteral
    sent_at: datetime
    error: str | None = None


class AvitoAccountRef(BaseModel):
    id: int = Field(ge=1)
    login: str = Field(min_length=1)
    session_storage_path: str = Field(min_length=1)


@runtime_checkable
class AvitoClient(Protocol):
    async def parse_category(self, category: CategoryDTO) -> list[ParserResult]: ...

    async def send_message(
        self, account: AvitoAccountRef, seller: SellerDTO, text: str
    ) -> SendResult: ...
