from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from wms_integration.webhooks import (
    WebhookVerifier,
    compute_signature,
    create_app,
)

BASE_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
SECRET = "whsec_test"


class FakeClock:
    def __init__(self, moment: datetime = BASE_TIME) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, seconds: float) -> datetime:
        self.moment += timedelta(seconds=seconds)
        return self.moment


class Handler:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def __call__(self, payload: dict) -> None:
        self.calls.append(payload)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def handler() -> Handler:
    return Handler()


@pytest.fixture
async def client(clock, handler):
    app = create_app(WebhookVerifier(secret=SECRET, clock=clock), handler)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://wms.test") as http:
        yield http


def signed_headers(clock: FakeClock, body: bytes, *, secret: str = SECRET) -> dict[str, str]:
    timestamp = str(int(clock.moment.timestamp()))
    return {
        "X-WMS-Timestamp": timestamp,
        "X-WMS-Signature": compute_signature(secret, timestamp, body),
        "Content-Type": "application/json",
    }


ORDER = {"order_id": "A-100", "destination": "warehouse-a", "items": 2}


async def test_valid_webhook_is_accepted_once(client, clock, handler) -> None:
    body = json.dumps(ORDER).encode()

    response = await client.post("/webhooks/wms/order", content=body, headers=signed_headers(clock, body))

    assert response.status_code == 202
    assert response.json() == {"accepted": True}
    assert handler.calls == [ORDER]


async def test_wrong_secret_is_rejected(client, clock, handler) -> None:
    body = json.dumps(ORDER).encode()
    headers = signed_headers(clock, body, secret="other-secret")

    response = await client.post("/webhooks/wms/order", content=body, headers=headers)

    assert response.status_code == 401
    assert handler.calls == []


async def test_tampered_body_is_rejected(client, clock) -> None:
    body = json.dumps(ORDER).encode()
    headers = signed_headers(clock, body)
    tampered = json.dumps({**ORDER, "items": 99}).encode()

    response = await client.post("/webhooks/wms/order", content=tampered, headers=headers)

    assert response.status_code == 401


async def test_stale_timestamp_is_rejected(client, clock) -> None:
    body = json.dumps(ORDER).encode()
    headers = signed_headers(clock, body)
    clock.advance(3600)

    response = await client.post("/webhooks/wms/order", content=body, headers=headers)

    assert response.status_code == 401
    assert "tolerance" in response.json()["detail"]


async def test_future_timestamp_is_rejected(client, clock) -> None:
    future = FakeClock(clock.moment + timedelta(minutes=30))
    body = json.dumps(ORDER).encode()
    headers = signed_headers(future, body)

    response = await client.post("/webhooks/wms/order", content=body, headers=headers)

    assert response.status_code == 401


async def test_replay_is_rejected(client, clock, handler) -> None:
    body = json.dumps(ORDER).encode()
    headers = signed_headers(clock, body)

    first = await client.post("/webhooks/wms/order", content=body, headers=headers)
    second = await client.post("/webhooks/wms/order", content=body, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 409
    assert len(handler.calls) == 1


async def test_missing_headers_are_rejected(client) -> None:
    response = await client.post("/webhooks/wms/order", json=ORDER)

    assert response.status_code == 401


async def test_malformed_json_with_valid_signature_is_bad_request(client, clock) -> None:
    body = b"{not json"
    headers = signed_headers(clock, body)

    response = await client.post("/webhooks/wms/order", content=body, headers=headers)

    assert response.status_code == 400


async def test_health(client) -> None:
    response = await client.get("/health")
    assert response.json() == {"status": "ok"}
