from __future__ import annotations

from datetime import datetime, timedelta

from robot_dispatch.config import Settings
from robot_dispatch.db.models import utcnow
from robot_dispatch.logging_setup import get_logger
from robot_dispatch.messaging.publisher import Publisher
from robot_dispatch.repositories.protocols import UnitOfWorkFactory

logger = get_logger("outbox")


class OutboxRelay:
    """Transactional outbox publisher.

    The dispatcher writes the outgoing command into `outbox_messages` inside the
    same transaction that assigns the task. This relay is the only place that
    talks to RabbitMQ, so a broker outage or a crash never loses a command: the
    row stays pending and is retried until the broker confirms the publish.
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        publisher: Publisher,
        settings: Settings,
        *,
        clock=utcnow,
    ) -> None:
        self._uow_factory = uow_factory
        self._publisher = publisher
        self._settings = settings
        self._clock = clock

    async def relay_once(self) -> int:
        published = 0
        now = self._clock()
        async with self._uow_factory() as uow:
            messages = await uow.outbox.lock_pending(now=now, limit=self._settings.outbox_batch_size)
            for message in messages:
                try:
                    await self._publisher.publish(
                        exchange=message.exchange,
                        routing_key=message.routing_key,
                        payload=message.payload,
                        message_id=message.message_id,
                        headers=message.headers,
                        expiration_ms=message.expiration_ms,
                    )
                except Exception as exc:  # noqa: BLE001 - any publish failure is retried
                    attempts = message.attempts + 1
                    delay = min(2 ** attempts, self._settings.retry_max_delay_seconds)
                    await uow.outbox.mark_failed(
                        message,
                        str(exc),
                        now + timedelta(seconds=delay),
                        attempts,
                    )
                    level = logger.error if attempts >= self._settings.outbox_max_attempts else logger.warning
                    level(
                        "outbox publish failed",
                        message_id=message.message_id,
                        attempts=attempts,
                        retry_in_seconds=delay,
                        error=str(exc),
                    )
                    continue
                await uow.outbox.mark_sent(message, self._clock())
                published += 1
            await uow.commit()
        if published:
            logger.info("outbox relayed", count=published)
        return published


class HeartbeatWatchdog:
    """Marks robots offline when their heartbeats stop."""

    def __init__(self, robot_service, settings: Settings, *, clock=utcnow) -> None:
        self._robots = robot_service
        self._settings = settings
        self._clock = clock

    async def sweep_once(self) -> int:
        threshold: datetime = self._clock() - timedelta(seconds=self._settings.robot_offline_after_seconds)
        return await self._robots.mark_offline(threshold)
