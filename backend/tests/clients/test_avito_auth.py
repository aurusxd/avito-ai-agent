from typing import Any

from app.clients.avito.browser import explain_launch_failure, launch_args
from app.clients.avito.playwright_auth import (
    CAPTCHA_TEXT_MARKERS,
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


def test_missing_display_is_explained() -> None:
    raw = (
        "TargetClosedError: BrowserType.launch: Target page, context or browser has been closed "
        "Browser logs: Looks like you launched a headed browser without having a XServer running."
    )

    explained = explain_launch_failure(raw)

    assert explained is not None
    assert "xvfb" in explained


def test_missing_chromium_is_explained() -> None:
    raw = "Error: Executable doesn't exist at /ms-playwright/chromium-1234/chrome-linux/chrome"

    explained = explain_launch_failure(raw)

    assert explained is not None
    assert "playwright install chromium" in explained


def test_root_sandbox_failure_is_explained() -> None:
    raw = "Error: Running as root without --no-sandbox is not supported"

    assert explain_launch_failure(raw) == (
        "chromium cannot sandbox in this container, set BROWSER_NO_SANDBOX=true"
    )


def test_unknown_launch_failure_is_not_explained() -> None:
    assert explain_launch_failure("Error: something entirely new") is None


def test_container_flags_are_off_by_default() -> None:
    assert launch_args(get_settings()) == ["--disable-blink-features=AutomationControlled"]


def test_container_flags_are_added_when_enabled() -> None:
    tuned = get_settings().model_copy(
        update={"browser_no_sandbox": True, "browser_disable_dev_shm": True}
    )

    args = launch_args(tuned)

    assert "--no-sandbox" in args
    assert "--disable-setuid-sandbox" in args
    assert "--disable-dev-shm-usage" in args


def full_probe(**overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "text": "",
        "bodyText": "",
        "ready": "complete",
        "inputs": [],
        "captchaWidgets": 0,
        "passwordVisible": False,
        "submitVisible": False,
    }
    state.update(overrides)
    return state


def test_bundle_named_captcha_is_not_a_captcha() -> None:
    # avito ships assets like captcha.chunk.js on every page; only what the
    # human sees counts
    state = full_probe(bodyText="Вход в Авито. Телефон или почта. Пароль.")

    assert int(state["captchaWidgets"]) == 0
    assert not any(marker in state["bodyText"].lower() for marker in CAPTCHA_TEXT_MARKERS)


def test_visible_captcha_text_is_detected() -> None:
    state = full_probe(bodyText="Подтвердите, что вы не робот")

    assert any(marker in state["bodyText"].lower() for marker in CAPTCHA_TEXT_MARKERS)


def test_captcha_widget_counts_even_without_text() -> None:
    state = full_probe(captchaWidgets=1)

    assert int(state["captchaWidgets"]) > 0
