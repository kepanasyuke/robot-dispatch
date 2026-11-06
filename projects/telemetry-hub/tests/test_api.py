from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from telemetry_hub.api import create_app
from telemetry_hub.ingest import TelemetryIngestor
from telemetry_hub.models import RobotState


@pytest.fixture
def app():
    return create_app(TelemetryIngestor())


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://telemetry.test") as http:
        yield http


def payload(seq: int, **overrides) -> dict:
    sample = {
        "robot_id": "robot-1",
        "seq": seq,
        "ts": "2026-01-01T12:00:00+00:00",
        "battery": 88.5,
        "state": "idle",
        "position": {"x": 1.0, "y": 2.0},
        "metrics": {"speed": 0.4},
    }
    sample.update(overrides)
    return sample


async def test_ingest_batch_reports_outcomes(client) -> None:
    response = await client.post(
        "/api/v1/telemetry", json={"samples": [payload(1), payload(2), payload(1)]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] == 2
    assert body["duplicate"] == 1
    assert len(body["results"]) == 3


async def test_ingest_rejects_malformed_sample(client) -> None:
    response = await client.post("/api/v1/telemetry", json={"samples": [payload(1, battery=140)]})
    assert response.status_code == 422


async def test_naive_timestamp_is_rejected(client) -> None:
    response = await client.post(
        "/api/v1/telemetry", json={"samples": [payload(1, ts="2026-01-01T12:00:00")]}
    )
    assert response.status_code == 422


async def test_unknown_field_is_rejected(client) -> None:
    response = await client.post(
        "/api/v1/telemetry", json={"samples": [payload(1, vendor="acme")]}
    )
    assert response.status_code == 422


async def test_robot_snapshot_and_samples(client) -> None:
    await client.post("/api/v1/telemetry", json={"samples": [payload(1), payload(2)]})

    robot = await client.get("/api/v1/robots/robot-1")
    samples = await client.get("/api/v1/robots/robot-1/samples", params={"limit": 1})

    assert robot.status_code == 200
    body = robot.json()
    assert body["robot_id"] == "robot-1"
    assert body["samples"] == 2
    assert body["state"] == RobotState.IDLE.value
    assert len(samples.json()) == 1


async def test_unknown_robot_returns_404(client) -> None:
    robot = await client.get("/api/v1/robots/ghost")
    samples = await client.get("/api/v1/robots/ghost/samples")

    assert robot.status_code == 404
    assert samples.status_code == 404


async def test_robots_list_and_stats(client) -> None:
    await client.post(
        "/api/v1/telemetry",
        json={"samples": [payload(1), payload(1, robot_id="robot-2", state="busy")]},
    )

    robots = await client.get("/api/v1/robots")
    stats = await client.get("/api/v1/stats")

    assert [item["robot_id"] for item in robots.json()] == ["robot-1", "robot-2"]
    assert stats.json()["robots"] == 2
    assert stats.json()["outcomes"]["accepted"] == 2


async def test_health(client) -> None:
    response = await client.get("/health")
    assert response.json() == {"status": "ok"}
