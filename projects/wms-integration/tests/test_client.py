from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from wms_integration.circuit import CircuitBreaker, CircuitOpenError, CircuitState
from wms_integration.client import HttpRequestError, ResilientHttpClient, RetryPolicy
from wms_integration.orders import OrderSyncService, OrderValidationError, WmsOrder

BASE_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, moment: datetime = BASE_TIME) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, seconds: float) -> datetime:
        self.moment += timedelta(seconds=seconds)
        return self.moment


class FakeSleep:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


class ScriptedTransport:
    """Returns scripted responses and records every request."""

    def __init__(self, responses: list[httpx.Response | Exception]) -> None:
        self.responses = responses
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self.responses) - 1)
        item = self.responses[index]
        if isinstance(item, Exception):
            raise item
        return item


def build_client(
    transport: ScriptedTransport,
    *,
    retry: RetryPolicy | None = None,
    breaker: CircuitBreaker | None = None,
) -> tuple[ResilientHttpClient, FakeSleep]:
    sleep = FakeSleep()
    client = ResilientHttpClient(
        base_url="http://wms.test",
        retry=retry or RetryPolicy(max_attempts=3, base_delay_seconds=0.0, jitter_ratio=0.0),
        breaker=breaker or CircuitBreaker(failure_threshold=5, clock=FakeClock()),
        sleep=sleep,
        transport=httpx.MockTransport(transport),
    )
    return client, sleep


async def test_successful_request_reports_single_attempt() -> None:
    transport = ScriptedTransport([httpx.Response(200, json={"ok": True})])
    client, sleep = build_client(transport)

    result = await client.get_json("/api/v1/tasks")

    assert result.status_code == 200
    assert result.json_body == {"ok": True}
    assert result.attempts == 1
    assert sleep.delays == []
    await client.aclose()


async def test_retries_on_server_error_and_recovers() -> None:
    transport = ScriptedTransport([httpx.Response(503), httpx.Response(200, json={"ok": True})])
    client, sleep = build_client(transport)

    result = await client.get_json("/api/v1/tasks")

    assert result.attempts == 2
    assert len(sleep.delays) == 1
    await client.aclose()


async def test_client_error_is_not_retried() -> None:
    transport = ScriptedTransport([httpx.Response(400, json={"detail": "bad"})])
    client, sleep = build_client(transport)

    with pytest.raises(HttpRequestError) as error:
        await client.post_json("/api/v1/tasks", {"type": "delivery"})

    assert error.value.status_code == 400
    assert error.value.attempts == 1
    assert sleep.delays == []
    assert client.breaker.failures == 0  # the dependency is alive
    await client.aclose()


async def test_retries_are_exhausted_on_persistent_failure() -> None:
    transport = ScriptedTransport([httpx.Response(500)])
    client, sleep = build_client(transport)

    with pytest.raises(HttpRequestError) as error:
        await client.get_json("/api/v1/tasks")

    assert error.value.attempts == 3
    assert len(transport.requests) == 3
    assert len(sleep.delays) == 2
    assert client.breaker.failures == 1
    await client.aclose()


async def test_timeout_is_retried() -> None:
    transport = ScriptedTransport([httpx.ConnectTimeout("timeout"), httpx.Response(200, json={})])
    client, sleep = build_client(transport)

    result = await client.get_json("/api/v1/tasks")

    assert result.attempts == 2
    assert len(sleep.delays) == 1
    await client.aclose()


async def test_idempotency_key_is_reused_on_every_attempt() -> None:
    transport = ScriptedTransport([httpx.Response(503), httpx.Response(503), httpx.Response(201, json={})])
    client, _sleep = build_client(transport)

    await client.post_json("/api/v1/tasks", {"type": "delivery"}, idempotency_key="order-1")

    keys = [request.headers["Idempotency-Key"] for request in transport.requests]
    assert keys == ["order-1", "order-1", "order-1"]
    await client.aclose()


async def test_open_circuit_stops_traffic() -> None:
    breaker = CircuitBreaker(failure_threshold=1, clock=FakeClock())
    transport = ScriptedTransport([httpx.Response(500)])
    client, _sleep = build_client(transport, breaker=breaker)

    with pytest.raises(HttpRequestError):
        await client.get_json("/api/v1/tasks")
    assert breaker.state is CircuitState.OPEN
    attempts_before = len(transport.requests)

    with pytest.raises(CircuitOpenError):
        await client.get_json("/api/v1/tasks")
    assert len(transport.requests) == attempts_before
    await client.aclose()


async def test_half_open_probe_closes_circuit() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=timedelta(seconds=10), clock=clock)
    transport = ScriptedTransport(
        [httpx.Response(500), httpx.Response(500), httpx.Response(500), httpx.Response(200, json={})]
    )
    client, _sleep = build_client(transport, breaker=breaker)

    with pytest.raises(HttpRequestError):
        await client.get_json("/api/v1/tasks")

    clock.advance(11)
    assert breaker.state is CircuitState.HALF_OPEN
    result = await client.get_json("/api/v1/tasks")

    assert result.status_code == 200
    assert breaker.state is CircuitState.CLOSED
    await client.aclose()


async def test_order_is_mapped_to_task_payload() -> None:
    client_sync = OrderSyncService(client=None)  # type: ignore[arg-type]
    order = WmsOrder(
        order_id="A-100",
        destination="warehouse-a",
        priority=200,
        items=3,
        deadline=BASE_TIME,
        comment="fragile",
    )

    payload = client_sync.to_task_payload(order)

    assert payload["type"] == "delivery"
    assert payload["external_id"] == "wms:A-100"
    assert payload["priority"] == 200
    assert payload["payload"] == {
        "destination": "warehouse-a",
        "items": 3,
        "wms_order_id": "A-100",
        "comment": "fragile",
        "deadline": BASE_TIME.isoformat(),
    }


@pytest.mark.parametrize(
    "order",
    [
        WmsOrder(order_id="A-1", destination=" "),
        WmsOrder(order_id="A-1", destination="a", items=0),
        WmsOrder(order_id="A-1", destination="a", priority=5000),
    ],
)
def test_invalid_order_is_rejected(order) -> None:
    service = OrderSyncService(client=None)  # type: ignore[arg-type]
    with pytest.raises(OrderValidationError):
        service.to_task_payload(order)


async def test_sync_reports_created_and_replayed() -> None:
    transport = ScriptedTransport([httpx.Response(201, json={"id": "task-1"})])
    client, _sleep = build_client(transport)
    service = OrderSyncService(client)

    created = await service.sync(WmsOrder(order_id="A-1", destination="a"))
    assert created.created is True
    assert created.task_id == "task-1"
    assert created.attempts == 1
    await client.aclose()

    replay_transport = ScriptedTransport([httpx.Response(200, json={"id": "task-1"})])
    replay_client, _ = build_client(replay_transport)
    replayed = await OrderSyncService(replay_client).sync(WmsOrder(order_id="A-1", destination="a"))

    assert replayed.created is False
    assert replay_transport.requests[0].headers["Idempotency-Key"] == "wms:A-1"
    await replay_client.aclose()
