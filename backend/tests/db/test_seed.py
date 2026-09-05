from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, AppSettings, Category, ScheduleSettings, Script
from app.db.seed import SEED_ACCOUNT_LOGIN, SEED_CATEGORIES, SEED_SCRIPTS, seed_all
from app.domain.templates import KNOWN_PLACEHOLDERS, missing_placeholders


async def _count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def test_seed_all_populates_fixtures(session: AsyncSession) -> None:
    await seed_all(session)

    assert await _count(session, Category) == len(SEED_CATEGORIES)
    assert await _count(session, Script) == len(SEED_SCRIPTS)
    assert await _count(session, Account) == 1
    assert await _count(session, ScheduleSettings) == 1
    assert await _count(session, AppSettings) == 1

    account = await session.scalar(select(Account).where(Account.login == SEED_ACCOUNT_LOGIN))
    assert account is not None
    assert account.daily_limit == 15


async def test_seed_all_is_idempotent(session: AsyncSession) -> None:
    await seed_all(session)
    await seed_all(session)

    assert await _count(session, Category) == len(SEED_CATEGORIES)
    assert await _count(session, Script) == len(SEED_SCRIPTS)
    assert await _count(session, Account) == 1


async def test_seed_scripts_cover_three_stages_by_five_variants(session: AsyncSession) -> None:
    await seed_all(session)

    rows = list(await session.scalars(select(Script)))
    pairs = {(row.stage, row.variant_index) for row in rows}

    assert pairs == {(stage, variant) for stage in (1, 2, 3) for variant in range(1, 6)}
    for row in rows:
        used = {name for name in KNOWN_PLACEHOLDERS if f"{{{name}}}" in row.template_text}
        assert used, f"stage {row.stage} variant {row.variant_index} has no placeholder"
        assert missing_placeholders(row.template_text) == set()
