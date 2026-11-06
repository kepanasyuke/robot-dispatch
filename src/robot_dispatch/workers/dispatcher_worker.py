from __future__ import annotations

import asyncio

from robot_dispatch.config import Settings, get_settings
from robot_dispatch.infra.redis_lock import NullLock, RedisLock
from robot_dispatch.logging_setup import get_logger
from robot_dispatch.messaging.outbox_relay import HeartbeatWatchdog, OutboxRelay
from robot_dispatch.services.dispatcher import DispatcherService, LeaseReaper
from robot_dispatch.services.task_service import RobotService
from robot_dispatch.workers.runtime import (
    install_signal_handlers,
    periodic,
    run,
    runtime,
)

logger = get_logger("dispatcher-worker")


class LeadershipGate:
    """Keeps the dispatcher single-writer when several replicas run."""

    def __init__(self, lock: RedisLock | NullLock, ttl_ms: int = 10_000) -> None:
        self._lock = lock
        self._ttl_ms = ttl_ms
        self._holding = False

    @property
    def is_leader(self) -> bool:
        return self._holding or not self._lock.available

    async def maintain(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            if self._holding:
                self._holding = await self._lock.extend()
            else:
                self._holding = await self._lock.acquire()
            if self._holding:
                logger.debug("leadership renewed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._ttl_ms / 3000)
            except TimeoutError:
                continue
        if self._holding:
            await self._lock.release()


async def main() -> None:
    settings: Settings = get_settings()
    async with runtime(settings) as rt:
        dispatcher = DispatcherService(rt.uow_factory, settings)
        relay = OutboxRelay(rt.uow_factory, rt.broker, settings)
        reaper = LeaseReaper(rt.uow_factory, settings)
        watchdog = HeartbeatWatchdog(RobotService(rt.uow_factory), settings)

        lock: RedisLock | NullLock = RedisLock(settings.redis_url, ttl_ms=10_000)
        if settings.redis_url:
            await lock.connect()
        else:
            lock = NullLock()
        gate = LeadershipGate(lock)

        stop = asyncio.Event()
        install_signal_handlers(stop)

        async def dispatch_step() -> None:
            if not gate.is_leader:
                return
            for _ in range(50):
                outcome = await dispatcher.dispatch_once()
                if not outcome.dispatched:
                    break

        try:
            await asyncio.gather(
                periodic("dispatch", dispatch_step, settings.dispatcher_poll_interval_ms, stop),
                periodic("outbox", relay.relay_once, settings.outbox_poll_interval_ms, stop),
                periodic("reaper", reaper.reap_once, settings.reaper_interval_ms, stop),
                periodic(
                    "watchdog",
                    watchdog.sweep_once,
                    settings.robot_offline_after_seconds * 1000,
                    stop,
                ),
                gate.maintain(stop),
            )
        finally:
            await lock.close()


def cli() -> None:
    run(main)


if __name__ == "__main__":
    cli()
