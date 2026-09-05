from app.clients.telegram.base import LeadNotification


class FakeNotifier:
    def __init__(self, failure: Exception | None = None, fail_times: int = 0) -> None:
        self.failure = failure
        self.fail_times = fail_times
        self.sent: list[LeadNotification] = []

    def _maybe_fail(self) -> None:
        if self.failure is not None and self.fail_times > 0:
            self.fail_times -= 1
            raise self.failure

    async def send_lead(self, notification: LeadNotification) -> None:
        validated = LeadNotification.model_validate(notification)
        self._maybe_fail()
        self.sent.append(validated)
