from __future__ import annotations

from datetime import datetime, timedelta

from robot_dispatch.config import Settings
from robot_dispatch.db.models import Robot, Task, TaskEvent, utcnow
from robot_dispatch.domain.enums import RobotStatus, TaskEventKind, TaskStatus
from robot_dispatch.domain.policies import RetryPolicy, should_retry
from robot_dispatch.domain.state_machine import ensure_transition
from robot_dispatch.logging_setup import get_logger
from robot_dispatch.messaging.messages import HeartbeatMessage, TaskResultMessage
from robot_dispatch.repositories.protocols import UnitOfWork, UnitOfWorkFactory

logger = get_logger("results")


class ResultService:
    """Applies robot feedback to tasks.

    Every result is checked against the task's current `command_id`. A late
    result from a previous attempt, a duplicate delivery or a message from a
    lost robot must not resurrect a finished task, so stale messages are
    recorded as `result_ignored` events and dropped.
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        settings: Settings,
        *,
        retry_policy: RetryPolicy | None = None,
        clock=utcnow,
    ) -> None:
        self._uow_factory = uow_factory
        self._settings = settings
        self._policy = retry_policy or RetryPolicy(
            base_delay_seconds=settings.retry_base_delay_seconds,
            max_delay_seconds=settings.retry_max_delay_seconds,
            jitter_ratio=settings.retry_jitter_ratio,
        )
        self._clock = clock

    async def handle(self, message: TaskResultMessage) -> str:
        now = self._clock()
        async with self._uow_factory() as uow:
            task = await uow.tasks.get(message.task_id)
            if task is None:
                logger.warning("result for unknown task", task_id=str(message.task_id))
                return "unknown_task"

            current = TaskStatus(task.status)
            if current.is_terminal:
                await self._ignore(uow, task, message, now, "task already finished")
                await uow.commit()
                return "terminal_task"

            if message.command_id is not None and task.command_id != message.command_id:
                await self._ignore(uow, task, message, now, "stale command_id")
                await uow.commit()
                return "stale_command"

            if current not in {TaskStatus.ASSIGNED, TaskStatus.RUNNING}:
                await self._ignore(uow, task, message, now, f"task is {current.value}")
                await uow.commit()
                return "unexpected_status"

            if message.event == "progress":
                await self._apply_progress(uow, task, message, now)
                await uow.commit()
                return "progress"

            robot = await uow.robots.get(task.robot_id) if task.robot_id else None
            self._release_robot(robot, now)

            if message.event == "succeeded":
                task.status = ensure_transition(current, TaskStatus.SUCCEEDED).value
                task.result = message.result or {"detail": message.detail}
                task.last_error = None
                task.lease_expires_at = None
                task.finished_at = now
                task.updated_at = now
                task.version += 1
                await uow.events.add(
                    _event(
                        task,
                        TaskEventKind.SUCCEEDED,
                        from_status=current.value,
                        to_status=task.status,
                        robot_id=task.robot_id,
                        message=message.detail,
                        payload={"attempt": task.attempts},
                    )
                )
            else:
                await self._apply_failure(uow, task, message, now, current)

            await uow.commit()
            return message.event

    async def _apply_progress(
        self, uow: UnitOfWork, task: Task, message: TaskResultMessage, now: datetime
    ) -> None:
        previous = TaskStatus(task.status)
        if previous is TaskStatus.ASSIGNED:
            task.status = ensure_transition(previous, TaskStatus.RUNNING).value
        task.lease_expires_at = now + timedelta(seconds=task.timeout_seconds)
        task.updated_at = now
        task.version += 1
        await uow.events.add(
            _event(
                task,
                TaskEventKind.PROGRESS,
                from_status=previous.value,
                to_status=task.status,
                robot_id=task.robot_id,
                message=message.detail,
                payload={"progress": message.progress, "attempt": task.attempts},
            )
        )

    async def _apply_failure(
        self,
        uow: UnitOfWork,
        task: Task,
        message: TaskResultMessage,
        now: datetime,
        current: TaskStatus,
    ) -> None:
        error = message.error or message.detail or "robot reported failure"
        task.last_error = error

        if should_retry(task.attempts, task.max_attempts):
            delay = self._policy.delay_seconds(task.attempts)
            task.status = ensure_transition(current, TaskStatus.RETRYING).value
            task.available_at = now + timedelta(seconds=delay)
            task.lease_expires_at = None
            task.updated_at = now
            task.version += 1
            await uow.events.add(
                _event(
                    task,
                    TaskEventKind.RETRY_SCHEDULED,
                    from_status=current.value,
                    to_status=task.status,
                    robot_id=task.robot_id,
                    message=f"retry in {delay:.1f}s after: {error}",
                    payload={
                        "attempt": task.attempts,
                        "max_attempts": task.max_attempts,
                        "retry_in_seconds": round(delay, 3),
                    },
                )
            )
            return

        task.status = ensure_transition(current, TaskStatus.FAILED).value
        task.lease_expires_at = None
        task.finished_at = now
        task.updated_at = now
        task.version += 1
        await uow.events.add(
            _event(
                task,
                TaskEventKind.FAILED,
                from_status=current.value,
                to_status=task.status,
                robot_id=task.robot_id,
                message=error,
                payload={"attempts": task.attempts, "max_attempts": task.max_attempts},
            )
        )

    def _release_robot(self, robot: Robot | None, now: datetime) -> None:
        if robot is None:
            return
        robot.status = RobotStatus.IDLE.value
        robot.current_task_id = None
        robot.last_seen_at = now
        robot.updated_at = now

    async def _ignore(
        self,
        uow: UnitOfWork,
        task: Task,
        message: TaskResultMessage,
        now: datetime,
        reason: str,
    ) -> None:
        logger.info("result ignored", task_id=str(task.id), reason=reason, event=message.event)
        await uow.events.add(
            _event(
                task,
                TaskEventKind.RESULT_IGNORED,
                from_status=task.status,
                to_status=task.status,
                robot_id=message.robot_id,
                message=reason,
                payload={
                    "event": message.event,
                    "command_id": str(message.command_id) if message.command_id else None,
                },
            )
        )


class HeartbeatService:
    """Keeps `robots.last_seen_at` fresh and revives robots that came back online."""

    def __init__(self, uow_factory: UnitOfWorkFactory, *, clock=utcnow) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def handle(self, message: HeartbeatMessage) -> str:
        now = self._clock()
        async with self._uow_factory() as uow:
            robot = await uow.robots.get(message.robot_id)
            if robot is None:
                logger.warning("heartbeat from unknown robot", robot_id=str(message.robot_id))
                return "unknown_robot"

            robot.last_seen_at = now
            robot.updated_at = now
            if robot.current_task_id is not None:
                robot.status = RobotStatus.BUSY.value
            elif message.status in {RobotStatus.IDLE.value, RobotStatus.BUSY.value}:
                robot.status = message.status
            else:
                robot.status = RobotStatus.IDLE.value
            await uow.commit()
            return "ok"


def _event(task: Task, kind: TaskEventKind, **kwargs) -> TaskEvent:
    return TaskEvent.new(task_id=task.id, kind=kind.value, **kwargs)
