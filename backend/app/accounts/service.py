from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import BACKEND_ROOT, Settings
from app.db.models import Account, AppSettings
from app.domain.rotation import (
    AccountState,
    RotationSettings,
    clamp_daily_limit,
    clamp_settings,
    is_available,
    remaining_quota,
    rotation_members,
    select_account,
)
from app.domain.schemas import (
    AccountCreate,
    AccountRead,
    AccountUpdate,
    RotationMember,
    RotationPreview,
)
from app.errors import ConflictError, NotFoundError


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class AccountService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.timezone = ZoneInfo(settings.timezone)

    async def list(self) -> list[AccountRead]:
        rows = await self.session.scalars(select(Account).order_by(Account.id))
        now = datetime.now(UTC)
        return [self._to_read(row, now) for row in rows]

    async def get(self, account_id: int) -> AccountRead:
        account = await self._get_or_raise(account_id)
        return self._to_read(account, datetime.now(UTC))

    async def create(self, payload: AccountCreate) -> AccountRead:
        await self._ensure_login_free(payload.login)
        account = Account(
            login=payload.login,
            session_storage_path=payload.session_storage_path,
            daily_limit=clamp_daily_limit(payload.daily_limit),
        )
        self.session.add(account)
        await self.session.commit()
        await self.session.refresh(account)
        return self._to_read(account, datetime.now(UTC))

    async def update(self, account_id: int, payload: AccountUpdate) -> AccountRead:
        account = await self._get_or_raise(account_id)
        changes = payload.model_dump(exclude_unset=True)
        if "login" in changes:
            await self._ensure_login_free(changes["login"], exclude_id=account_id)
        if "daily_limit" in changes:
            changes["daily_limit"] = clamp_daily_limit(changes["daily_limit"])
        for field, value in changes.items():
            setattr(account, field, value)
        await self.session.commit()
        await self.session.refresh(account)
        return self._to_read(account, datetime.now(UTC))

    async def delete(self, account_id: int) -> None:
        account = await self._get_or_raise(account_id)
        await self.session.delete(account)
        await self.session.commit()

    async def rotation_preview(self) -> RotationPreview:
        now = datetime.now(UTC)
        settings = await self.rotation_settings()
        accounts = list(await self.session.scalars(select(Account).order_by(Account.id)))
        states = [self._to_state(account) for account in accounts]
        member_ids = {member.id for member in rotation_members(states, settings)}
        selected = select_account(states, settings, now, self.timezone)

        members = [
            RotationMember(
                account_id=state.id,
                login=state.login,
                status=state.status,
                remaining_today=remaining_quota(state, now, self.timezone),
                in_rotation=state.id in member_ids,
                available=state.id in member_ids and is_available(state, now, self.timezone),
            )
            for state in states
        ]

        return RotationPreview(
            rotation_size=settings.rotation_size,
            delay_min_minutes=settings.delay_min_minutes,
            delay_max_minutes=settings.delay_max_minutes,
            daily_limit=clamp_daily_limit(self.settings.daily_message_limit),
            next_account_id=selected.id if selected else None,
            capacity_today=sum(member.remaining_today for member in members if member.in_rotation),
            members=members,
        )

    async def rotation_settings(self) -> RotationSettings:
        row = await self.session.scalar(select(AppSettings).order_by(AppSettings.id).limit(1))
        if row is None:
            return clamp_settings(
                self.settings.delay_min_minutes,
                self.settings.delay_max_minutes,
                self.settings.account_rotation_size,
            )
        return clamp_settings(
            row.delay_min_minutes,
            row.delay_max_minutes,
            row.account_rotation_size,
        )

    async def _get_or_raise(self, account_id: int) -> Account:
        account = await self.session.get(Account, account_id)
        if account is None:
            raise NotFoundError(f"account {account_id} not found")
        return account

    async def _ensure_login_free(self, login: str, exclude_id: int | None = None) -> None:
        query = select(Account.id).where(Account.login == login)
        if exclude_id is not None:
            query = query.where(Account.id != exclude_id)
        if await self.session.scalar(query) is not None:
            raise ConflictError(f"account with login {login!r} already exists")

    def _to_state(self, account: Account) -> AccountState:
        return AccountState(
            id=account.id,
            login=account.login,
            status=account.status.value,
            daily_message_count=account.daily_message_count,
            daily_limit=account.daily_limit,
            last_reset_at=_as_utc(account.last_reset_at),
        )

    def _to_read(self, account: Account, now: datetime) -> AccountRead:
        state = self._to_state(account)
        return AccountRead(
            id=account.id,
            login=account.login,
            session_storage_path=account.session_storage_path,
            daily_limit=clamp_daily_limit(account.daily_limit),
            status=state.status,
            daily_message_count=account.daily_message_count,
            remaining_today=remaining_quota(state, now, self.timezone),
            has_session=self._session_file_exists(account.session_storage_path),
            last_reset_at=_as_utc(account.last_reset_at),
            created_at=_as_utc(account.created_at),
        )

    def _session_file_exists(self, raw_path: str) -> bool:
        path = Path(raw_path)
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        return path.is_file()
