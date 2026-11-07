from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from robot_dispatch.messaging import broker as broker_module
from robot_dispatch.messaging.broker import Broker, _sanitize_headers
from robot_dispatch.messaging.messages import (
    COMMANDS_EXCHANGE,
    DLQ_QUEUE,
    DLX_EXCHANGE,
    EVENTS_EXCHANGE,
    RESULTS_QUEUE,
    RETRY_QUEUE,
)


class FakeExchange:
    def __init__(self, name: str) -> None:
        self.name = name
        self.published: list[tuple[object, str]] = []

    async def publish(self, message, routing_key: str) -> None:
        self.published.append((message, routing_key))


class FakeQueue:
    def __init__(self, name: str, message_count: int = 0, fail: bool = False) -> None:
        self.name = name
        self.declaration_result = SimpleNamespace(message_count=message_count)
        self.bindings: list[tuple[object, str]] = []
        self.consumed = None
        self._fail = fail

    async def bind(self, exchange, routing_key: str) -> None:
        self.bindings.append((exchange, routing_key))

    async def consume(self, handler, no_ack: bool = False) -> None:
        self.consumed = (handler, no_ack)

    def raise_if_needed(self) -> None:
        if self._fail:
            raise RuntimeError("queue does not exist")


class FakeChannel:
    def __init__(self) -> None:
        self.qos: int | None = None
        self.exchanges: dict[str, FakeExchange] = {}
        self.queues: dict[str, FakeQueue] = {}
        self.default_exchange = FakeExchange("")
        self.fail_declare: set[str] = set()

    async def set_qos(self, prefetch_count: int) -> None:
        self.qos = prefetch_count

    async def declare_exchange(self, name: str, kind, durable: bool = True) -> FakeExchange:
        exchange = FakeExchange(name)
        self.exchanges[name] = exchange
        return exchange

    async def declare_queue(self, name: str, durable: bool = True, **kwargs) -> FakeQueue:
        if name in self.fail_declare:
            raise RuntimeError(f"queue {name} does not exist")
        queue = FakeQueue(name, message_count=7 if name == RESULTS_QUEUE else 0)
        self.queues[name] = queue
        return queue


class FakeConnection:
    def __init__(self) -> None:
        self.is_closed = False
        self._channel = FakeChannel()
        self.closed = False

    async def channel(self, publisher_confirms: bool = True) -> FakeChannel:
        return self._channel

    async def close(self) -> None:
        self.closed = True
        self.is_closed = True


@pytest.fixture
def connection(monkeypatch) -> FakeConnection:
    fake = FakeConnection()

    async def connect_robust(url: str, timeout: int = 30) -> FakeConnection:  # noqa: ASYNC109
        return fake

    monkeypatch.setattr(broker_module.aio_pika, "connect_robust", connect_robust)
    return fake


async def test_connect_declares_topology(connection) -> None:
    broker = Broker("amqp://test", prefetch=5)

    await broker.connect()

    assert broker.connected is True
    channel = connection._channel
    assert channel.qos == 5
    assert set(channel.exchanges) == {COMMANDS_EXCHANGE, EVENTS_EXCHANGE, DLX_EXCHANGE}
    assert set(channel.queues) == {DLQ_QUEUE, RESULTS_QUEUE, RETRY_QUEUE}
    assert broker.results_queue is not None
    assert broker.retry_queue is not None
    assert channel.queues[RESULTS_QUEUE].bindings


async def test_connect_retries_then_fails(monkeypatch) -> None:
    attempts: list[int] = []

    async def connect_robust(url: str, timeout: int = 30):  # noqa: ASYNC109
        attempts.append(1)
        raise OSError("broker is down")

    async def fast_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(broker_module.aio_pika, "connect_robust", connect_robust)
    monkeypatch.setattr(broker_module.asyncio, "sleep", fast_sleep)

    broker = Broker("amqp://test", connect_retries=3, connect_delay=0)

    with pytest.raises(RuntimeError, match="cannot connect to rabbitmq"):
        await broker.connect()

    assert len(attempts) == 3
    assert broker.connected is False


async def test_close_resets_state(connection) -> None:
    broker = Broker("amqp://test")
    await broker.connect()

    await broker.close()

    assert connection.closed is True
    assert broker.connected is False
    assert await broker.queue_depth("any") is None


async def test_ensure_robot_queue_binds_command_routing(connection) -> None:
    broker = Broker("amqp://test")
    await broker.connect()
    robot_id = uuid.uuid4()

    await broker.ensure_robot_queue(robot_id)

    queue = connection._channel.queues[f"cmd.{robot_id}"]
    exchange, routing_key = queue.bindings[0]
    assert routing_key == f"command.{robot_id}"
    assert exchange.name == COMMANDS_EXCHANGE


async def test_publish_requires_known_exchange(connection) -> None:
    broker = Broker("amqp://test")
    await broker.connect()

    with pytest.raises(KeyError, match="unknown exchange"):
        await broker.publish(exchange="nope", routing_key="k", payload={})


async def test_publish_serializes_payload(connection) -> None:
    broker = Broker("amqp://test")
    await broker.connect()
    robot_id = uuid.uuid4()

    await broker.publish(
        exchange=COMMANDS_EXCHANGE,
        routing_key=f"command.{robot_id}",
        payload={"robot_id": robot_id, "n": 1},
        message_id="m-1",
        headers={"robot_id": robot_id, "kind": "command"},
        expiration_ms=1000,
    )

    message, routing_key = connection._channel.exchanges[COMMANDS_EXCHANGE].published[0]
    assert routing_key == f"command.{robot_id}"
    assert json.loads(message.body) == {"robot_id": str(robot_id), "n": 1}
    assert message.message_id == "m-1"
    assert message.headers["robot_id"] == str(robot_id)
    assert message.expiration == 1000


async def test_publish_raw_uses_default_exchange(connection) -> None:
    broker = Broker("amqp://test")
    await broker.connect()

    await broker.publish_raw(queue=RETRY_QUEUE, body=b"{}", headers={"x-retry-count": 2}, expiration_ms=500)

    message, routing_key = connection._channel.default_exchange.published[0]
    assert routing_key == RETRY_QUEUE
    assert message.body == b"{}"
    assert message.headers["x-retry-count"] == 2
    assert message.expiration == 500


async def test_consume_requires_connection() -> None:
    broker = Broker("amqp://test")

    async def handler(_message):  # pragma: no cover - consistency guard
        return None

    with pytest.raises(RuntimeError, match="not connected"):
        await broker.consume(handler)


async def test_consume_subscribes_results_queue(connection) -> None:
    broker = Broker("amqp://test")
    await broker.connect()

    async def handler(_message) -> None:
        return None

    await broker.consume(handler)

    queue = connection._channel.queues[RESULTS_QUEUE]
    assert queue.consumed == (handler, False)


async def test_queue_depth_returns_message_count(connection) -> None:
    broker = Broker("amqp://test")
    await broker.connect()

    assert await broker.queue_depth(RESULTS_QUEUE) == 7


async def test_queue_depth_handles_missing_queue(connection) -> None:
    broker = Broker("amqp://test")
    await broker.connect()
    connection._channel.fail_declare.add("missing")

    assert await broker.queue_depth("missing") is None


def test_sanitize_headers_keeps_primitives() -> None:
    clean = _sanitize_headers({"n": 1, "f": 1.5, "b": True, "s": "x", "raw": b"y", "none": None})

    assert clean == {"n": 1, "f": 1.5, "b": True, "s": "x", "raw": b"y", "none": None}


def test_sanitize_headers_stringifies_objects() -> None:
    identifier = uuid.uuid4()

    clean = _sanitize_headers({"id": identifier, "list": [1, 2]})

    assert clean == {"id": str(identifier), "list": "[1, 2]"}


def test_sanitize_headers_handles_empty() -> None:
    assert _sanitize_headers(None) == {}
    assert _sanitize_headers({}) == {}

