from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.telegram.base import LeadNotification, Notifier, NotifierUnavailableError
from app.config import Settings
from app.db.models import Lead, Listing, MessageLog, Reply, Seller, SellerStatus, Sentiment
from app.domain.schemas import (
    LeadDeliveryResult,
    LeadRead,
    LeadsRunResult,
    MessageDTO,
    Stage,
)
from app.errors import NotFoundError


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class LeadService:
    def __init__(self, session: AsyncSession, notifier: Notifier, settings: Settings) -> None:
        self.session = session
        self.notifier = notifier
        self.settings = settings

    async def deliver_pending(self) -> LeadsRunResult:
        sellers = list(
            await self.session.scalars(
                select(Seller).where(Seller.status == SellerStatus.INTERESTED).order_by(Seller.id)
            )
        )
        run = LeadsRunResult(candidates=len(sellers))

        for seller in sellers:
            outcome = await self._deliver(seller)
            run.results.append(outcome)
            if outcome.delivered:
                run.delivered += 1
            elif outcome.already_delivered:
                run.skipped += 1
            elif outcome.reason is not None and outcome.lead_id is None:
                run.failed += 1
            else:
                run.skipped += 1

        await self.session.commit()
        return run

    async def deliver_seller(self, seller_id: int) -> LeadDeliveryResult:
        seller = await self.session.get(Seller, seller_id)
        if seller is None:
            raise NotFoundError(f"seller {seller_id} not found")

        outcome = await self._deliver(seller)
        await self.session.commit()
        return outcome

    async def list_leads(self) -> list[LeadRead]:
        rows = await self.session.scalars(select(Lead).order_by(Lead.id.desc()))
        return [LeadRead.model_validate(row) for row in rows]

    async def _deliver(self, seller: Seller) -> LeadDeliveryResult:
        reply = await self._trigger_reply(seller)
        if reply is None:
            return LeadDeliveryResult(
                seller_id=seller.id,
                reply_id=0,
                reason="no analysed interested reply for this seller",
            )

        lead = await self.session.scalar(select(Lead).where(Lead.reply_id == reply.id))
        if lead is not None and lead.sent_to_telegram_at is not None:
            return LeadDeliveryResult(
                seller_id=seller.id,
                reply_id=reply.id,
                lead_id=lead.id,
                already_delivered=True,
            )

        history = await self._conversation(seller)
        notification = LeadNotification(
            seller_name=seller.name,
            listing_url=await self._listing_url(seller),
            conversation_history=history,
            stage_reached=await self._stage_reached(seller),
        )

        try:
            await self.notifier.send_lead(notification)
        except NotifierUnavailableError as error:
            logger.warning(
                "lead for seller {seller} not delivered: {reason}",
                seller=seller.id,
                reason=str(error),
            )
            return LeadDeliveryResult(seller_id=seller.id, reply_id=reply.id, reason=str(error))

        if lead is None:
            lead = Lead(seller_id=seller.id, reply_id=reply.id)
            self.session.add(lead)

        lead.conversation_history = [item.model_dump(mode="json") for item in history]
        lead.sent_to_telegram_at = datetime.now(UTC)
        seller.status = SellerStatus.LEAD

        await self.session.flush()
        logger.info("lead for seller {seller} delivered to telegram", seller=seller.id)

        return LeadDeliveryResult(
            seller_id=seller.id, reply_id=reply.id, lead_id=lead.id, delivered=True
        )

    async def _trigger_reply(self, seller: Seller) -> Reply | None:
        return await self.session.scalar(
            select(Reply)
            .where(
                Reply.seller_id == seller.id,
                Reply.ai_sentiment == Sentiment.INTERESTED,
                Reply.analyzed_at.is_not(None),
            )
            .order_by(Reply.received_at.desc(), Reply.id.desc())
            .limit(1)
        )

    async def _conversation(self, seller: Seller) -> list[MessageDTO]:
        logs = list(
            await self.session.scalars(select(MessageLog).where(MessageLog.seller_id == seller.id))
        )
        replies = list(
            await self.session.scalars(select(Reply).where(Reply.seller_id == seller.id))
        )

        history = [
            MessageDTO(
                role="bot",
                text=log.final_text,
                stage=log.stage,  # type: ignore[arg-type]
                sent_at=_as_utc(log.sent_at),
            )
            for log in logs
        ] + [
            MessageDTO(role="seller", text=reply.reply_text, sent_at=_as_utc(reply.received_at))
            for reply in replies
        ]

        history.sort(key=lambda item: item.sent_at)
        return history[-self.settings.leads_history_limit :]

    async def _listing_url(self, seller: Seller) -> str:
        listing = await self.session.scalar(
            select(Listing).where(Listing.seller_id == seller.id).order_by(Listing.id).limit(1)
        )
        return listing.url if listing else seller.profile_url

    async def _stage_reached(self, seller: Seller) -> Stage:
        stage = await self.session.scalar(
            select(MessageLog.stage)
            .where(MessageLog.seller_id == seller.id)
            .order_by(MessageLog.stage.desc())
            .limit(1)
        )
        return stage or 1  # type: ignore[return-value]
