from datetime import UTC, datetime, timedelta
from random import Random
from zoneinfo import ZoneInfo

from hypothesis import given
from hypothesis import strategies as st

from app.domain.rotation import (
    MAX_DAILY_LIMIT,
    MAX_DELAY_MINUTES,
    MAX_ROTATION_SIZE,
    MIN_DELAY_MINUTES,
    MIN_ROTATION_SIZE,
    AccountState,
    RotationSettings,
    apply_daily_reset,
    clamp_daily_limit,
    clamp_settings,
    is_available,
    needs_daily_reset,
    next_delay,
    next_send_at,
    register_send,
    remaining_quota,
    rotation_members,
    select_account,
)

MSK = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)

statuses = st.sampled_from(["active", "paused", "banned"])
aware_datetimes = st.datetimes(
    min_value=datetime(2024, 1, 1),
    max_value=datetime(2030, 1, 1),
    timezones=st.just(UTC),
)


@st.composite
def account_states(draw: st.DrawFn) -> AccountState:
    return AccountState(
        id=draw(st.integers(min_value=1, max_value=50)),
        login=draw(st.text(min_size=1, max_size=12)),
        status=draw(statuses),
        daily_message_count=draw(st.integers(min_value=0, max_value=40)),
        daily_limit=draw(st.integers(min_value=1, max_value=40)),
        last_reset_at=draw(aware_datetimes),
    )


@st.composite
def raw_settings(draw: st.DrawFn) -> RotationSettings:
    return clamp_settings(
        draw(st.integers(min_value=-100, max_value=100)),
        draw(st.integers(min_value=-100, max_value=100)),
        draw(st.integers(min_value=-10, max_value=10)),
    )


def account(**overrides: object) -> AccountState:
    base: dict[str, object] = {
        "id": 1,
        "login": "acc-1",
        "status": "active",
        "daily_message_count": 0,
        "daily_limit": 15,
        "last_reset_at": NOW,
    }
    base.update(overrides)
    return AccountState(**base)  # type: ignore[arg-type]


@given(
    delay_min=st.integers(min_value=-100, max_value=100),
    delay_max=st.integers(min_value=-100, max_value=100),
    size=st.integers(min_value=-10, max_value=10),
)
def test_clamp_settings_stays_inside_policy(delay_min: int, delay_max: int, size: int) -> None:
    settings = clamp_settings(delay_min, delay_max, size)

    assert MIN_DELAY_MINUTES <= settings.delay_min_minutes <= MAX_DELAY_MINUTES
    assert MIN_DELAY_MINUTES <= settings.delay_max_minutes <= MAX_DELAY_MINUTES
    assert settings.delay_min_minutes <= settings.delay_max_minutes
    assert MIN_ROTATION_SIZE <= settings.rotation_size <= MAX_ROTATION_SIZE


@given(limit=st.integers(min_value=-50, max_value=500))
def test_clamp_daily_limit_never_exceeds_policy(limit: int) -> None:
    assert 1 <= clamp_daily_limit(limit) <= MAX_DAILY_LIMIT


@given(settings=raw_settings(), seed=st.integers(min_value=0, max_value=10_000))
def test_next_delay_always_inside_window(settings: RotationSettings, seed: int) -> None:
    delay = next_delay(settings, Random(seed))

    assert timedelta(minutes=MIN_DELAY_MINUTES) <= delay <= timedelta(minutes=MAX_DELAY_MINUTES)
    assert delay >= timedelta(minutes=settings.delay_min_minutes)
    assert delay <= timedelta(minutes=settings.delay_max_minutes)
    assert next_send_at(NOW, settings, Random(seed)) == NOW + delay


@given(state=account_states(), now=aware_datetimes)
def test_remaining_quota_never_leaves_bounds(state: AccountState, now: datetime) -> None:
    quota = remaining_quota(state, now, UTC)

    assert 0 <= quota <= clamp_daily_limit(state.daily_limit)


@given(state=account_states(), now=aware_datetimes)
def test_register_send_never_exceeds_limit(state: AccountState, now: datetime) -> None:
    before = remaining_quota(state, now, UTC)
    updated = register_send(state, now, UTC)
    after = remaining_quota(updated, now, UTC)

    assert updated.daily_message_count <= clamp_daily_limit(updated.daily_limit)
    if before > 0:
        assert after == before - 1
    else:
        assert after == 0


@given(state=account_states(), now=aware_datetimes)
def test_apply_daily_reset_is_idempotent(state: AccountState, now: datetime) -> None:
    once = apply_daily_reset(state, now, UTC)
    twice = apply_daily_reset(once, now, UTC)

    assert once == twice
    assert not needs_daily_reset(once, now, UTC)


@given(states=st.lists(account_states(), max_size=8), settings=raw_settings())
def test_rotation_members_respect_size_and_status(
    states: list[AccountState], settings: RotationSettings
) -> None:
    members = rotation_members(states, settings)

    assert len(members) <= settings.rotation_size
    assert all(member.status == "active" for member in members)
    assert [member.id for member in members] == sorted(member.id for member in members)


@given(states=st.lists(account_states(), max_size=8), settings=raw_settings(), now=aware_datetimes)
def test_select_account_only_returns_available_member(
    states: list[AccountState], settings: RotationSettings, now: datetime
) -> None:
    members = rotation_members(states, settings)
    selected = select_account(states, settings, now, UTC)
    available = [member for member in members if is_available(member, now, UTC)]

    if not available:
        assert selected is None
    else:
        assert selected is not None
        assert selected in members
        assert is_available(selected, now, UTC)
        assert remaining_quota(selected, now, UTC) == max(
            remaining_quota(member, now, UTC) for member in available
        )


def test_select_account_prefers_least_loaded_then_lowest_id() -> None:
    settings = clamp_settings(5, 15, 3)
    states = [
        account(id=1, daily_message_count=5),
        account(id=2, daily_message_count=1),
        account(id=3, daily_message_count=1),
    ]

    selected = select_account(states, settings, NOW, UTC)

    assert selected is not None
    assert selected.id == 2


def test_rotation_size_keeps_extra_accounts_out() -> None:
    settings = clamp_settings(5, 15, 2)
    states = [account(id=1), account(id=2), account(id=3)]

    assert [member.id for member in rotation_members(states, settings)] == [1, 2]


def test_paused_and_banned_accounts_never_selected() -> None:
    settings = clamp_settings(5, 15, 3)
    states = [
        account(id=1, status="paused"),
        account(id=2, status="banned"),
        account(id=3, status="active"),
    ]

    selected = select_account(states, settings, NOW, UTC)

    assert selected is not None
    assert selected.id == 3


def test_exhausted_rotation_returns_none() -> None:
    settings = clamp_settings(5, 15, 3)
    states = [account(id=1, daily_message_count=15), account(id=2, daily_message_count=15)]

    assert select_account(states, settings, NOW, UTC) is None


def test_quota_refills_after_local_day_rollover() -> None:
    yesterday = datetime(2026, 9, 5, 10, 0, tzinfo=UTC)
    state = account(daily_message_count=15, last_reset_at=yesterday)

    assert needs_daily_reset(state, NOW, MSK) is True
    assert remaining_quota(state, NOW, MSK) == 15

    reset = apply_daily_reset(state, NOW, MSK)
    assert reset.daily_message_count == 0
    assert reset.last_reset_at == NOW


def test_day_boundary_follows_the_given_timezone() -> None:
    just_after_msk_midnight = datetime(2026, 9, 5, 21, 30, tzinfo=UTC)
    state = account(daily_message_count=15, last_reset_at=just_after_msk_midnight)

    assert needs_daily_reset(state, NOW, MSK) is False
    assert remaining_quota(state, NOW, MSK) == 0

    assert needs_daily_reset(state, NOW, UTC) is True
    assert remaining_quota(state, NOW, UTC) == 15


def test_rotation_spreads_load_evenly_over_a_day() -> None:
    settings = clamp_settings(5, 15, 3)
    states = {index: account(id=index) for index in (1, 2, 3)}

    sent: list[int] = []
    while True:
        selected = select_account(list(states.values()), settings, NOW, UTC)
        if selected is None:
            break
        sent.append(selected.id)
        states[selected.id] = register_send(selected, NOW, UTC)

    assert len(sent) == 45
    assert [sent.count(index) for index in (1, 2, 3)] == [15, 15, 15]
