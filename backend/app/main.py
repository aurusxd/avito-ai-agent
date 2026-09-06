from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from sqlalchemy import text

from app.accounts.router import router as accounts_router
from app.ai_pipeline.router import router as ai_router
from app.categories.router import router as categories_router
from app.config import get_settings
from app.db.base import engine
from app.errors import register_error_handlers
from app.leads.router import router as leads_router
from app.logging import setup_logging
from app.outreach.router import router as outreach_router
from app.parser.router import router as parser_router
from app.scheduler import is_running, shutdown_scheduler, start_scheduler
from app.scripts_admin.router import router as scripts_router
from app.settings_admin.router import router as settings_router


async def _database_ready() -> bool:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        logger.exception("database is not reachable")
        return False
    return True


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    settings = get_settings()
    logger.info("starting {app_name}", app_name=settings.app_name)
    await _database_ready()
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()
        await engine.dispose()
        logger.info("stopped {app_name}", app_name=settings.app_name)


system_router = APIRouter(tags=["system"])


@system_router.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "database": await _database_ready(),
        "scheduler": is_running(),
    }


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(system_router)
    app.include_router(accounts_router, prefix="/api")
    app.include_router(ai_router, prefix="/api")
    app.include_router(categories_router, prefix="/api")
    app.include_router(leads_router, prefix="/api")
    app.include_router(outreach_router, prefix="/api")
    app.include_router(parser_router, prefix="/api")
    app.include_router(scripts_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")
    return app


app = create_app()
