from app.clients.avito.base import LoginStep

VALID_CODE = "111111"
CAPTCHA_LOGIN = "captcha-user"
BAD_PASSWORD = "wrong"


class FakeAvitoAuthClient:
    provider = "fake"

    def __init__(self, code: str = VALID_CODE, captcha_rounds: int = 0) -> None:
        self.expected_code = code
        self.captcha_rounds = captcha_rounds
        self.resume_calls = 0
        self.login: str | None = None
        self.proxy_url: str | None = None
        self.closed = False
        self.code_attempts = 0
        self.saw_password = False

    async def start(self, login: str, password: str, proxy_url: str | None = None) -> LoginStep:
        self.login = login
        self.proxy_url = proxy_url
        self.saw_password = bool(password)

        if not password or password == BAD_PASSWORD:
            return LoginStep(status="failed", hint="avito rejected the login or password")
        if login == CAPTCHA_LOGIN:
            return LoginStep(status="captcha_required", hint="avito asks for a captcha")
        return LoginStep(status="code_required", hint="enter the code from the sms")

    async def resume(self, login: str, password: str) -> LoginStep:
        self.resume_calls += 1
        if login == CAPTCHA_LOGIN and self.resume_calls <= self.captcha_rounds:
            return LoginStep(status="captcha_required", hint="avito asks for a captcha")
        return LoginStep(status="code_required", hint="enter the code from the sms")

    async def submit_code(self, code: str) -> LoginStep:
        self.code_attempts += 1
        if code != self.expected_code:
            return LoginStep(status="code_required", hint="wrong code, try again")
        return LoginStep(status="saving", hint=None)

    async def storage_state(self) -> dict[str, object]:
        return {
            "cookies": [{"name": "sessid", "value": "fake", "domain": ".avito.ru"}],
            "origins": [],
        }

    async def screenshot(self) -> bytes | None:
        return b"fake-png"

    async def close(self) -> None:
        self.closed = True
