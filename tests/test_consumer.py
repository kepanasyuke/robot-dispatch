from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from robot_dispatch.db.models import utcnow
from robot_dispatch.domain.enums import TaskStatus
from robot_dispatch.messaging.consumer import RobotEventConsumer
from robot_dispatch.messaging.messages import RETRY_QUEUE, TaskResultMessage
from robot_dispatch.services.dispatcher import DispatcherService
from robot_dispatch.services.results import HeartbeatService, ResultService
from robot_dispatch.services.task_service import CreateTaskCommand, TaskService


class FakeMessage:
    def __init__(self, body: dict[str, Any] | bytes, headers: dict[str, Any] | None = None) -> None:
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.headers = headers or {}
        self.message_id = "m-1"
        self.acked = False
        self.rejected = False
        self.requeued: bool | None = None

    async def ack(self) -> None:
        self.acked = True

    async def reject(self, requeue: bool = True) -> None:
        self.rejected = True
        self.requeued = requeue


class FakeBroker:
    def __init__(self) -> None:
        self.raw: list[dict[str, Any]] = []
        self.fail_publish = False

    async def publish_raw(self, *, queue, body, headers=None, expiration_ms=None, message_id=None):
        if self.fail_publish:
            raise RuntimeError("broker is down")
        self.raw.append(
            {
                "queue": queue,
                "body": body,
                "headers": headers or {},
                "expiration_ms": expiration_ms,
                "message_id": message_id,
            }
        )


@pytest.fixture
def consumer(uow_factory, settings):
    broker = FakeBroker()
    results = ResultService(uow_factory, settings)
    heartbeats = HeartbeatService(uow_factory)
    return RobotEventConsumer(broker, results, heartbeats, settings), broker


async def prepare_task(uow_factory, settings, clock, robot):
    tasks = TaskService(uow_factory, settings, clock=clock)
    created = await tasks.create(CreateTaskCommand(type="delivery", payload={}))
    await DispatcherService(uow_factory, settings, clock=clock).dispatch_once()
    async with uow_factory() as uow:
        return await uow.tasks.get(created.task.id)


def result_payload(task, event: str = "succeeded", **kwargs) -> dict[str, Any]:
    payload = {
        "kind": "result",
        "event": event,
        "task_id": str(task.id),
        "robot_id": str(task.robot_id),
        "command_id": str(task.command_id),
        "occurred_at": datetime.now(tz=UTC).isoformat(),
    }
    payload.update(kwargs)
    return payload


async def test_valid_result_is_acked_and_applied(uow_factory, settings, clock, robot, consumer) -> None:
    task = await prepare_task(uow_factory, settings, clock, robot)
    handler, _broker = consumer
    message = FakeMessage(result_payload(task, result={"ok": True}))

    await handler.on_message(message)

    assert message.acked is True
    assert message.rejected is False
    async with uow_factory() as uow:
        stored = await uow.tasks.get(task.id)
    assert stored.status == TaskStatus.SUCCEEDED.value


async def test_heartbeat_is_acked(uow_factory, settings, clock, robot, consumer) -> None:
    handler, _broker = consumer
    message = FakeMessage(
        {
            "kind": "heartbeat",
            "robot_id": str(robot.id),
            "status": "idle",
            "occurred_at": utcnow().isoformat(),
        }
    )

    await handler.on_message(message)

    assert message.acked is True


async def test_malformed_payload_is_dead_lettered(uow_factory, settings, robot, consumer) -> None:
    handler, broker = consumer
    message = FakeMessage(b"{not json")

    await handler.on_message(message)

    assert message.rejected is True
    assert message.requeued is False
    assert broker.raw == []


async def test_invalid_schema_is_dead_lettered(uow_factory, settings, consumer) -> None:
    handler, _broker = consumer
    message = FakeMessage({"kind": "result", "event": "succeeded"})

    await handler.on_message(message)

    assert message.rejected is True
    assert message.requeued is False


async def test_handler_failure_schedules_delayed_retry(
    uow_factory, settings, clock, robot, consumer, monkeypatch
) -> None:
    task = await prepare_task(uow_factory, settings, clock, robot)
    handler, broker = consumer

    async def boom(_message: TaskResultMessage) -> str:
        raise RuntimeError("database hiccup")

    monkeypatch.setattr(handler._results, "handle", boom)
    message = FakeMessage(result_payload(task))

    await handler.on_message(message)

    assert message.acked is True
    assert message.rejected is False
    assert len(broker.raw) == 1
    retry = broker.raw[0]
    assert retry["queue"] == RETRY_QUEUE
    assert retry["headers"]["x-retry-count"] == 1
    assert "database hiccup" in retry["headers"]["x-last-error"]
    assert retry["expiration_ms"] == settings.result_retry_delay_ms


async def test_retry_limit_dead_letters_message(
    uow_factory, settings, clock, robot, consumer, monkeypatch
) -> None:
    task = await prepare_task(uow_factory, settings, clock, robot)
    handler, _broker = consumer

    async def boom(_message: TaskResultMessage) -> str:
        raise RuntimeError("still broken")

    monkeypatch.setattr(handler._results, "handle", boom)
    message = FakeMessage(
        result_payload(task), headers={"x-retry-count": settings.result_retry_max}
    )

    await handler.on_message(message)

    assert message.rejected is True
    assert message.requeued is False
