from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.ai.base import AIAnalysisRequest, AIClient, AIUnavailableError
from app.config import Settings
from app.db.models import MessageLog, Reply, Seller, SellerStatus, Sentiment
from app.domain.replies import next_seller_status
from app.domain.schemas import ReplyAnalysisResult, ReplyCreate, ReplyRead
from app.errors import ConflictError, NotFoundError


class ReplyAnalysisService:
    def __init__(self, session: AsyncSession, client: AIClient, settings: Settings) -> None:
        self.session = session
        self.client = client
        self.settings = settings

    async def register(self, request: ReplyCreate) -> ReplyAnalysisResult:
        payload = ReplyCreate.model_validate(request)

        if payload.external_id is not None:
            existing = await self.session.scalar(
                select(Reply).where(Reply.external_id == payload.external_id)
            )
            if existing is not None:
                seller = await self._seller_or_raise(existing.seller_id)
                return self._result(existing, seller, already_analyzed=True)

        seller = await self._seller_or_raise(payload.seller_id)

        log = await self.session.get(MessageLog, payload.message_log_id)
        if log is None:
            raise NotFoundError(f"message log {payload.message_log_id} not found")
        if log.seller_id != seller.id:
            raise ConflictError(
                f"message log {log.id} belongs to seller {log.seller_id}, not {seller.id}"
            )

        reply = Reply(
            seller_id=seller.id,
            message_log_id=log.id,
            reply_text=payload.reply_text,
            external_id=payload.external_id,
            received_at=payload.received_at or datetime.now(UTC),
        )
        self.session.add(reply)
        await self.session.flush()

        return await self._analyze(reply, seller)

    async def analyze(self, reply_id: int) -> ReplyAnalysisResult:
        reply = await self.session.get(Reply, reply_id)
        if reply is None:
            raise NotFoundError(f"reply {reply_id} not found")

        seller = await self._seller_or_raise(reply.seller_id)

        if reply.analyzed_at is not None:
            return self._result(reply, seller, already_analyzed=True)

        return await self._analyze(reply, seller)

    async def list_replies(self, seller_id: int | None = None) -> list[ReplyRead]:
        query = select(Reply).order_by(Reply.received_at.desc(), Reply.id.desc())
        if seller_id is not None:
            query = query.where(Reply.seller_id == seller_id)
        rows = await self.session.scalars(query)
        return [ReplyRead.model_validate(row) for row in rows]

    async def _analyze(self, reply: Reply, seller: Seller) -> ReplyAnalysisResult:
        try:
            response = await self.client.analyze_reply(
                AIAnalysisRequest(reply_text=reply.reply_text)
            )
        except AIUnavailableError as error:
            logger.warning(
                "reply {reply} stored without analysis: {reason}",
                reply=reply.id,
                reason=str(error),
            )
            await self.session.commit()
            await self.session.refresh(reply)
            return self._result(reply, seller, reason=str(error))

        before = seller.status.value
        after = next_seller_status(
            before,
            response.sentiment,
            response.confidence,
            self.settings.ai_sentiment_threshold,
        )

        reply.ai_sentiment = Sentiment(response.sentiment)
        reply.ai_confidence = response.confidence
        reply.analyzed_at = datetime.now(UTC)
        seller.status = SellerStatus(after)

        await self.session.commit()
        await self.session.refresh(reply)
        await self.session.refresh(seller)

        if after != before:
            logger.info(
                "seller {seller} moved from {before} to {after} on a {sentiment} reply",
                seller=seller.id,
                before=before,
                after=after,
                sentiment=response.sentiment,
            )

        return self._result(reply, seller, status_changed=after != before)

    async def _seller_or_raise(self, seller_id: int) -> Seller:
        seller = await self.session.get(Seller, seller_id)
        if seller is None:
            raise NotFoundError(f"seller {seller_id} not found")
        return seller

    def _result(
        self,
        reply: Reply,
        seller: Seller,
        status_changed: bool = False,
        reason: str | None = None,
        already_analyzed: bool = False,
    ) -> ReplyAnalysisResult:
        return ReplyAnalysisResult(
            reply=ReplyRead.model_validate(reply),
            seller_status=seller.status.value,
            status_changed=status_changed,
            provider=self._provider_name(),
            reason=reason,
            already_analyzed=already_analyzed,
        )

    def _provider_name(self) -> str | None:
        last = getattr(self.client, "last_provider", None)
        return last or getattr(self.client, "provider", None)
