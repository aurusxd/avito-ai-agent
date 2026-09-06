from dataclasses import dataclass, replace
from datetime import datetime, timedelta, tzinfo
from random import Random
from typing import Literal

AccountStatusLiteral = Literal["active", "paused", "banned"]

MAX_DAILY_LIMIT = 15
MIN_DELAY_MINUTES = 5
MAX_DELAY_MINUTES = 15
MIN_ROTATION_SIZE = 2
MAX_ROTATION_SIZE = 3


@dataclass(frozen=True)
class AccountState:
    id: int
    login: str
    status: AccountStatusLiteral
    daily_message_count: int
    daily_limit: int
    last_reset_at: datetime


@dataclass(frozen=True)
class RotationSettings:
    delay_min_minutes: int = MIN_DELAY_MINUTES
    delay_max_minutes: int = MAX_DELAY_MINUTES
    rotation_size: int = MAX_ROTATION_SIZE


def clamp_daily_limit(limit: int) -> int:
    return max(1, min(limit, MAX_DAILY_LIMIT))


def clamp_settings(
    delay_min_minutes: int,
    delay_max_minutes: int,
    rotation_size: int,
) -> RotationSettings:
    low = max(MIN_DELAY_MINUTES, min(delay_min_minutes, MAX_DELAY_MINUTES))
    high = max(MIN_DELAY_MINUTES, min(delay_max_minutes, MAX_DELAY_MINUTES))
    if high < low:
        low, high = high, low
    return RotationSettings(
        delay_min_minutes=low,
        delay_max_minutes=high,
        rotation_size=max(MIN_ROTATION_SIZE, min(rotation_size, MAX_ROTATION_SIZE)),
    )


def needs_daily_reset(state: AccountState, now: datetime, tz: tzinfo) -> bool:
    return state.last_reset_at.astimezone(tz).date() < now.astimezone(tz).date()


def apply_daily_reset(state: AccountState, now: datetime, tz: tzinfo) -> AccountState:
    if not needs_daily_reset(state, now, tz):
        return state
    return replace(state, daily_message_count=0, last_reset_at=now)


def remaining_quota(state: AccountState, now: datetime, tz: tzinfo) -> int:
    limit = clamp_daily_limit(state.daily_limit)
    if needs_daily_reset(state, now, tz):
        return limit
    return max(0, limit - state.daily_message_count)


def is_available(state: AccountState, now: datetime, tz: tzinfo) -> bool:
    return state.status == "active" and remaining_quota(state, now, tz) > 0


def rotation_members(
    states: list[AccountState],
    settings: RotationSettings,
) -> tuple[AccountState, ...]:
    active = sorted((s for s in states if s.status == "active"), key=lambda s: s.id)
    return tuple(active[: settings.rotation_size])


def select_account(
    states: list[AccountState],
    settings: RotationSettings,
    now: datetime,
    tz: tzinfo,
) -> AccountState | None:
    candidates = [s for s in rotation_members(states, settings) if is_available(s, now, tz)]
    if not candidates:
        return None
    return min(candidates, key=lambda s: (-remaining_quota(s, now, tz), s.id))


def register_send(state: AccountState, now: datetime, tz: tzinfo) -> AccountState:
    current = apply_daily_reset(state, now, tz)
    limit = clamp_daily_limit(current.daily_limit)
    return replace(current, daily_message_count=min(limit, current.daily_message_count + 1))


def next_delay(settings: RotationSettings, rng: Random) -> timedelta:
    low = settings.delay_min_minutes * 60
    high = settings.delay_max_minutes * 60
    return timedelta(seconds=rng.randint(low, high))


def next_send_at(now: datetime, settings: RotationSettings, rng: Random) -> datetime:
    return now + next_delay(settings, rng)
