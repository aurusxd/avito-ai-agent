from httpx import AsyncClient

from app.scheduler import (
    DEMO_JOB_ID,
    LEADS_JOB_ID,
    is_running,
    shutdown_scheduler,
    start_scheduler,
)


async def test_health_reports_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] is True


async def test_unknown_route_returns_404(client: AsyncClient) -> None:
    response = await client.get("/api/does-not-exist")

    assert response.status_code == 404


async def test_start_scheduler_is_idempotent() -> None:
    try:
        first = start_scheduler()
        second = start_scheduler()

        assert first is second
        assert is_running() is True
        assert sorted(job.id for job in second.get_jobs()) == sorted([DEMO_JOB_ID, LEADS_JOB_ID])
    finally:
        shutdown_scheduler()

    assert is_running() is False


async def test_validation_errors_never_echo_the_rejected_value(client) -> None:
    response = await client.post(
        "/api/categories", json={"name": "", "avito_url_or_slug": "x", "region": "sensitive-value"}
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert "sensitive-value" not in response.text
    for detail in body["error"]["details"]:
        assert set(detail) <= {"loc", "msg", "type"}
