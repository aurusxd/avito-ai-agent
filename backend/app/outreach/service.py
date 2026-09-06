from datetime import UTC, datetime
from random import Random
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.service import AccountService
from app.accounts.state import account_ref, store_state, to_state
from app.ai_pipeline.service import VariationService
from app.clients.ai.base import AIClient
from app.clients.avito.base import AvitoBlockedError, AvitoClient
from app.config import Settings
from app.db.models import (
    Account,
    BlockKind,
    MessageLog,
    MessageStatus,
    Script,
    Seller,
    SellerStatus,
)
from app.domain.rotation import (
    RotationSettings,
    apply_block,
    is_available,
    register_send,
    resume_if_cooled,
    select_account,
)
from app.domain.scheduling import closed_reason
from app.domain.schemas import MessageLogRead, OutreachRequest, OutreachResult, SellerDTO
from app.errors import NotFoundError
from app.settings_admin.service import BotSettingsService


class OutreachService:
    def __init__(
        self,
        session: AsyncSession,
        client: AvitoClient,
        settings: Settings,
        ai: AIClient,
        rng: Random | None = None,
    ) -> None:
        self.session = session
        self.client = client
        self.settings = settings
        self.timezone = ZoneInfo(settings.timezone)
        self.rng = rng or Random()
        self.variations = VariationService(session, ai, settings)

    async def send(self, request: OutreachRequest) -> OutreachResult:
        payload = OutreachRequest.model_validate(request)
        now = datetime.now(UTC)

        existing = await self._existing_log(payload.seller_id, payload.stage)
        if existing is not None:
            return OutreachResult(
                seller_id=payload.seller_id,
                stage=payload.stage,
                status=existing.status.value,
                account_id=existing.account_id,
                message_log_id=existing.id,
                variant_used=existing.variant_used,
                reason="stage already handled for this seller",
                already_sent=True,
            )

        seller = await self.session.get(Seller, payload.seller_id)
        if seller is None:
            raise NotFoundError(f"seller {payload.seller_id} not found")

        window = await BotSettingsService(self.session, self.settings).window()
        closed = closed_reason(window, now, self.timezone)
        if closed is not None:
            return OutreachResult(
                seller_id=payload.seller_id,
                stage=payload.stage,
                status="skipped",
                reason=closed,
            )

        account = await self._pick_account(payload.account_id, now)
        if account is None:
            await self.session.commit()
            return OutreachResult(
                seller_id=payload.seller_id,
                stage=payload.stage,
                status="skipped",
                reason="no account available: limits reached, paused or banned",
            )

        script = await self._pick_script(payload.stage)
        if script is None:
            await self.session.commit()
            return OutreachResult(
                seller_id=payload.seller_id,
                stage=payload.stage,
                account_id=account.id,
                status="skipped",
                reason=f"no active script for stage {payload.stage}",
            )

        variation = await self.variations.compose(seller, payload.stage, script)
        text = variation.final_text

        try:
            result = await self.client.send_message(
                account_ref(account),
                SellerDTO.model_validate(seller),
                text,
            )
        except AvitoBlockedError as error:
            return await self._handle_block(payload, account, script, text, error, now)

        log = MessageLog(
            seller_id=seller.id,
            account_id=account.id,
            stage=payload.stage,
            variant_used=script.variant_index,
            final_text=text,
            sent_at=result.sent_at,
            status=MessageStatus(result.status),
        )
        self.session.add(log)

        if result.status == "sent":
            store_state(account, register_send(to_state(account), now, self.timezone))
            if seller.status == SellerStatus.NEW:
                seller.status = SellerStatus.CONTACTED

        await self.session.commit()
        await self.session.refresh(log)

        return OutreachResult(
            seller_id=seller.id,
            stage=payload.stage,
            account_id=account.id,
            status=result.status,
            message_log_id=log.id,
            variant_used=script.variant_index,
            reason=result.error,
        )

    async def list_messages(self, seller_id: int | None = None) -> list[MessageLogRead]:
        query = select(MessageLog).order_by(MessageLog.sent_at.desc(), MessageLog.id.desc())
        if seller_id is not None:
            query = query.where(MessageLog.seller_id == seller_id)
        rows = await self.session.scalars(query)
        return [MessageLogRead.model_validate(row) for row in rows]

    async def _handle_block(
        self,
        payload: OutreachRequest,
        account: Account,
        script: Script,
        text: str,
        error: AvitoBlockedError,
        now: datetime,
    ) -> OutreachResult:
        logger.warning(
            "account {login} pulled from rotation: avito returned {kind}",
            login=account.login,
            kind=error.block_kind,
        )

        blocked = apply_block(to_state(account), error.block_kind, now, error.retry_after_seconds)
        store_state(account, blocked)
        account.last_block_kind = BlockKind(error.block_kind)
        account.last_block_at = now

        log = MessageLog(
            seller_id=payload.seller_id,
            account_id=account.id,
            stage=payload.stage,
            variant_used=script.variant_index,
            final_text=text,
            sent_at=now,
            status=MessageStatus.FAILED,
        )
        self.session.add(log)
        await self.session.commit()
        await self.session.refresh(log)

        return OutreachResult(
            seller_id=payload.seller_id,
            stage=payload.stage,
            account_id=account.id,
            status="failed",
            message_log_id=log.id,
            variant_used=script.variant_index,
            block_kind=error.block_kind,
            reason=str(error),
        )

    async def _existing_log(self, seller_id: int, stage: int) -> MessageLog | None:
        return await self.session.scalar(
            select(MessageLog).where(MessageLog.seller_id == seller_id, MessageLog.stage == stage)
        )

    async def _pick_account(self, account_id: int | None, now: datetime) -> Account | None:
        accounts = list(await self.session.scalars(select(Account).order_by(Account.id)))
        if not accounts:
            return None

        by_id = {account.id: account for account in accounts}
        if account_id is not None:
            account = by_id.get(account_id)
            if account is None:
                raise NotFoundError(f"account {account_id} not found")
            state = resume_if_cooled(to_state(account), now)
            store_state(account, state)
            return account if is_available(state, now, self.timezone) else None

        settings = await self._rotation_settings()
        selected = select_account(
            [to_state(account) for account in accounts], settings, now, self.timezone
        )
        if selected is None:
            return None
        account = by_id[selected.id]
        store_state(account, resume_if_cooled(selected, now))
        return account

    async def _rotation_settings(self) -> RotationSettings:
        return await AccountService(self.session, self.settings).rotation_settings()

    async def _pick_script(self, stage: int) -> Script | None:
        variants = list(
            await self.session.scalars(
                select(Script)
                .where(Script.stage == stage, Script.active.is_(True))
                .order_by(Script.variant_index)
            )
        )
        return self.rng.choice(variants) if variants else None
