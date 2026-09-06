from typing import NotRequired, TypedDict
from urllib.parse import urlsplit, urlunsplit

MASK = "***"


class ProxyCredentials(TypedDict):
    server: str
    username: NotRequired[str]
    password: NotRequired[str]


def _split(url: str) -> tuple[str, str, str, str] | None:
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.hostname:
        return None
    port = f":{parts.port}" if parts.port else ""
    return parts.scheme, parts.hostname + port, parts.username or "", parts.password or ""


def mask_proxy_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = _split(url)
    if parts is None:
        return MASK
    scheme, host, username, _ = parts
    netloc = f"{MASK}@{host}" if username else host
    return urlunsplit((scheme, netloc, "", "", ""))


def proxy_settings(url: str | None) -> ProxyCredentials | None:
    if not url:
        return None
    parts = _split(url)
    if parts is None:
        return None
    scheme, host, username, password = parts
    settings: ProxyCredentials = {"server": urlunsplit((scheme, host, "", "", ""))}
    if username:
        settings["username"] = username
    if password:
        settings["password"] = password
    return settings
