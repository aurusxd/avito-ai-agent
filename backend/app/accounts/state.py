from datetime import UTC, datetime

from app.clients.avito.base import AvitoAccountRef
from app.db.models import Account, AccountStatus
from app.domain.rotation import AccountState


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def to_state(account: Account) -> AccountState:
    return AccountState(
        id=account.id,
        login=account.login,
        status=account.status.value,
        daily_message_count=account.daily_message_count,
        daily_limit=account.daily_limit,
        last_reset_at=as_utc(account.last_reset_at),
        paused_until=as_utc(account.paused_until) if account.paused_until else None,
    )


def store_state(account: Account, state: AccountState) -> None:
    account.status = AccountStatus(state.status)
    account.daily_message_count = state.daily_message_count
    account.last_reset_at = state.last_reset_at
    account.paused_until = state.paused_until


def account_ref(account: Account) -> AvitoAccountRef:
    return AvitoAccountRef(
        id=account.id,
        login=account.login,
        session_storage_path=account.session_storage_path,
        proxy_url=account.proxy_url,
    )
