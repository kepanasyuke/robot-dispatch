from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import (
    AbstractChannel,
    AbstractExchange,
    AbstractIncomingMessage,
    AbstractQueue,
    AbstractRobustConnection,
)

from robot_dispatch.logging_setup import get_logger
from robot_dispatch.messaging.messages import (
    COMMANDS_EXCHANGE,
    DLQ_QUEUE,
    DLX_EXCHANGE,
    EVENTS_EXCHANGE,
    RESULTS_QUEUE,
    RETRY_QUEUE,
    command_queue_name,
    command_routing_key,
)

logger = get_logger("broker")

MessageHandler = Callable[[AbstractIncomingMessage], Awaitable[None]]


class Broker:
    """RabbitMQ topology for the dispatch service.

    robot.commands (direct)  --command.<robot_id>-->  cmd.<robot_id>   (one queue per robot)
    robot.events  (topic)    --result.#/heartbeat.#--> dispatch.results
    dispatch.results         --reject without requeue--> dispatch.dlx --> dispatch.results.dlq
    dispatch.results.retry   --per-message TTL--> robot.events/result.retried --> dispatch.results
    """

    def __init__(
        self,
        url: str,
        *,
        prefetch: int = 20,
        connect_retries: int = 10,
        connect_delay: float = 2.0,
    ) -> None:
        self._url = url
        self._prefetch = prefetch
        self._connect_retries = connect_retries
        self._connect_delay = connect_delay
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None
        self._exchanges: dict[str, AbstractExchange] = {}
        self.results_queue: AbstractQueue | None = None
        self.retry_queue: AbstractQueue | None = None

    @property
    def connected(self) -> bool:
        return self._connection is not None and not self._connection.is_closed

    async def connect(self) -> None:
        last_error: Exception | None = None
        for attempt in range(1, self._connect_retries + 1):
            try:
                self._connection = await aio_pika.connect_robust(self._url, timeout=30)
                self._channel = await self._connection.channel(publisher_confirms=True)
                await self._channel.set_qos(prefetch_count=self._prefetch)
                await self._declare_topology()
                logger.info("connected to rabbitmq", attempt=attempt)
                return
            except Exception as exc:  # noqa: BLE001 - broker may not be up yet
                last_error = exc
                logger.warning("rabbitmq connection failed, retrying", attempt=attempt, error=str(exc))
                await asyncio.sleep(self._connect_delay)
        raise RuntimeError(f"cannot connect to rabbitmq: {last_error}")

    async def close(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._connection = None
        self._channel = None
        self._exchanges.clear()

    async def _declare_topology(self) -> None:
        assert self._channel is not None
        channel = self._channel

        commands = await channel.declare_exchange(COMMANDS_EXCHANGE, ExchangeType.DIRECT, durable=True)
        events = await channel.declare_exchange(EVENTS_EXCHANGE, ExchangeType.TOPIC, durable=True)
        dlx = await channel.declare_exchange(DLX_EXCHANGE, ExchangeType.DIRECT, durable=True)
        self._exchanges = {COMMANDS_EXCHANGE: commands, EVENTS_EXCHANGE: events, DLX_EXCHANGE: dlx}

        dlq = await channel.declare_queue(DLQ_QUEUE, durable=True)
        await dlq.bind(dlx, routing_key="dead")

        results = await channel.declare_queue(
            RESULTS_QUEUE,
            durable=True,
            arguments={"x-dead-letter-exchange": DLX_EXCHANGE, "x-dead-letter-routing-key": "dead"},
        )
        await results.bind(events, routing_key="result.#")
        await results.bind(events, routing_key="heartbeat.#")
        self.results_queue = results

        retry = await channel.declare_queue(
            RETRY_QUEUE,
            durable=True,
            arguments={
                "x-dead-letter-exchange": EVENTS_EXCHANGE,
                "x-dead-letter-routing-key": "result.retried",
            },
        )
        await retry.bind(events, routing_key="result.retry")
        self.retry_queue = retry

    async def ensure_robot_queue(self, robot_id: Any) -> None:
        """Idempotently create the per-robot command queue."""
        assert self._channel is not None
        queue = await self._channel.declare_queue(
            command_queue_name(robot_id),
            durable=True,
            arguments={"x-dead-letter-exchange": DLX_EXCHANGE, "x-dead-letter-routing-key": "dead"},
        )
        exchange = self._exchanges[COMMANDS_EXCHANGE]
        await queue.bind(exchange, routing_key=command_routing_key(robot_id))

    async def publish(
        self,
        *,
        exchange: str,
        routing_key: str,
        payload: dict[str, Any],
        message_id: str | None = None,
        headers: dict[str, Any] | None = None,
        expiration_ms: int | None = None,
    ) -> None:
        target = self._exchanges.get(exchange)
        if target is None:
            raise KeyError(f"unknown exchange {exchange}")
        message = Message(
            body=json.dumps(payload, default=str).encode(),
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=message_id,
            headers=_sanitize_headers(headers),
            expiration=str(expiration_ms) if expiration_ms else None,
            timestamp=datetime.now(tz=UTC),
        )
        await target.publish(message, routing_key=routing_key)

    async def publish_raw(
        self,
        *,
        queue: str,
        body: bytes,
        headers: dict[str, Any] | None = None,
        expiration_ms: int | None = None,
        message_id: str | None = None,
    ) -> None:
        """Publish straight to a queue through the default exchange (used for delayed retries)."""
        assert self._channel is not None
        message = Message(
            body=body,
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=message_id,
            headers=_sanitize_headers(headers),
            expiration=str(expiration_ms) if expiration_ms else None,
            timestamp=datetime.now(tz=UTC),
        )
        await self._channel.default_exchange.publish(message, routing_key=queue)

    async def consume(self, handler: MessageHandler) -> None:
        if self.results_queue is None:
            raise RuntimeError("broker is not connected")
        await self.results_queue.consume(handler, no_ack=False)

    async def queue_depth(self, name: str) -> int | None:
        if self._channel is None:
            return None
        try:
            queue = await self._channel.declare_queue(name, durable=True, passive=True)
        except Exception:  # noqa: BLE001 - queue may not exist yet
            return None
        declaration = queue.declaration_result
        return int(getattr(declaration, "message_count", 0) or 0)


def _sanitize_headers(headers: dict[str, Any] | None) -> dict[str, Any]:
    """AMQP headers must be primitives; UUIDs and enums are stringified."""
    if not headers:
        return {}
    clean: dict[str, Any] = {}
    for key, value in headers.items():
        if isinstance(value, (str, int, float, bool, bytes)) or value is None:
            clean[key] = value
        else:
            clean[key] = str(value)
    return clean
