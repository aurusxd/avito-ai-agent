from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.base import STATE_RUNNING
from loguru import logger

from app.config import get_settings

DEMO_JOB_ID = "demo-heartbeat"

_scheduler: AsyncIOScheduler | None = None


async def demo_heartbeat() -> None:
    logger.info("scheduler heartbeat")


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
