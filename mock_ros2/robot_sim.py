"""Mock ROS2 robot fleet.

This process stands in for the real ROS2 stack: it registers robots over the
public REST API, consumes `cmd.<robot_id>` queues, reports progress/success and
sends heartbeats back through the `robot.events` exchange.

Run it to exercise the whole system without a robot:

    python -m mock_ros2.robot_sim --count 2 --work-seconds 6
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import random
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

import aio_pika
import httpx
from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractIncomingMessage

EVENTS_EXCHANGE = "robot.events"


def now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


async def publish(client_channel, exchange, routing_key: str, payload: dict[str, Any]) -> None:
    await exchange.publish(
        Message(
            body=json.dumps(payload).encode(),
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=uuid.uuid4().hex,
        ),
        routing_key=routing_key,
    )


class SimulatedRobot:
    def __init__(
        self,
        *,
        name: str,
        namespace: str,
        capabilities: list[str],
        api_url: str,
        amqp_url: str,
        work_seconds: float,
        failure_rate: float,
        heartbeat_interval: float,
        seed: int | None = None,
    ) -> None:
        self.name = name
        self.namespace = namespace
        self.capabilities = capabilities
        self.api_url = api_url.rstrip("/")
        self.amqp_url = amqp_url
        self.work_seconds = work_seconds
        self.failure_rate = failure_rate
        self.heartbeat_interval = heartbeat_interval
        self.rng = random.Random(seed if seed is not None else name)

        self.robot_id: str | None = None
        self.executed_commands: set[str] = set()
        self.busy = False
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None
        self._events_exchange: AbstractExchange | None = None

    async def register(self) -> None:
        async with httpx.AsyncClient(timeout=10) as http:
            response = await http.post(
                f"{self.api_url}/api/v1/robots",
                json={
                    "name": self.name,
                    "namespace": self.namespace,
                    "capabilities": self.capabilities,
                },
            )
            response.raise_for_status()
            self.robot_id = response.json()["id"]
        print(f"[{self.name}] registered as {self.robot_id}", flush=True)

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(self.amqp_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=1)
        self._events_exchange = await self._channel.declare_exchange(
            EVENTS_EXCHANGE, ExchangeType.TOPIC, durable=True
        )

    async def start(self) -> None:
        assert self._channel is not None and self.robot_id is not None
        queue = await self._channel.declare_queue(f"cmd.{self.robot_id}", durable=True)
        await queue.consume(self.on_command)
        await self._heartbeat_loop()

    async def _heartbeat_loop(self) -> None:
        while True:
            await publish(
                self._channel,
                self._events_exchange,
                f"heartbeat.{self.robot_id}",
                {
                    "kind": "heartbeat",
                    "robot_id": self.robot_id,
                    "namespace": self.namespace,
                    "status": "busy" if self.busy else "idle",
                    "battery": round(self.rng.uniform(35, 100), 1),
                    "occurred_at": now_iso(),
                },
            )
            await asyncio.sleep(self.heartbeat_interval)

    async def on_command(self, message: AbstractIncomingMessage) -> None:
        async with message.process(requeue=True):
            command = json.loads(message.body)
            command_id = command["command_id"]

            if command_id in self.executed_commands:
                print(f"[{self.name}] duplicate command {command_id} ignored", flush=True)
                return
            self.executed_commands.add(command_id)
            self.busy = True
            task_id = command["task_id"]
            print(
                f"[{self.name}] task {task_id} type={command['task_type']} "
                f"attempt={command['attempt']} payload={command['payload']}",
                flush=True,
            )

            try:
                for step in (25, 50, 75):
                    await asyncio.sleep(self.work_seconds / 4)
                    await self._report(
                        task_id,
                        command_id,
                        "progress",
                        progress=float(step),
                        detail=f"{step}% done",
                    )

                await asyncio.sleep(self.work_seconds / 4)
                if self.rng.random() < self.failure_rate:
                    await self._report(
                        task_id,
                        command_id,
                        "failed",
                        error="simulated hardware fault: payload slipped",
                    )
                    print(f"[{self.name}] task {task_id} FAILED (simulated)", flush=True)
                else:
                    await self._report(
                        task_id,
                        command_id,
                        "succeeded",
                        result={
                            "delivered": True,
                            "robot": self.name,
                            "duration_seconds": self.work_seconds,
                        },
                    )
                    print(f"[{self.name}] task {task_id} SUCCEEDED", flush=True)
            finally:
                self.busy = False

    async def _report(
        self,
        task_id: str,
        command_id: str,
        event: str,
        *,
        progress: float | None = None,
        detail: str | None = None,
        error: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "kind": "result",
            "event": event,
            "task_id": task_id,
            "robot_id": self.robot_id,
            "command_id": command_id,
            "occurred_at": now_iso(),
        }
        if progress is not None:
            payload["progress"] = progress
        if detail is not None:
            payload["detail"] = detail
        if error is not None:
            payload["error"] = error
        if result is not None:
            payload["result"] = result
        await publish(self._channel, self._events_exchange, f"result.{self.robot_id}", payload)

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()


async def run_fleet(args: argparse.Namespace) -> None:
    robots = [
        SimulatedRobot(
            name=f"{args.name_prefix}-{index + 1}",
            namespace=f"/{args.name_prefix}{index + 1}",
            capabilities=args.capabilities,
            api_url=args.api_url,
            amqp_url=args.amqp_url,
            work_seconds=args.work_seconds,
            failure_rate=args.failure_rate,
            heartbeat_interval=args.heartbeat_interval,
        )
        for index in range(args.count)
    ]

    for robot in robots:
        await robot.register()
    for robot in robots:
        await robot.connect()

    try:
        await asyncio.gather(*(robot.start() for robot in robots))
    finally:
        for robot in robots:
            await robot.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mock ROS2 robot fleet for the dispatch service")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--amqp-url", default="amqp://dispatch:dispatch@localhost:5672/")
    parser.add_argument("--name-prefix", default="robot")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--capabilities", nargs="+", default=["delivery"])
    parser.add_argument("--work-seconds", type=float, default=6.0)
    parser.add_argument("--failure-rate", type=float, default=0.0)
    parser.add_argument("--heartbeat-interval", type=float, default=5.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run_fleet(args))
    sys.exit(0)


if __name__ == "__main__":
    main()
