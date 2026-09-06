from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.rotation import MAX_DAILY_LIMIT, AccountStatusLiteral, BlockKindLiteral
from app.domain.variation import VariationSourceLiteral

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


class SellerRead(SellerDTO):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    created_at: datetime


class ListingRead(ListingDTO):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seller_id: int
    category_id: int
    parsed_at: datetime


class ParserRunResult(BaseModel):
    category_id: int
    sellers_matched: int = 0
    sellers_created: int = 0
    sellers_updated: int = 0
    listings_created: int = 0
    listings_updated: int = 0


class AccountBase(BaseModel):
    login: str = Field(min_length=1, max_length=255)
    session_storage_path: str = Field(min_length=1, max_length=512)
    daily_limit: int = Field(default=MAX_DAILY_LIMIT, ge=1, le=MAX_DAILY_LIMIT)
    proxy_url: str | None = Field(default=None, max_length=512)


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    login: str | None = Field(default=None, min_length=1, max_length=255)
    session_storage_path: str | None = Field(default=None, min_length=1, max_length=512)
    daily_limit: int | None = Field(default=None, ge=1, le=MAX_DAILY_LIMIT)
    status: AccountStatusLiteral | None = None
    proxy_url: str | None = Field(default=None, max_length=512)


class AccountRead(AccountBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: AccountStatusLiteral
    daily_message_count: int
    remaining_today: int
    has_session: bool
    has_proxy: bool
    last_reset_at: datetime
    created_at: datetime
    paused_until: datetime | None = None
    last_block_kind: BlockKindLiteral | None = None
    last_block_at: datetime | None = None


class RotationMember(BaseModel):
    account_id: int
    login: str
    status: AccountStatusLiteral
    remaining_today: int
    in_rotation: bool
    available: bool
    paused_until: datetime | None = None


class RotationPreview(BaseModel):
    rotation_size: int
    delay_min_minutes: int
    delay_max_minutes: int
    daily_limit: int
    next_account_id: int | None = None
    capacity_today: int = 0
    members: list[RotationMember] = Field(default_factory=list)


class OutreachRequest(BaseModel):
    seller_id: int = Field(ge=1)
    stage: Stage
    account_id: int | None = Field(default=None, ge=1)


class OutreachResult(BaseModel):
    seller_id: int
    stage: Stage
    status: MessageStatusLiteral
    account_id: int | None = None
    message_log_id: int | None = None
    variant_used: int | None = None
    block_kind: BlockKindLiteral = "none"
    reason: str | None = None
    already_sent: bool = False


class MessageLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seller_id: int
    account_id: int
    stage: Stage
    variant_used: int
    final_text: str
    sent_at: datetime
    status: MessageStatusLiteral


class VariationRequest(BaseModel):
    seller_id: int = Field(ge=1)
    stage: Stage
    variant_index: int | None = Field(default=None, ge=1, le=5)


class VariationResult(BaseModel):
    seller_id: int
    stage: Stage
    variant_used: int
    template_text: str
    final_text: str
    source: VariationSourceLiteral
    provider: str | None = None
    reason: str | None = None
