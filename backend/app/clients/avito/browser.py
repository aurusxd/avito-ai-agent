from app.config import Settings

BASE_ARGS: tuple[str, ...] = ("--disable-blink-features=AutomationControlled",)

HEADLESS_HINT = (
    "avito detects headless browsers; run the container under xvfb and keep AVITO_HEADLESS=false"
)
XSERVER_MARKERS = ("xserver", "x server", "missing x server", "headed browser")


def launch_args(settings: Settings) -> list[str]:
    args = list(BASE_ARGS)
    if settings.browser_no_sandbox:
        args += ["--no-sandbox", "--disable-setuid-sandbox"]
    if settings.browser_disable_dev_shm:
        args.append("--disable-dev-shm-usage")
    return args


def explain_launch_failure(message: str) -> str | None:
    lowered = message.lower()

    if any(marker in lowered for marker in XSERVER_MARKERS):
        return (
            "the container has no display: a headed browser needs xvfb. "
            "Rebuild the backend image so it starts under xvfb-run, or set "
            "AVITO_HEADLESS=true and accept that avito will block the login"
        )
    if "no usable sandbox" in lowered or "running as root without --no-sandbox" in lowered:
        return "chromium cannot sandbox in this container, set BROWSER_NO_SANDBOX=true"
    if "executable doesn't exist" in lowered or "please run the following command" in lowered:
        return "chromium is not installed in the image, run: playwright install chromium"
    if "out of memory" in lowered or "/dev/shm" in lowered:
        return (
            "chromium ran out of shared memory, set BROWSER_DISABLE_DEV_SHM=true or raise shm_size"
        )
    return None
