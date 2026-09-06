from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal

LoginStatusLiteral = Literal[
    "starting",
    "code_required",
    "captcha_required",
    "saving",
    "done",
    "failed",
    "expired",
]

TERMINAL_STATUSES: frozenset[str] = frozenset({"done", "failed", "expired"})
AWAITING_OPERATOR: frozenset[str] = frozenset({"code_required", "captcha_required"})

DEFAULT_TTL_SECONDS = 600


@dataclass(frozen=True)
class LoginSession:
    session_id: str
    login: str
    status: LoginStatusLiteral
    created_at: datetime
    updated_at: datetime
    hint: str | None = None
    account_id: int | None = None
    has_screenshot: bool = False


def is_terminal(session: LoginSession) -> bool:
    return session.status in TERMINAL_STATUSES


def awaits_operator(session: LoginSession) -> bool:
    return session.status in AWAITING_OPERATOR


def can_submit_code(session: LoginSession) -> bool:
    return session.status == "code_required"


def expires_at(session: LoginSession, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> datetime:
    return session.updated_at + timedelta(seconds=max(1, ttl_seconds))


def is_expired(
    session: LoginSession, now: datetime, ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> bool:
    if is_terminal(session):
        return False
    return now >= expires_at(session, ttl_seconds)


def advance(
    session: LoginSession,
    status: LoginStatusLiteral,
    now: datetime,
    hint: str | None = None,
    account_id: int | None = None,
    has_screenshot: bool = False,
) -> LoginSession:
    if is_terminal(session):
        return session

    return replace(
        session,
        status=status,
        updated_at=now,
        hint=hint,
        account_id=account_id if account_id is not None else session.account_id,
        has_screenshot=has_screenshot,
    )


def expire(
    session: LoginSession, now: datetime, ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> LoginSession:
    if not is_expired(session, now, ttl_seconds):
        return session
    return replace(
        session,
        status="expired",
        updated_at=now,
        hint="login session timed out, start again",
        has_screenshot=False,
    )
