from typing import Annotated

from fastapi import Depends, Header

from app.config import Settings, get_settings
from app.errors import UnauthorizedError

PANEL_TOKEN_HEADER = "X-Panel-Token"


async def require_panel_token(
    settings: Annotated[Settings, Depends(get_settings)],
    x_panel_token: Annotated[str | None, Header(alias=PANEL_TOKEN_HEADER)] = None,
) -> None:
    if not settings.panel_api_token:
        return
    if x_panel_token != settings.panel_api_token:
        raise UnauthorizedError("panel token is missing or invalid")
