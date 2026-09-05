from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Stage = Literal[1, 2, 3]
SellerStatusLiteral = Literal["new", "contacted", "interested", "lead", "rejected"]
MessageStatusLiteral = Literal["sent", "failed", "skipped"]
SentimentLiteral = Literal["interested", "neutral", "negative"]
MessageRole = Literal["bot", "seller"]


class CategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    avito_url_or_slug: str = Field(min_length=1, max_length=512)
    region: str = Field(min_length=1, max_length=255)
    min_listings_per_seller: int = Field(default=3, ge=1)
    enabled: bool = True


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    avito_url_or_slug: str | None = Field(default=None, min_length=1, max_length=512)
    region: str | None = Field(default=None, min_length=1, max_length=255)
    min_listings_per_seller: int | None = Field(default=None, ge=1)
    enabled: bool | None = None


class CategoryDTO(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class SellerDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    avito_seller_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    profile_url: str = Field(min_length=1)
    listings_count: int = Field(ge=0)
    region: str = Field(min_length=1)
    status: SellerStatusLiteral = "new"


class ListingDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    avito_listing_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    region: str = Field(min_length=1)
    price: int | None = Field(default=None, ge=0)


class MessageDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: MessageRole
    text: str
    stage: Stage | None = None
    sent_at: datetime


class OutreachJob(BaseModel):
    seller_id: int = Field(ge=1)
    stage: Stage
    account_id: int = Field(ge=1)
