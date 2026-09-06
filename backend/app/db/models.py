from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class AccountStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    BANNED = "banned"


class BlockKind(StrEnum):
    NONE = "none"
    CAPTCHA = "captcha"
    RATE_LIMITED = "rate_limited"
    FORBIDDEN = "forbidden"
    AUTH_REQUIRED = "auth_required"
    UNAVAILABLE = "unavailable"


class SellerStatus(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    INTERESTED = "interested"
    LEAD = "lead"
    REJECTED = "rejected"


class MessageStatus(StrEnum):
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class Sentiment(StrEnum):
    INTERESTED = "interested"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


def _enum_column(enum_cls: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        values_callable=lambda e: [m.value for m in e],
    )


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    login: Mapped[str] = mapped_column(String(255), unique=True)
    session_storage_path: Mapped[str] = mapped_column(String(512))
    status: Mapped[AccountStatus] = mapped_column(
        _enum_column(AccountStatus, "account_status"), default=AccountStatus.ACTIVE
    )
    daily_message_count: Mapped[int] = mapped_column(Integer, default=0)
    daily_limit: Mapped[int] = mapped_column(Integer, default=15)
    last_reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    proxy_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    paused_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_block_kind: Mapped[BlockKind | None] = mapped_column(
        _enum_column(BlockKind, "block_kind"), nullable=True
    )
    last_block_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    avito_url_or_slug: Mapped[str] = mapped_column(String(512))
    region: Mapped[str] = mapped_column(String(255))
    min_listings_per_seller: Mapped[int] = mapped_column(Integer, default=3)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    sellers: Mapped[list["Seller"]] = relationship(back_populates="category")


class Seller(Base):
    __tablename__ = "sellers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    avito_seller_id: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    profile_url: Mapped[str] = mapped_column(String(512))
    listings_count: Mapped[int] = mapped_column(Integer, default=0)
    region: Mapped[str] = mapped_column(String(255))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    status: Mapped[SellerStatus] = mapped_column(
        _enum_column(SellerStatus, "seller_status"), default=SellerStatus.NEW
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    category: Mapped[Category] = relationship(back_populates="sellers")
    listings: Mapped[list["Listing"]] = relationship(back_populates="seller")


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id", ondelete="CASCADE"))
    avito_listing_id: Mapped[str] = mapped_column(String(255), unique=True)
    title: Mapped[str] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(String(512))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    region: Mapped[str] = mapped_column(String(255))
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parsed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    seller: Mapped[Seller] = relationship(back_populates="listings")


class Script(Base):
    __tablename__ = "scripts"
    __table_args__ = (
        UniqueConstraint("stage", "variant_index", name="uq_scripts_stage_variant"),
        CheckConstraint("stage BETWEEN 1 AND 3", name="ck_scripts_stage"),
        CheckConstraint("variant_index BETWEEN 1 AND 5", name="ck_scripts_variant_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stage: Mapped[int] = mapped_column(Integer)
    variant_index: Mapped[int] = mapped_column(Integer)
    template_text: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class MessageLog(Base):
    __tablename__ = "message_log"
    __table_args__ = (
        UniqueConstraint("seller_id", "stage", name="uq_message_log_seller_stage"),
        CheckConstraint("stage BETWEEN 1 AND 3", name="ck_message_log_stage"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id", ondelete="CASCADE"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    stage: Mapped[int] = mapped_column(Integer)
    variant_used: Mapped[int] = mapped_column(Integer)
    final_text: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[MessageStatus] = mapped_column(
        _enum_column(MessageStatus, "message_status"), default=MessageStatus.SENT
    )


class Reply(Base):
    __tablename__ = "replies"
    __table_args__ = (UniqueConstraint("external_id", name="uq_replies_external_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id", ondelete="CASCADE"))
    message_log_id: Mapped[int] = mapped_column(ForeignKey("message_log.id", ondelete="CASCADE"))
    reply_text: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ai_sentiment: Mapped[Sentiment | None] = mapped_column(
        _enum_column(Sentiment, "ai_sentiment"), nullable=True
    )
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (UniqueConstraint("reply_id", name="uq_leads_reply_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id", ondelete="CASCADE"))
    reply_id: Mapped[int] = mapped_column(ForeignKey("replies.id", ondelete="CASCADE"))
    sent_to_telegram_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    conversation_history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class ScheduleSettings(Base):
    __tablename__ = "schedule_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    window_start: Mapped[int] = mapped_column(Integer, default=9)
    window_end: Mapped[int] = mapped_column(Integer, default=21)
    weekdays_enabled: Mapped[list[int]] = mapped_column(JSON, default=lambda: [0, 1, 2, 3, 4])
    paused: Mapped[bool] = mapped_column(Boolean, default=False)


class AppSettings(Base):
    __tablename__ = "app_settings"
    __table_args__ = (
        CheckConstraint("account_rotation_size BETWEEN 2 AND 3", name="ck_app_settings_rotation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delay_min_minutes: Mapped[int] = mapped_column(Integer, default=5)
    delay_max_minutes: Mapped[int] = mapped_column(Integer, default=15)
    account_rotation_size: Mapped[int] = mapped_column(Integer, default=3)
