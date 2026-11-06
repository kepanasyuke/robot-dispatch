from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fleet_monitor.api import create_app
from fleet_monitor.monitor import FleetMonitor
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def monitor() -> FleetMonitor:
    return FleetMonitor()


@pytest.fixture
async def client(monitor):
    app = create_app(monitor)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://monitor.test") as http:
        yield http


def stale_sample(robot_id: str = "robot-1", **overrides) -> dict:
    last_seen = (datetime.now(tz=UTC) - timedelta(minutes=5)).isoformat()
    payload = {"robot_id": robot_id, "last_seen": last_seen, "error_rate": 0.0}
    payload.update(overrides)
    return payload


async def test_health_sample_creates_alert(client) -> None:
    response = await client.post("/api/v1/health", json=stale_sample())

    assert response.status_code == 200
    body = response.json()
    assert body["evaluated"] == 1
    assert body["alerts"][0]["type"] == "offline"
    assert body["alerts"][0]["status"] == "open"


async def test_alert_workflow_ack_and_resolve(client) -> None:
    created = (await client.post("/api/v1/health", json=stale_sample())).json()
    alert_id = created["alerts"][0]["id"]

    acked = await client.post(f"/api/v1/alerts/{alert_id}/ack", json={"by": "operator"})
    resolved = await client.post(f"/api/v1/alerts/{alert_id}/resolve")
    again = await client.post(f"/api/v1/alerts/{alert_id}/resolve")

    assert acked.status_code == 200
    assert acked.json()["status"] == "acked"
    assert acked.json()["acknowledged_by"] == "operator"
    assert resolved.json()["status"] == "resolved"
    assert again.status_code == 409


async def test_unknown_alert_returns_404(client) -> None:
    ack = await client.post("/api/v1/alerts/alert-ghost/ack", json={"by": "operator"})
    resolve = await client.post("/api/v1/alerts/alert-ghost/resolve")

    assert ack.status_code == 404
    assert resolve.status_code == 404


async def test_alerts_filtering(client) -> None:
    await client.post("/api/v1/health", json=stale_sample("robot-1"))
    fresh = datetime.now(tz=UTC).isoformat()
    await client.post(
        "/api/v1/health",
        json={"robot_id": "robot-2", "last_seen": fresh, "battery_percent": 5.0},
    )

    all_alerts = await client.get("/api/v1/alerts")
    robots = await client.get("/api/v1/alerts", params={"robot_id": "robot-2"})

    assert len(all_alerts.json()) == 2
    assert len(robots.json()) == 1
    assert robots.json()[0]["type"] == "low_battery"


async def test_metrics_endpoint(client) -> None:
    await client.post("/api/v1/health", json=stale_sample())

    response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "fleet_robots_known 1" in body
    assert "fleet_alerts_active 1" in body
    assert 'fleet_alerts_active_by_severity{severity="critical"} 1' in body


async def test_invalid_battery_is_rejected(client) -> None:
    response = await client.post("/api/v1/health", json={"robot_id": "robot-1", "battery_percent": 150})
    assert response.status_code == 422


async def test_naive_timestamp_is_rejected(client) -> None:
    response = await client.post(
        "/api/v1/health",
        json={"robot_id": "robot-1", "last_seen": "2026-01-01T12:00:00"},
    )
    assert response.status_code == 422


async def test_robots_endpoint(client) -> None:
    await client.post("/api/v1/health", json=stale_sample())

    response = await client.get("/api/v1/robots")

    assert response.json()[0]["robot_id"] == "robot-1"


async def test_health_endpoint(client) -> None:
    response = await client.get("/health")
    assert response.json() == {"status": "ok"}
