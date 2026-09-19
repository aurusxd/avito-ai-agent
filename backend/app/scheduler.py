from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.base import STATE_RUNNING
from loguru import logger

from app.config import get_settings

DEMO_JOB_ID = "demo-heartbeat"
LEADS_JOB_ID = "leads-delivery"
INBOX_JOB_ID = "inbox-poll"

_scheduler: AsyncIOScheduler | None = None


async def demo_heartbeat() -> None:
    logger.info("scheduler heartbeat")


async def deliver_leads() -> None:
    from app.clients.telegram import get_notifier
    from app.db.base import session_factory
    from app.leads.service import LeadService

    settings = get_settings()
    async with session_factory() as session:
        run = await LeadService(session, get_notifier(), settings).deliver_pending()

    if run.delivered or run.failed:
        logger.info(
            "leads job: {delivered} delivered, {failed} failed, {candidates} candidate(s)",
            delivered=run.delivered,
            failed=run.failed,
            candidates=run.candidates,
        )


async def poll_inbox() -> None:
    from app.ai_pipeline.analysis import ReplyAnalysisService
    from app.ai_pipeline.inbox import InboxService
    from app.clients.ai import get_ai_client
    from app.clients.avito import get_avito_client
    from app.db.base import session_factory

    settings = get_settings()
    async with session_factory() as session:
        analysis = ReplyAnalysisService(session, get_ai_client(), settings)
        service = InboxService(session, get_avito_client(), analysis, settings)
        results = await service.poll_all(settings.inbox_poll_limit)

    ingested = sum(result.ingested for result in results)
    blocked = sum(1 for result in results if result.block_kind != "none")
    if ingested or blocked:
        logger.info(
            "inbox job: {accounts} account(s) read, {ingested} new reply(ies), {blocked} blocked",
            accounts=len(results),
            ingested=ingested,
            blocked=blocked,
        )


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone=get_settings().timezone)
    return _scheduler


def is_running() -> bool:
    return _scheduler is not None and _scheduler.state == STATE_RUNNING


def start_scheduler() -> AsyncIOScheduler:
    scheduler = get_scheduler()
    scheduler.add_job(
        demo_heartbeat,
        trigger="interval",
        minutes=5,
        id=DEMO_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        deliver_leads,
        trigger="interval",
        seconds=get_settings().leads_poll_seconds,
        id=LEADS_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        poll_inbox,
        trigger="interval",
        seconds=get_settings().inbox_poll_seconds,
        id=INBOX_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    if scheduler.state != STATE_RUNNING:
        scheduler.start()
    logger.info("scheduler started with {count} job(s)", count=len(scheduler.get_jobs()))
    return scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.state == STATE_RUNNING:
        _scheduler.shutdown(wait=False)
        logger.info("scheduler stopped")
    _scheduler = None
