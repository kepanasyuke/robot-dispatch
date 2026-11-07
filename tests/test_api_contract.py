from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from robot_dispatch.api.deps import get_uow_factory
from robot_dispatch.main import create_app

TASK_FIELDS = {
    "id",
    "type",
    "status",
    "priority",
    "payload",
    "external_id",
    "robot_id",
    "command_id",
    "attempts",
    "max_attempts",
    "timeout_seconds",
    "available_at",
    "lease_expires_at",
    "started_at",
    "finished_at",
    "last_error",
    "result",
    "created_at",
    "updated_at",
    "version",
}

EVENT_FIELDS = {
    "id",
    "task_id",
    "kind",
    "from_status",
    "to_status",
    "robot_id",
    "message",
    "payload",
    "created_at",
}


@pytest.fixture
async def client(uow_factory, settings):
    app = create_app(settings)
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://dispatch.test") as http:
        yield http


async def create_task(client: AsyncClient, **overrides) -> dict:
    payload = {"type": "delivery", "payload": {"target": "a"}, "priority": 100}
    payload.update(overrides)
    response = await client.post("/api/v1/tasks", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({}, "type"),
        ({"type": ""}, "type"),
        ({"type": "   "}, "type"),
        ({"type": "x" * 65}, "type"),
        ({"type": "delivery", "priority": -1}, "priority"),
        ({"type": "delivery", "priority": 1001}, "priority"),
        ({"type": "delivery", "max_attempts": 0}, "max_attempts"),
        ({"type": "delivery", "max_attempts": 11}, "max_attempts"),
        ({"type": "delivery", "timeout_seconds": 0}, "timeout_seconds"),
        ({"type": "delivery", "timeout_seconds": 86_401}, "timeout_seconds"),
        ({"type": "delivery", "external_id": "id" * 65}, "external_id"),
        ({"type": "delivery", "payload": "not-an-object"}, "payload"),
    ],
)
async def test_create_task_validation(client, payload, field) -> None:
    response = await client.post("/api/v1/tasks", json=payload)

    assert response.status_code == 422
    locations = [".".join(str(part) for part in item["loc"]) for item in response.json()["detail"]]
    assert any(field in location for location in locations)


@pytest.mark.parametrize("raw", ["Delivery", " DELIVERY ", "delivery\n", "DeLiVeRy"])
async def test_task_type_is_normalized(client, raw) -> None:
    task = await create_task(client, type=raw)
    assert task["type"] == "delivery"


@pytest.mark.parametrize("priority", [0, 1, 500, 1000])
async def test_priority_boundaries_are_accepted(client, priority) -> None:
    task = await create_task(client, priority=priority)
    assert task["priority"] == priority


async def test_task_response_has_full_contract(client) -> None:
    task = await create_task(client)
    assert set(task) == TASK_FIELDS


async def test_created_event_has_full_contract(client) -> None:
    task = await create_task(client)
    events = (await client.get(f"/api/v1/tasks/{task['id']}/events")).json()
    assert len(events) == 1
    assert set(events[0]) == EVENT_FIELDS
    assert events[0]["kind"] == "created"
    assert events[0]["to_status"] == "pending"


@pytest.mark.parametrize(
    "status", ["pending", "assigned", "running", "retrying", "succeeded", "failed", "cancelled"]
)
async def test_list_filter_by_status_returns_subset(client, status) -> None:
    await create_task(client, external_id="one")
    response = await client.get("/api/v1/tasks", params={"status": status})

    assert response.status_code == 200
    assert all(item["status"] == status for item in response.json()["items"])


@pytest.mark.parametrize("task_type", ["delivery", "patrol", "inventory"])
async def test_list_filter_by_type(client, task_type) -> None:
    await create_task(client, type="delivery", external_id="d-1")
    await create_task(client, type="patrol", external_id="p-1")

    response = await client.get("/api/v1/tasks", params={"type": task_type})
    assert [item["type"] for item in response.json()["items"]] == [
        task_type for _ in range(len(response.json()["items"]))
    ]


@pytest.mark.parametrize("limit", [1, 10, 50, 200])
async def test_list_respects_limit(client, limit) -> None:
    for index in range(3):
        await create_task(client, external_id=f"task-{index}")

    response = await client.get("/api/v1/tasks", params={"limit": limit, "offset": 0})
    body = response.json()
    assert body["limit"] == limit
    assert len(body["items"]) == min(limit, 3)


@pytest.mark.parametrize("limit", [0, 201, -5])
async def test_list_rejects_out_of_range_limit(client, limit) -> None:
    response = await client.get("/api/v1/tasks", params={"limit": limit})
    assert response.status_code == 422


async def test_list_rejects_negative_offset(client) -> None:
    response = await client.get("/api/v1/tasks", params={"offset": -1})
    assert response.status_code == 422


async def test_list_is_paginated(client) -> None:
    for index in range(5):
        await create_task(client, external_id=f"page-{index}")

    first = (await client.get("/api/v1/tasks", params={"limit": 2, "offset": 0})).json()
    second = (await client.get("/api/v1/tasks", params={"limit": 2, "offset": 2})).json()

    assert len(first["items"]) == 2
    assert len(second["items"]) == 2
    assert {item["id"] for item in first["items"]}.isdisjoint({item["id"] for item in second["items"]})


@pytest.mark.parametrize("suffix", ["", "/events", "/cancel"])
async def test_unknown_task_is_404(client, suffix) -> None:
    unknown = uuid.uuid4()
    method = client.post if suffix == "/cancel" else client.get
    response = await method(f"/api/v1/tasks/{unknown}{suffix}")

    assert response.status_code == 404
    assert response.json()["task_id"] == str(unknown)


@pytest.mark.parametrize("raw", ["not-a-uuid", "12345", "00000000-0000-0000-0000-00000000000"])
async def test_malformed_uuid_is_422(client, raw) -> None:
    response = await client.get(f"/api/v1/tasks/{raw}")
    assert response.status_code == 422


async def test_cancel_pending_task(client) -> None:
    task = await create_task(client)
    response = await client.post(f"/api/v1/tasks/{task['id']}/cancel")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["finished_at"] is not None
    assert body["version"] == task["version"] + 1


async def test_second_cancel_is_conflict(client) -> None:
    task = await create_task(client)
    await client.post(f"/api/v1/tasks/{task['id']}/cancel")

    again = await client.post(f"/api/v1/tasks/{task['id']}/cancel")
    assert again.status_code == 409
    assert again.json()["status"] == "cancelled"
    assert again.json()["task_id"] == task["id"]


async def test_cancel_unknown_task_is_404(client) -> None:
    response = await client.post(f"/api/v1/tasks/{uuid.uuid4()}/cancel")
    assert response.status_code == 404


@pytest.mark.parametrize(
    "capabilities", [["Delivery"], [" delivery ", "DELIVERY", "patrol"], ["a", "b", "a"]]
)
async def test_robot_capabilities_are_normalized(client, capabilities) -> None:
    response = await client.post(
        "/api/v1/robots",
        json={"name": "robot-1", "namespace": "/robot1", "capabilities": capabilities},
    )

    assert response.status_code == 201
    values = response.json()["capabilities"]
    assert values == sorted({value.strip().lower() for value in capabilities})


async def test_robot_registration_is_idempotent_by_name(client) -> None:
    first = await client.post("/api/v1/robots", json={"name": "robot-1", "namespace": "/r1"})
    second = await client.post(
        "/api/v1/robots", json={"name": "robot-1", "namespace": "/r1", "capabilities": ["patrol"]}
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "namespace": "/r1", "capabilities": ["delivery"]},
        {"name": "r" * 129, "namespace": "/r1", "capabilities": ["delivery"]},
        {"name": "robot-1", "namespace": "", "capabilities": ["delivery"]},
        {"name": "robot-1", "namespace": "/r1", "capabilities": []},
        {"name": "robot-1", "namespace": "/r1", "capabilities": ["  "]},
    ],
)
async def test_robot_registration_validation(client, body) -> None:
    response = await client.post("/api/v1/robots", json=body)
    assert response.status_code == 422


async def test_unknown_robot_is_404(client) -> None:
    response = await client.get(f"/api/v1/robots/{uuid.uuid4()}")
    assert response.status_code == 404
    assert "robot_id" in response.json()


async def test_stats_reports_statuses(client) -> None:
    await create_task(client, external_id="s-1")
    await create_task(client, external_id="s-2")
    await client.post("/api/v1/robots", json={"name": "robot-1", "namespace": "/r1"})

    body = (await client.get("/api/v1/stats")).json()

    assert body["task_total"] == 2
    assert body["tasks"]["pending"] == 2
    assert sum(count for status, count in body["tasks"].items() if status != "pending") == 0
    assert body["robots"] == {"idle": 1}


async def test_liveness_is_always_ok(client) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {}}


async def test_readiness_reports_database_check(client) -> None:
    response = await client.get("/health/ready")
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"


async def test_request_id_header_is_echoed(client) -> None:
    response = await client.get("/api/v1/tasks", headers={"X-Request-ID": "trace-42"})
    assert response.headers["X-Request-ID"] == "trace-42"


async def test_request_id_is_generated(client) -> None:
    response = await client.get("/api/v1/tasks")
    assert len(response.headers["X-Request-ID"]) == 32


async def test_idempotency_key_header_is_stable(client) -> None:
    headers = {"Idempotency-Key": "client-77"}
    first = await client.post("/api/v1/tasks", json={"type": "delivery"}, headers=headers)
    second = await client.post("/api/v1/tasks", json={"type": "delivery"}, headers=headers)

    assert first.json()["id"] == second.json()["id"]
    assert second.headers["Idempotent-Replay"] == "true"


async def test_body_external_id_wins_over_header(client) -> None:
    headers = {"Idempotency-Key": "header-key"}
    first = await client.post(
        "/api/v1/tasks", json={"type": "delivery", "external_id": "body-key"}, headers=headers
    )
    second = await client.post(
        "/api/v1/tasks",
        json={"type": "delivery", "external_id": "body-key"},
        headers={"Idempotency-Key": "other"},
    )

    assert first.json()["external_id"] == "body-key"
    assert second.json()["id"] == first.json()["id"]


async def test_different_idempotency_keys_create_different_tasks(client) -> None:
    first = await client.post("/api/v1/tasks", json={"type": "delivery"}, headers={"Idempotency-Key": "a"})
    second = await client.post("/api/v1/tasks", json={"type": "delivery"}, headers={"Idempotency-Key": "b"})

    assert first.json()["id"] != second.json()["id"]


async def test_missing_api_key_is_rejected(uow_factory, settings) -> None:
    secured = settings.model_copy(update={"api_key": "secret"})
    app = create_app(secured)
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://dispatch.test") as http:
        denied = await http.get("/api/v1/tasks")
        wrong = await http.get("/api/v1/tasks", headers={"X-API-Key": "nope"})
        allowed = await http.get("/api/v1/tasks", headers={"X-API-Key": "secret"})

    assert denied.status_code == 401
    assert wrong.status_code == 401
    assert allowed.status_code == 200
