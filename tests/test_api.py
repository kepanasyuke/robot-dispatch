from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from robot_dispatch.api.deps import get_uow_factory
from robot_dispatch.main import create_app


@pytest.fixture
async def client(uow_factory, settings):
    app = create_app(settings)
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://dispatch.test") as http:
        yield http


async def test_create_task_returns_201_and_location(client) -> None:
    response = await client.post("/api/v1/tasks", json={"type": "Delivery", "payload": {"n": 1}})

    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "delivery"
    assert body["status"] == "pending"
    assert body["attempts"] == 0
    assert response.headers["location"] == f"/api/v1/tasks/{body['id']}"
    assert "X-Request-ID" in response.headers


async def test_idempotent_create_returns_the_same_task(client) -> None:
    payload = {"type": "delivery", "payload": {}, "external_id": "order-1"}

    first = await client.post("/api/v1/tasks", json=payload)
    second = await client.post("/api/v1/tasks", json=payload)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.headers["Idempotent-Replay"] == "true"
    assert second.json()["id"] == first.json()["id"]


async def test_idempotency_key_header_is_honoured(client) -> None:
    headers = {"Idempotency-Key": "client-key-9"}

    first = await client.post("/api/v1/tasks", json={"type": "delivery"}, headers=headers)
    second = await client.post("/api/v1/tasks", json={"type": "delivery"}, headers=headers)

    assert first.json()["id"] == second.json()["id"]
    assert second.status_code == 200


async def test_list_and_filter_tasks(client) -> None:
    await client.post("/api/v1/tasks", json={"type": "delivery", "priority": 10})
    await client.post("/api/v1/tasks", json={"type": "patrol", "priority": 20})

    all_tasks = await client.get("/api/v1/tasks")
    delivery = await client.get("/api/v1/tasks", params={"type": "delivery"})
    pending = await client.get("/api/v1/tasks", params={"status": "pending"})
    failed = await client.get("/api/v1/tasks", params={"status": "failed"})

    assert all_tasks.json()["limit"] == 50
    assert len(all_tasks.json()["items"]) == 2
    assert len(delivery.json()["items"]) == 1
    assert len(pending.json()["items"]) == 2
    assert failed.json()["items"] == []


async def test_get_task_and_events(client) -> None:
    created = (await client.post("/api/v1/tasks", json={"type": "delivery"})).json()

    task = await client.get(f"/api/v1/tasks/{created['id']}")
    events = await client.get(f"/api/v1/tasks/{created['id']}/events")

    assert task.status_code == 200
    assert task.json()["id"] == created["id"]
    assert [event["kind"] for event in events.json()] == ["created"]


async def test_get_unknown_task_returns_404(client) -> None:
    response = await client.get("/api/v1/tasks/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


async def test_invalid_uuid_is_422(client) -> None:
    response = await client.get("/api/v1/tasks/not-a-uuid")
    assert response.status_code == 422


async def test_cancel_task(client) -> None:
    created = (await client.post("/api/v1/tasks", json={"type": "delivery"})).json()

    response = await client.post(f"/api/v1/tasks/{created['id']}/cancel")
    again = await client.post(f"/api/v1/tasks/{created['id']}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert again.status_code == 409
    assert again.json()["status"] == "cancelled"


async def test_register_and_list_robots(client) -> None:
    created = await client.post(
        "/api/v1/robots",
        json={"name": "robot-1", "namespace": "/robot1", "capabilities": ["Delivery", "patrol"]},
    )
    updated = await client.post(
        "/api/v1/robots",
        json={"name": "robot-1", "namespace": "/robot1", "capabilities": ["delivery"]},
    )
    listed = await client.get("/api/v1/robots")

    assert created.status_code == 201
    assert created.json()["capabilities"] == ["delivery", "patrol"]
    assert created.json()["status"] == "idle"
    assert updated.status_code == 200
    assert len(listed.json()["items"]) == 1


async def test_robot_requires_capabilities(client) -> None:
    response = await client.post(
        "/api/v1/robots", json={"name": "robot-x", "namespace": "/rx", "capabilities": []}
    )
    assert response.status_code == 422


async def test_stats_endpoint(client) -> None:
    await client.post("/api/v1/tasks", json={"type": "delivery"})
    await client.post("/api/v1/robots", json={"name": "robot-1", "namespace": "/r1"})

    response = await client.get("/api/v1/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["tasks"]["pending"] == 1
    assert body["task_total"] == 1
    assert body["robots"] == {"idle": 1}
    assert body["queues"] == {}


async def test_liveness_endpoint(client) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_api_key_is_enforced_when_configured(uow_factory, settings) -> None:
    secured = settings.model_copy(update={"api_key": "secret"})
    app = create_app(secured)
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://dispatch.test") as http:
        denied = await http.get("/api/v1/tasks")
        allowed = await http.get("/api/v1/tasks", headers={"X-API-Key": "secret"})

    assert denied.status_code == 401
    assert allowed.status_code == 200
