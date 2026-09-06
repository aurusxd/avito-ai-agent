from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.service import AccountService
from app.config import Settings
from app.db.models import (
    Account,
    AccountStatus,
    Category,
    Lead,
    MessageLog,
    MessageStatus,
    Reply,
    Seller,
    SellerStatus,
)
from app.domain.schemas import DashboardStats, StageStat
from app.settings_admin.service import BotSettingsService

STAGES = (1, 2, 3)


class DashboardService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.timezone = ZoneInfo(settings.timezone)

    async def stats(self) -> DashboardStats:
        bot_settings = await BotSettingsService(self.session, self.settings).read()
        rotation = await AccountService(self.session, self.settings).rotation_preview()

        return DashboardStats(
            categories_enabled=await self._count(Category, Category.enabled.is_(True)),
            sellers_total=await self._count(Seller),
            sellers_contacted=await self._count(Seller, Seller.status != SellerStatus.NEW),
            sellers_interested=await self._count(Seller, Seller.status == SellerStatus.INTERESTED),
            sellers_rejected=await self._count(Seller, Seller.status == SellerStatus.REJECTED),
            leads_total=await self._count(Lead),
            leads_delivered=await self._count(Lead, Lead.sent_to_telegram_at.is_not(None)),
            replies_total=await self._count(Reply),
            replies_analyzed=await self._count(Reply, Reply.analyzed_at.is_not(None)),
            messages_sent=await self._count(MessageLog, MessageLog.status == MessageStatus.SENT),
            messages_failed=await self._count(
                MessageLog, MessageLog.status == MessageStatus.FAILED
            ),
            messages_today=await self._messages_today(),
            stages=await self._stages(),
            accounts_active=await self._count(Account, Account.status == AccountStatus.ACTIVE),
            accounts_blocked=await self._count(Account, Account.status == AccountStatus.BANNED),
            capacity_today=rotation.capacity_today,
            paused=bot_settings.paused,
            window_open_now=bot_settings.window_open_now,
            closed_reason=bot_settings.closed_reason,
            next_window_at=bot_settings.next_window_at,
        )

    async def _count(self, model: type, *conditions: object) -> int:
        query = select(func.count()).select_from(model)
        for condition in conditions:
            query = query.where(condition)  # type: ignore[arg-type]
        return await self.session.scalar(query) or 0

    async def _messages_today(self) -> int:
        start = (
            datetime.now(self.timezone)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .astimezone(UTC)
        )
        return await self._count(
            MessageLog,
            MessageLog.status == MessageStatus.SENT,
            MessageLog.sent_at >= start.replace(tzinfo=None),
        )

    async def _stages(self) -> list[StageStat]:
        rows = list(
            await self.session.execute(
                select(MessageLog.stage, MessageLog.status, func.count()).group_by(
                    MessageLog.stage, MessageLog.status
                )
            )
        )
        stats = {stage: StageStat(stage=stage) for stage in STAGES}  # type: ignore[misc]
        for stage, status, count in rows:
            stat = stats.get(stage)
            if stat is None:
                continue
            if status == MessageStatus.SENT:
                stat.sent = count
            elif status == MessageStatus.FAILED:
                stat.failed = count
            else:
                stat.skipped = count
        return [stats[stage] for stage in STAGES]
