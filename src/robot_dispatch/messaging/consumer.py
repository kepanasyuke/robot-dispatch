from __future__ import annotations

import json
from typing import Any

from aio_pika.abc import AbstractIncomingMessage
from pydantic import ValidationError

from robot_dispatch.config import Settings
from robot_dispatch.logging_setup import get_logger
from robot_dispatch.messaging.broker import Broker
from robot_dispatch.messaging.messages import RETRY_QUEUE, HeartbeatMessage, TaskResultMessage
from robot_dispatch.services.results import HeartbeatService, ResultService

logger = get_logger("consumer")


class RobotEventConsumer:
    """Consumes robot results and heartbeats with bounded redelivery.

    A handler error is retried up to `result_retry_max` times with a per-message
    TTL in `dispatch.results.retry`, then dead-lettered to `dispatch.results.dlq`.
    Malformed payloads are dead-lettered immediately: replaying them cannot help.
    """

    def __init__(
        self,
        broker: Broker,
        results: ResultService,
        heartbeats: HeartbeatService,
        settings: Settings,
    ) -> None:
        self._broker = broker
        self._results = results
        self._heartbeats = heartbeats
        self._settings = settings

    async def start(self) -> None:
        await self._broker.consume(self.on_message)
        logger.info("consumer started")

    async def on_message(self, message: AbstractIncomingMessage) -> None:
        headers: dict[str, Any] = dict(message.headers or {})
        try:
            payload = json.loads(message.body)
            kind = payload.get("kind")
            if kind == "heartbeat":
                await self._heartbeats.handle(HeartbeatMessage.model_validate(payload))
            else:
                await self._results.handle(TaskResultMessage.model_validate(payload))
        except (json.JSONDecodeError, ValidationError, KeyError) as exc:
            logger.error("malformed robot event, dead-lettering", error=str(exc))
            await message.reject(requeue=False)
            return
        except Exception as exc:  # noqa: BLE001 - infrastructure failure, retry
            await self._schedule_retry(message, headers, exc)
            return
        await message.ack()

    async def _schedule_retry(
        self, message: AbstractIncomingMessage, headers: dict[str, Any], error: Exception
    ) -> None:
        attempt = int(headers.get("x-retry-count", 0)) + 1
        if attempt > self._settings.result_retry_max:
            logger.error(
                "robot event dropped after retries",
                attempts=attempt,
                error=str(error),
                message_id=message.message_id,
            )
            await message.reject(requeue=False)
            return

        delay_ms = self._settings.result_retry_delay_ms * attempt
        try:
            await self._broker.publish_raw(
                queue=RETRY_QUEUE,
                body=message.body,
                headers={
                    **headers,
                    "x-retry-count": attempt,
                    "x-last-error": str(error)[:500],
                },
                expiration_ms=delay_ms,
                message_id=message.message_id,
            )
        except Exception as publish_error:  # noqa: BLE001 - broker may be down
            logger.error("cannot schedule retry, requeueing", error=str(publish_error))
            await message.reject(requeue=True)
            return

        await message.ack()
        logger.warning("robot event requeued", attempt=attempt, retry_in_ms=delay_ms, error=str(error))
