from __future__ import annotations

from datetime import timedelta

from robot_dispatch.db.models import utcnow
from robot_dispatch.domain.enums import RobotStatus, TaskStatus
from robot_dispatch.messaging.messages import HeartbeatMessage, TaskResultMessage
from robot_dispatch.services.dispatcher import DispatcherService
from robot_dispatch.services.results import HeartbeatService, ResultService
from robot_dispatch.services.task_service import CreateTaskCommand, TaskService


async def dispatched_task(uow_factory, settings, clock, robot):
    tasks = TaskService(uow_factory, settings, clock=clock)
    created = await tasks.create(CreateTaskCommand(type="delivery", payload={"a": 1}))
    await DispatcherService(uow_factory, settings, clock=clock).dispatch_once()
    async with uow_factory() as uow:
        task = await uow.tasks.get(created.task.id)
    return task


def result_message(task, event: str, **kwargs) -> TaskResultMessage:
    payload = {
        "event": event,
        "task_id": task.id,
        "robot_id": task.robot_id,
        "command_id": task.command_id,
        "occurred_at": utcnow(),
    }
    payload.update(kwargs)
    return TaskResultMessage(**payload)


async def test_progress_moves_task_to_running_and_extends_lease(
    uow_factory, settings, clock, robot
) -> None:
    task = await dispatched_task(uow_factory, settings, clock, robot)
    clock.advance(10)
    service = ResultService(uow_factory, settings, clock=clock)

    action = await service.handle(result_message(task, "progress", progress=42.0, detail="half"))

    assert action == "progress"
    async with uow_factory() as uow:
        updated = await uow.tasks.get(task.id)
    assert updated.status == TaskStatus.RUNNING.value
    assert updated.lease_expires_at == clock.moment + timedelta(seconds=updated.timeout_seconds)


async def test_success_finishes_task_and_frees_robot(uow_factory, settings, clock, robot) -> None:
    task = await dispatched_task(uow_factory, settings, clock, robot)
    service = ResultService(uow_factory, settings, clock=clock)

    action = await service.handle(result_message(task, "succeeded", result={"delivered": True}))

    assert action == "succeeded"
    async with uow_factory() as uow:
        updated = await uow.tasks.get(task.id)
        stored_robot = await uow.robots.get(robot.id)
    assert updated.status == TaskStatus.SUCCEEDED.value
    assert updated.result == {"delivered": True}
    assert updated.finished_at is not None
    assert stored_robot.status == RobotStatus.IDLE.value
    assert stored_robot.current_task_id is None


async def test_failure_schedules_retry_with_backoff(uow_factory, settings, clock, robot) -> None:
    task = await dispatched_task(uow_factory, settings, clock, robot)
    service = ResultService(uow_factory, settings, clock=clock)

    action = await service.handle(result_message(task, "failed", error="gripper stuck"))

    assert action == "failed"
    async with uow_factory() as uow:
        updated = await uow.tasks.get(task.id)
    assert updated.status == TaskStatus.RETRYING.value
    assert updated.last_error == "gripper stuck"
    assert updated.attempts == 1
    assert updated.available_at == clock.moment + timedelta(seconds=5)


async def test_failure_after_max_attempts_fails_task(uow_factory, settings, clock, robot) -> None:
    tasks = TaskService(uow_factory, settings, clock=clock)
    created = await tasks.create(
        CreateTaskCommand(type="delivery", payload={}, max_attempts=1)
    )
    await DispatcherService(uow_factory, settings, clock=clock).dispatch_once()
    async with uow_factory() as uow:
        task = await uow.tasks.get(created.task.id)

    service = ResultService(uow_factory, settings, clock=clock)
    await service.handle(result_message(task, "failed", error="boom"))

    async with uow_factory() as uow:
        updated = await uow.tasks.get(task.id)
        events = await uow.events.list_for_task(task.id)
    assert updated.status == TaskStatus.FAILED.value
    assert events[-1].kind == "failed"


async def test_stale_command_result_is_ignored(uow_factory, settings, clock, robot) -> None:
    task = await dispatched_task(uow_factory, settings, clock, robot)
    service = ResultService(uow_factory, settings, clock=clock)

    stale = result_message(task, "succeeded")
    stale.command_id = __import__("uuid").uuid4()

    action = await service.handle(stale)

    assert action == "stale_command"
    async with uow_factory() as uow:
        updated = await uow.tasks.get(task.id)
        events = await uow.events.list_for_task(task.id)
    assert updated.status == TaskStatus.ASSIGNED.value
    assert events[-1].kind == "result_ignored"


async def test_duplicate_result_after_finish_is_ignored(uow_factory, settings, clock, robot) -> None:
    task = await dispatched_task(uow_factory, settings, clock, robot)
    service = ResultService(uow_factory, settings, clock=clock)
    await service.handle(result_message(task, "succeeded"))

    action = await service.handle(result_message(task, "failed", error="late duplicate"))

    assert action == "terminal_task"
    async with uow_factory() as uow:
        updated = await uow.tasks.get(task.id)
    assert updated.status == TaskStatus.SUCCEEDED.value
    assert updated.finished_at is not None


async def test_result_for_unknown_task_is_dropped(uow_factory, settings, clock) -> None:
    service = ResultService(uow_factory, settings, clock=clock)
    message = TaskResultMessage(
        event="succeeded",
        task_id=__import__("uuid").uuid4(),
        robot_id=__import__("uuid").uuid4(),
        occurred_at=utcnow(),
    )
    assert await service.handle(message) == "unknown_task"


async def test_heartbeat_refreshes_robot_and_clears_offline(uow_factory, settings, clock, robot) -> None:
    async with uow_factory() as uow:
        stored = await uow.robots.get(robot.id)
        stored.status = RobotStatus.OFFLINE.value
        await uow.commit()

    service = HeartbeatService(uow_factory, clock=clock)
    clock.advance(5)
    action = await service.handle(
        HeartbeatMessage(robot_id=robot.id, status="idle", occurred_at=clock.moment)
    )

    assert action == "ok"
    async with uow_factory() as uow:
        updated = await uow.robots.get(robot.id)
    assert updated.status == RobotStatus.IDLE.value
    assert updated.last_seen_at == clock.moment


async def test_heartbeat_from_unknown_robot(uow_factory, clock) -> None:
    service = HeartbeatService(uow_factory, clock=clock)
    action = await service.handle(
        HeartbeatMessage(robot_id=__import__("uuid").uuid4(), occurred_at=clock.moment)
    )
    assert action == "unknown_robot"
