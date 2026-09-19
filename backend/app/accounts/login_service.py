import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.avito.base import AvitoAuthClient, LoginStep
from app.clients.avito.playwright_auth import describe
from app.config import BACKEND_ROOT, Settings
from app.db.models import Account
from app.domain.auth_session import (
    LoginSession,
    LoginStatusLiteral,
    advance,
    awaits_operator,
    can_confirm,
    expire,
    expires_at,
    is_terminal,
)
from app.domain.proxy import mask_proxy_url
from app.domain.rotation import clamp_daily_limit
from app.domain.schemas import LoginSessionRead, LoginStartRequest
from app.errors import AppError, ConflictError, NotFoundError

SLUG = re.compile(r"[^a-z0-9._-]+")


@dataclass
class LoginRun:
    session: LoginSession
    client: AvitoAuthClient
    proxy_url: str | None
    daily_limit: int
    screenshot: bytes | None = None


_runs: dict[str, LoginRun] = {}


def reset_login_runs() -> None:
    _runs.clear()


def _slug(login: str) -> str:
    cleaned = SLUG.sub("-", login.strip().lower()).strip("-")
    return cleaned or "account"


class LoginService:
    """Hands a browser to a person and keeps whatever session they create.

    The sign in itself is entirely manual: the operator works in the bot's own
    browser over noVNC. Nothing here sees a password, a captcha or an sms code.
    """

    def __init__(self, session: AsyncSession, client: AvitoAuthClient, settings: Settings) -> None:
        self.session = session
        self.client = client
        self.settings = settings

    async def start(self, request: LoginStartRequest) -> LoginSessionRead:
        payload = LoginStartRequest.model_validate(request)
        await self._ensure_login_free(payload.login)
        self._ensure_remote_view_ready()

        now = datetime.now(UTC)
        run = LoginRun(
            session=LoginSession(
                session_id=uuid4().hex,
                login=payload.login,
                status="starting",
                created_at=now,
                updated_at=now,
            ),
            client=self.client,
            proxy_url=payload.proxy_url,
            daily_limit=clamp_daily_limit(payload.daily_limit),
        )
        _runs[run.session.session_id] = run

        try:
            step = await self.client.open(payload.proxy_url)
        except Exception as error:
            logger.warning("opening the browser crashed: {reason}", reason=describe(error))
            run.screenshot = await self._safe_screenshot(run)
            await self._finish(run, "failed", f"browser crashed: {describe(error)}")
            return self._read(run)

        await self._apply(run, step)
        return self._read(run)

    async def state(self, session_id: str) -> LoginSessionRead:
        run = self._require(session_id)
        await self._sweep(run)
        return self._read(run)

    async def confirm(self, session_id: str) -> LoginSessionRead:
        run = self._require(session_id)
        await self._sweep(run)

        if not can_confirm(run.session):
            raise ConflictError(f"session is {run.session.status}, there is nothing to confirm")

        try:
            step = await run.client.check()
        except Exception as error:
            run.screenshot = await self._safe_screenshot(run)
            await self._finish(run, "failed", f"session check crashed: {describe(error)}")
            return self._read(run)

        await self._apply(run, step)
        return self._read(run)

    async def cancel(self, session_id: str) -> LoginSessionRead:
        run = self._require(session_id)
        if not is_terminal(run.session):
            await self._finish(run, "failed", "cancelled from the panel")
        return self._read(run)

    def screenshot(self, session_id: str) -> bytes:
        run = self._require(session_id)
        if run.screenshot is None:
            raise NotFoundError(f"session {session_id} has no screenshot")
        return run.screenshot

    async def _apply(self, run: LoginRun, step: LoginStep) -> None:
        now = datetime.now(UTC)

        if step.status != "saving":
            run.screenshot = await self._safe_screenshot(run)

        if step.status == "saving":
            await self._persist(run, now)
            return

        if step.status == "failed":
            await self._finish(run, "failed", step.hint)
            return

        run.session = advance(
            run.session, step.status, now, hint=step.hint, has_screenshot=bool(run.screenshot)
        )

    async def _persist(self, run: LoginRun, now: datetime) -> None:
        run.session = advance(run.session, "saving", now)

        try:
            state = await run.client.storage_state()
        except Exception as error:
            await self._finish(run, "failed", f"could not read the session: {describe(error)}")
            return

        relative = Path(self.settings.sessions_dir) / f"{_slug(run.session.login)}.storage.json"
        target = BACKEND_ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        account = Account(
            login=run.session.login,
            session_storage_path=str(relative).replace("\\", "/"),
            daily_limit=run.daily_limit,
            proxy_url=run.proxy_url,
        )
        self.session.add(account)
        await self.session.commit()
        await self.session.refresh(account)

        logger.info(
            "account {login} signed in by hand and stored, proxy {proxy}",
            login=account.login,
            proxy=mask_proxy_url(run.proxy_url) if run.proxy_url else "direct",
        )

        run.session = advance(
            run.session, "done", datetime.now(UTC), hint=None, account_id=account.id
        )
        await self._release(run)

    async def _finish(self, run: LoginRun, status: LoginStatusLiteral, hint: str | None) -> None:
        run.session = advance(
            run.session,
            status,
            datetime.now(UTC),
            hint=hint,
            has_screenshot=bool(run.screenshot),
        )
        await self._release(run)

    async def _safe_screenshot(self, run: LoginRun) -> bytes | None:
        try:
            return await run.client.screenshot()
        except Exception:
            logger.debug("could not take a login screenshot")
            return None

    async def _release(self, run: LoginRun) -> None:
        try:
            await run.client.close()
        except Exception:
            logger.debug("login browser was already gone")

    async def _sweep(self, run: LoginRun) -> None:
        now = datetime.now(UTC)
        expired = expire(run.session, now, self.settings.login_session_ttl_seconds)
        if expired is not run.session and expired.status == "expired":
            run.session = expired
            await self._release(run)

    def _require(self, session_id: str) -> LoginRun:
        run = _runs.get(session_id)
        if run is None:
            raise NotFoundError(f"login session {session_id} not found")
        return run

    def _ensure_remote_view_ready(self) -> None:
        # the operator signs in inside the browser, so without the remote view
        # there is no way to finish and the session would only time out; the
        # showcase logs in on its own and needs no window
        if self.settings.demo_mode:
            return
        if not self.settings.vnc_enabled or not self.settings.vnc_public_url:
            raise AppError(
                "remote browser view is off: set VNC_ENABLED, VNC_PASSWORD and "
                "VNC_PUBLIC_URL, otherwise nobody can sign in"
            )

    async def _ensure_login_free(self, login: str) -> None:
        if await self.session.scalar(select(Account.id).where(Account.login == login)) is not None:
            raise ConflictError(f"account with login {login!r} already exists")

    def _remote_view_url(self, run: LoginRun) -> str | None:
        if not awaits_operator(run.session):
            return None
        return self.settings.vnc_public_url or None

    def _read(self, run: LoginRun) -> LoginSessionRead:
        return LoginSessionRead(
            session_id=run.session.session_id,
            login=run.session.login,
            status=run.session.status,
            hint=run.session.hint,
            account_id=run.session.account_id,
            has_screenshot=run.session.has_screenshot,
            remote_view_url=self._remote_view_url(run),
            expires_at=expires_at(run.session, self.settings.login_session_ttl_seconds),
        )
