from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from app.domain.auth_session import (
    AWAITING_OPERATOR,
    TERMINAL_STATUSES,
    LoginSession,
    LoginStatusLiteral,
    advance,
    awaits_operator,
    can_confirm,
    expire,
    expires_at,
    is_expired,
    is_terminal,
)

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
TTL = 900

statuses: st.SearchStrategy[LoginStatusLiteral] = st.sampled_from(
    ["starting", "waiting_for_operator", "saving", "done", "failed", "expired"]
)
ttls = st.integers(min_value=-100, max_value=3600)
offsets = st.integers(min_value=-3600, max_value=7200)


def session(**overrides: object) -> LoginSession:
    base: dict[str, object] = {
        "session_id": "sess-1",
        "login": "operator-1",
        "status": "starting",
        "created_at": NOW,
        "updated_at": NOW,
    }
    base.update(overrides)
    return LoginSession(**base)  # type: ignore[arg-type]


def test_flow_walks_from_start_to_done() -> None:
    current = session()
    current = advance(current, "waiting_for_operator", NOW, hint="войдите в окне")
    assert can_confirm(current) is True
    assert awaits_operator(current) is True

    current = advance(current, "saving", NOW)
    assert can_confirm(current) is False

    current = advance(current, "done", NOW, account_id=7)
    assert is_terminal(current) is True
    assert current.account_id == 7


def test_done_session_is_frozen() -> None:
    done = advance(session(), "done", NOW, account_id=3)

    assert advance(done, "waiting_for_operator", NOW) == done
    assert advance(done, "failed", NOW) == done


def test_account_id_survives_later_steps() -> None:
    current = advance(session(), "saving", NOW, account_id=5)
    current = advance(current, "done", NOW)

    assert current.account_id == 5


def test_session_expires_after_the_ttl() -> None:
    current = session()

    assert is_expired(current, NOW + timedelta(seconds=TTL - 1), TTL) is False
    assert is_expired(current, NOW + timedelta(seconds=TTL), TTL) is True

    expired = expire(current, NOW + timedelta(seconds=TTL), TTL)
    assert expired.status == "expired"
    assert expired.hint is not None


def test_activity_pushes_the_deadline() -> None:
    later = NOW + timedelta(seconds=300)
    current = advance(session(), "waiting_for_operator", later)

    assert expires_at(current, TTL) == later + timedelta(seconds=TTL)
    assert is_expired(current, later + timedelta(seconds=TTL - 1), TTL) is False


def test_terminal_session_never_expires() -> None:
    done = advance(session(), "done", NOW)

    assert is_expired(done, NOW + timedelta(days=7), TTL) is False
    assert expire(done, NOW + timedelta(days=7), TTL) == done


@given(status=statuses, target=statuses)
def test_terminal_status_is_never_left(
    status: LoginStatusLiteral, target: LoginStatusLiteral
) -> None:
    current = session(status=status)
    result = advance(current, target, NOW)

    if status in TERMINAL_STATUSES:
        assert result == current
    else:
        assert result.status == target


@given(status=statuses, offset=offsets, ttl=ttls)
def test_expire_is_idempotent(status: LoginStatusLiteral, offset: int, ttl: int) -> None:
    current = session(status=status)
    moment = NOW + timedelta(seconds=offset)

    once = expire(current, moment, ttl)

    assert expire(once, moment, ttl) == once


@given(status=statuses)
def test_only_the_waiting_state_can_be_confirmed(status: LoginStatusLiteral) -> None:
    current = session(status=status)

    assert can_confirm(current) == (status == "waiting_for_operator")
    assert awaits_operator(current) == (status in AWAITING_OPERATOR)


@given(status=statuses, target=statuses)
def test_advance_never_moves_time_backwards(
    status: LoginStatusLiteral, target: LoginStatusLiteral
) -> None:
    current = session(status=status)
    later = NOW + timedelta(seconds=42)

    assert advance(current, target, later).updated_at >= current.updated_at
