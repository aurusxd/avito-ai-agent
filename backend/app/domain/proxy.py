from typing import NotRequired, TypedDict
from urllib.parse import quote, unquote, urlsplit, urlunsplit

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
    # a url carries credentials percent-encoded, the proxy expects them raw
    return (
        parts.scheme,
        parts.hostname + port,
        unquote(parts.username or ""),
        unquote(parts.password or ""),
    )


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


def line_to_url(line: str, protocol: str = "http") -> str | None:
    """Turn a provider line `host:port:login:password` into a proxy url.

    Providers encode sticky session options inside the password, so it can carry
    characters that break a url and has to be quoted.
    """
    parts = line.strip().split(":")
    if len(parts) < 4:
        return None

    host, port, login = parts[0], parts[1], parts[2]
    password = ":".join(parts[3:])
    if not host or not port.isdigit() or not login:
        return None

    credentials = f"{quote(login, safe='')}:{quote(password, safe='')}"
    return urlunsplit((protocol, f"{credentials}@{host}:{port}", "", "", ""))


def session_id_from_line(line: str) -> str | None:
    marker = "_session-"
    _, _, tail = line.partition(marker)
    if not tail:
        return None
    return tail.split("_")[0] or None


def proxy_auth_line(url: str | None) -> str | None:
    """Turn a proxy url into the `login:password@host:port` line spfa expects (§27.6).

    Credentials come back decoded: the service rejects a percent-encoded password
    the same way the proxy itself would.
    """
    if not url:
        return None
    parts = _split(url)
    if parts is None:
        return None
    _, host, username, password = parts
    if not username or not password:
        return None
    return f"{username}:{password}@{host}"
