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
    can_submit_code,
    expire,
    expires_at,
    is_terminal,
)
from app.domain.proxy import mask_proxy_url
from app.domain.rotation import clamp_daily_limit
from app.domain.schemas import LoginSessionRead, LoginStartRequest
from app.errors import ConflictError, NotFoundError, ValidationFailedError

SLUG = re.compile(r"[^a-z0-9._-]+")


@dataclass
class LoginRun:
    session: LoginSession
    client: AvitoAuthClient
    proxy_url: str | None
    daily_limit: int
    screenshot: bytes | None = None
    # kept in process memory only, for the life of this login session, so that a
    # check cleared by hand can be resumed. Wiped the moment the session ends and
    # never written to the database, a log line or an api response.
    password: str | None = None


_runs: dict[str, LoginRun] = {}


def reset_login_runs() -> None:
    _runs.clear()


def _slug(login: str) -> str:
    cleaned = SLUG.sub("-", login.strip().lower()).strip("-")
    return cleaned or "account"


class LoginService:
    def __init__(self, session: AsyncSession, client: AvitoAuthClient, settings: Settings) -> None:
        self.session = session
        self.client = client
        self.settings = settings

    async def start(self, request: LoginStartRequest) -> LoginSessionRead:
        payload = LoginStartRequest.model_validate(request)
        await self._ensure_login_free(payload.login)

        now = datetime.now(UTC)
        session = LoginSession(
            session_id=uuid4().hex,
            login=payload.login,
            status="starting",
            created_at=now,
            updated_at=now,
        )
        run = LoginRun(
            session=session,
            client=self.client,
            proxy_url=payload.proxy_url,
            daily_limit=clamp_daily_limit(payload.daily_limit),
            password=payload.password.get_secret_value(),
        )
        _runs[session.session_id] = run

        try:
            step = await self.client.start(
                payload.login,
                payload.password.get_secret_value(),
                payload.proxy_url,
            )
        except Exception as error:
            logger.warning(
                "login for {login} crashed: {kind}",
                login=payload.login,
                kind=type(error).__name__,
            )
            run.screenshot = await self._safe_screenshot(run)
            await self._finish(
                run,
                "failed",
                f"login crashed: {describe(error, payload.password.get_secret_value())}",
            )
            return self._read(run)

        await self._apply(run, step)
        return self._read(run)

    async def state(self, session_id: str) -> LoginSessionRead:
        run = self._require(session_id)
        await self._sweep(run)
        return self._read(run)

    async def submit_code(self, session_id: str, code: str) -> LoginSessionRead:
        run = self._require(session_id)
        await self._sweep(run)

        if not can_submit_code(run.session):
            raise ConflictError(f"session is in status {run.session.status}, it expects no code")
        if not code.strip():
            raise ValidationFailedError("code must not be empty")

        try:
            step = await run.client.submit_code(code.strip())
        except Exception as error:
            await self._finish(run, "failed", f"code check crashed: {describe(error)}")
            return self._read(run)

        await self._apply(run, step)
        return self._read(run)

    async def resume(self, session_id: str) -> LoginSessionRead:
        run = self._require(session_id)
        await self._sweep(run)

        if is_terminal(run.session):
            raise ConflictError(f"session is {run.session.status}, there is nothing to resume")
        if run.password is None:
            raise ConflictError("this login session can no longer be resumed, start again")

        try:
            step = await run.client.resume(run.session.login, run.password)
        except Exception as error:
            run.screenshot = await self._safe_screenshot(run)
            await self._finish(run, "failed", f"resume crashed: {describe(error, run.password)}")
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
        status = step.status
        hint = step.hint
        now = datetime.now(UTC)

        if status != "saving":
            run.screenshot = await self._safe_screenshot(run)

        if status == "saving":
            await self._persist(run, now)
            return

        if status == "failed":
            await self._finish(run, "failed", hint)
            return

        run.session = advance(
            run.session, status, now, hint=hint, has_screenshot=bool(run.screenshot)
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
            "account {login} signed in and stored, proxy {proxy}",
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
        run.password = None
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

    async def _ensure_login_free(self, login: str) -> None:
        if await self.session.scalar(select(Account.id).where(Account.login == login)) is not None:
            raise ConflictError(f"account with login {login!r} already exists")

    def _remote_view_url(self, run: LoginRun) -> str | None:
        # only handed out while a person is actually needed at the browser
        if not self.settings.vnc_enabled or not self.settings.vnc_public_url:
            return None
        if not awaits_operator(run.session):
            return None
        return self.settings.vnc_public_url

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
