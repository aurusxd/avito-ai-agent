from httpx import AsyncClient

from app.scheduler import DEMO_JOB_ID, is_running, shutdown_scheduler, start_scheduler


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
        assert [job.id for job in second.get_jobs()] == [DEMO_JOB_ID]
    finally:
        shutdown_scheduler()

    assert is_running() is False
