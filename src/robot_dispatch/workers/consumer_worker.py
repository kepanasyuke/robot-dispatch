from __future__ import annotations

import asyncio

from robot_dispatch.config import Settings, get_settings
from robot_dispatch.logging_setup import get_logger
from robot_dispatch.messaging.consumer import RobotEventConsumer
from robot_dispatch.services.results import HeartbeatService, ResultService
from robot_dispatch.workers.runtime import install_signal_handlers, run, runtime

logger = get_logger("consumer-worker")


async def main() -> None:
    settings: Settings = get_settings()
    async with runtime(settings) as rt:
        results = ResultService(rt.uow_factory, settings)
        heartbeats = HeartbeatService(rt.uow_factory)
        consumer = RobotEventConsumer(rt.broker, results, heartbeats, settings)

        stop = asyncio.Event()
        install_signal_handlers(stop)

        await consumer.start()
        logger.info("consumer worker ready")
        try:
            await stop.wait()
        finally:
            await rt.broker.close()
            logger.info("consumer worker stopped")


def cli() -> None:
    run(main)


if __name__ == "__main__":
    cli()
