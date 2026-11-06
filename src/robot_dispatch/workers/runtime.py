from __future__ import annotations

import asyncio
import signal
import sys
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine

from robot_dispatch.config import Settings
from robot_dispatch.db.session import create_engine, create_session_factory
from robot_dispatch.db.uow import make_sql_uow_factory
from robot_dispatch.logging_setup import configure_logging, get_logger
from robot_dispatch.messaging.broker import Broker

logger = get_logger("worker")


@dataclass
class Runtime:
    settings: Settings
    engine: AsyncEngine
    uow_factory: Callable
    broker: Broker


@asynccontextmanager
async def runtime(settings: Settings):
    configure_logging(settings.log_level, settings.log_json)
    engine = create_engine(settings.database_url)
    uow_factory = make_sql_uow_factory(create_session_factory(engine))
    broker = Broker(
        settings.rabbitmq_url,
        prefetch=settings.consumer_prefetch,
        connect_retries=settings.rabbitmq_connect_retries,
        connect_delay=settings.rabbitmq_connect_delay_seconds,
    )
    await broker.connect()

    try:
        async with uow_factory() as uow:
            robots = await uow.robots.list()
        for robot in robots:
            await broker.ensure_robot_queue(robot.id)
        logger.info("robot queues ensured", count=len(robots))
    except Exception as exc:  # noqa: BLE001 - schema may not be migrated yet
        logger.warning("cannot pre-declare robot queues", error=str(exc))

    try:
        yield Runtime(settings=settings, engine=engine, uow_factory=uow_factory, broker=broker)
    finally:
        await broker.close()
        await engine.dispose()


def install_signal_handlers(stop: asyncio.Event) -> None:
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
    except (NotImplementedError, RuntimeError, AttributeError):
        # Windows event loop has no add_signal_handler; KeyboardInterrupt ends the run.
        pass


async def periodic(
    name: str,
    step: Callable[[], Awaitable[object]],
    interval_ms: int,
    stop: asyncio.Event,
) -> None:
    """Run `step` forever, swallowing per-iteration failures with a log entry."""
    logger.info("loop started", loop=name, interval_ms=interval_ms)
    while not stop.is_set():
        try:
            await step()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a loop must survive a single bad iteration
            logger.exception("loop iteration failed", loop=name)
        try:
            await asyncio.wait_for(stop.wait(), timeout=max(interval_ms, 1) / 1000)
        except TimeoutError:
            continue
    logger.info("loop stopped", loop=name)


def run(main_coro_factory: Callable[[], Awaitable[None]]) -> None:
    try:
        asyncio.run(main_coro_factory())
    except KeyboardInterrupt:  # pragma: no cover - interactive shutdown
        sys.exit(0)
