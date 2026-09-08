from typing import TYPE_CHECKING

from app.config import get_settings

if TYPE_CHECKING:
    from app.clients.proxy.base import ProxyProvider


def get_proxy_provider() -> "ProxyProvider":
    if get_settings().proxy_provider == "lteboost":
        from app.clients.proxy.lteboost import LteboostProxyProvider

        return LteboostProxyProvider()

    from app.clients.proxy.fake import FakeProxyProvider

    return FakeProxyProvider()
