from app.clients.avito.browser import explain_launch_failure, launch_args
from app.clients.avito.playwright_auth import describe, scrub
from app.config import get_settings


def test_describe_keeps_the_message_and_hides_a_secret() -> None:
    error = RuntimeError("net::ERR_TUNNEL_CONNECTION_FAILED for hunter2")

    described = describe(error, "hunter2")

    assert "RuntimeError" in described
    assert "ERR_TUNNEL_CONNECTION_FAILED" in described
    assert "hunter2" not in described
    assert "***" in described


def test_describe_collapses_whitespace_and_truncates() -> None:
    assert len(describe(RuntimeError("a" * 500))) == 220
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
