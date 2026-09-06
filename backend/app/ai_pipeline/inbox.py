from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.state import account_ref, store_state, to_state
from app.ai_pipeline.analysis import ReplyAnalysisService
from app.clients.avito.base import AvitoBlockedError, AvitoClient, IncomingReplyDTO
from app.config import Settings
from app.db.models import Account, AccountStatus, BlockKind, MessageLog, Seller
from app.domain.rotation import apply_block, resume_if_cooled
from app.domain.schemas import InboxPollRequest, InboxPollResult, ReplyCreate
from app.errors import NotFoundError


class InboxService:
    def __init__(
        self,
        session: AsyncSession,
        client: AvitoClient,
        analysis: ReplyAnalysisService,
        settings: Settings,
    ) -> None:
        self.session = session
        self.client = client
        self.analysis = analysis
        self.settings = settings

    async def poll(self, request: InboxPollRequest) -> InboxPollResult:
        payload = InboxPollRequest.model_validate(request)
        now = datetime.now(UTC)

        account = await self._pick_account(payload.account_id, now)
        if account is None:
            await self.session.commit()
            return InboxPollResult(reason="no account available to read the inbox")

        result = InboxPollResult(account_id=account.id)

        try:
            replies = await self.client.fetch_replies(account_ref(account), payload.limit)
        except AvitoBlockedError as error:
            return await self._handle_block(account, error, now, result)

        result.fetched = len(replies)
        for reply in replies:
            await self._ingest(reply, result)

        await self.session.commit()
        return result

    async def _ingest(self, reply: IncomingReplyDTO, result: InboxPollResult) -> None:
        seller = await self.session.scalar(
            select(Seller).where(Seller.avito_seller_id == reply.avito_seller_id)
        )
        if seller is None:
            result.unknown_sellers += 1
            return

        log = await self.session.scalar(
            select(MessageLog)
            .where(MessageLog.seller_id == seller.id)
            .order_by(MessageLog.stage.desc(), MessageLog.id.desc())
            .limit(1)
        )
        if log is None:
            result.without_message_log += 1
            return

        analysis = await self.analysis.register(
            ReplyCreate(
                seller_id=seller.id,
                message_log_id=log.id,
                reply_text=reply.text,
                external_id=reply.external_id,
                received_at=reply.received_at,
            )
        )

        if analysis.already_analyzed:
            result.duplicates += 1
            return

        result.ingested += 1
        if analysis.reply.analyzed_at is not None:
            result.analyzed += 1

    async def _handle_block(
        self,
        account: Account,
        error: AvitoBlockedError,
        now: datetime,
        result: InboxPollResult,
    ) -> InboxPollResult:
        logger.warning(
            "inbox read for {login} stopped: avito returned {kind}",
            login=account.login,
            kind=error.block_kind,
        )

        store_state(
            account,
            apply_block(to_state(account), error.block_kind, now, error.retry_after_seconds),
        )
        account.last_block_kind = BlockKind(error.block_kind)
        account.last_block_at = now
        await self.session.commit()

        result.block_kind = error.block_kind
        result.reason = str(error)
        return result

    async def _pick_account(self, account_id: int | None, now: datetime) -> Account | None:
        if account_id is not None:
            account = await self.session.get(Account, account_id)
            if account is None:
                raise NotFoundError(f"account {account_id} not found")
            store_state(account, resume_if_cooled(to_state(account), now))
            return account if account.status == AccountStatus.ACTIVE else None

        accounts = list(await self.session.scalars(select(Account).order_by(Account.id)))
        for account in accounts:
            store_state(account, resume_if_cooled(to_state(account), now))
            if account.status == AccountStatus.ACTIVE:
                return account
        return None
