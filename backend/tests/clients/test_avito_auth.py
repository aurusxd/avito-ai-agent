from typing import Any

from app.clients.avito.playwright_auth import (
    PlaywrightAvitoAuthClient,
    _short,
    describe,
    scrub,
)
from app.config import get_settings

PHONE_FIELD = {
    "marker": None,
    "name": "login",
    "type": "tel",
    "inputmode": "numeric",
    "autocomplete": "username",
    "maxlength": None,
}

CODE_FIELD_BY_MARKER = {
    "marker": "login-form/code/input",
    "name": None,
    "type": "text",
    "inputmode": "numeric",
    "autocomplete": None,
    "maxlength": "6",
}

CODE_FIELD_BY_AUTOCOMPLETE = {
    "marker": None,
    "name": None,
    "type": "text",
    "inputmode": "numeric",
    "autocomplete": "one-time-code",
    "maxlength": "6",
}


def client() -> PlaywrightAvitoAuthClient:
    return PlaywrightAvitoAuthClient(get_settings())


def probe(text: str, inputs: list[dict[str, Any]]) -> dict[str, Any]:
    return {"text": text, "inputs": inputs, "passwordVisible": False, "submitVisible": False}


def test_numeric_phone_field_is_not_taken_for_a_code_field() -> None:
    state = probe("Вход в Авито. Телефон или почта. Пароль.", [PHONE_FIELD])

    assert client()._code_selector(state) is None


def test_code_field_is_found_by_its_marker() -> None:
    state = probe("Введите код из СМС", [CODE_FIELD_BY_MARKER])

    assert client()._code_selector(state) == '[data-marker="login-form/code/input"]'


def test_code_field_is_found_by_autocomplete() -> None:
    state = probe("Подтвердите вход", [CODE_FIELD_BY_AUTOCOMPLETE])

    assert client()._code_selector(state) == 'input[autocomplete="one-time-code"]'


def test_nameless_field_counts_only_when_the_popup_mentions_a_code() -> None:
    anonymous = {
        "marker": None,
        "name": "otp",
        "type": "text",
        "inputmode": "numeric",
        "autocomplete": None,
        "maxlength": "6",
    }

    assert client()._code_selector(probe("Мы отправили код на телефон", [anonymous])) == (
        'input[name="otp"]'
    )
    assert client()._code_selector(probe("Вход в Авито", [anonymous])) is None


def test_no_inputs_means_no_code_field() -> None:
    assert client()._code_selector(probe("Введите код", [])) is None


def test_short_collapses_whitespace_and_trims() -> None:
    assert _short("  Неверный   логин\n\nили пароль  ") == "Неверный логин или пароль"
    assert _short("") == "empty popup"
    assert len(_short("а" * 500)) == 160


def test_describe_keeps_the_message_and_hides_the_password() -> None:
    error = RuntimeError("net::ERR_TUNNEL_CONNECTION_FAILED for hunter2")

    described = describe(error, "hunter2")

    assert "RuntimeError" in described
    assert "ERR_TUNNEL_CONNECTION_FAILED" in described
    assert "hunter2" not in described
    assert "***" in described


def test_describe_collapses_whitespace_and_truncates() -> None:
    error = RuntimeError("a" * 500)

    assert len(describe(error)) == 220
    assert describe(RuntimeError("two\n\nlines")) == "RuntimeError: two lines"


def test_scrub_leaves_the_message_alone_without_a_secret() -> None:
    assert scrub("plain message", "") == "plain message"
