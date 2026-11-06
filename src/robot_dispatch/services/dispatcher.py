from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from robot_dispatch.config import Settings
from robot_dispatch.db.models import Robot, Task, utcnow
from robot_dispatch.domain.enums import RobotStatus, TaskEventKind, TaskStatus
from robot_dispatch.domain.policies import RetryPolicy, should_retry
from robot_dispatch.domain.state_machine import ensure_transition
from robot_dispatch.logging_setup import get_logger
from robot_dispatch.messaging.messages import (
    COMMANDS_EXCHANGE,
    CommandMessage,
    command_routing_key,
)
from robot_dispatch.repositories.protocols import UnitOfWork, UnitOfWorkFactory

logger = get_logger("dispatcher")


@dataclass(frozen=True)
class DispatchOutcome:
    dispatched: bool
    reason: str
    task_id: uuid.UUID | None = None
    robot_id: uuid.UUID | None = None
    attempt: int | None = None


class DispatcherService:
    """Assigns queued tasks to idle robots.

    Reliability rules:
    * candidates are locked with `FOR UPDATE SKIP LOCKED`, so N replicas never
      grab the same task;
    * the assignment, the robot state change and the outgoing command (outbox)
      are committed in one transaction: a crash cannot leave a task assigned to
      a robot that never receives a command;
    * every attempt gets a fresh `command_id` and a lease, so a silent robot is
      detected by the reaper instead of stalling the task forever.
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        settings: Settings,
        *,
        clock=utcnow,
    ) -> None:
        self._uow_factory = uow_factory
        self._settings = settings
        self._clock = clock

    async def dispatch_once(self) -> DispatchOutcome:
        now = self._clock()
        async with self._uow_factory() as uow:
            candidates = await uow.tasks.lock_ready(now=now, limit=self._settings.dispatcher_batch_size)
            if not candidates:
                return DispatchOutcome(dispatched=False, reason="no_ready_tasks")

            for task in candidates:
                robot = await uow.robots.find_idle_for(
                    task_type=task.type,
                    now=now,
                    offline_after=self._settings.robot_offline_after_seconds,
                )
                if robot is None:
                    continue
                outcome = await self._assign(uow, task, robot, now)
                await uow.commit()
                logger.info(
                    "task dispatched",
                    task_id=str(task.id),
                    robot=robot.name,
                    attempt=task.attempts,
                )
                return outcome

            return DispatchOutcome(dispatched=False, reason="no_idle_robot")

    async def _assign(
        self, uow: UnitOfWork, task: Task, robot: Robot, now: datetime
    ) -> DispatchOutcome:
        previous = TaskStatus(task.status)
        attempt = task.attempts + 1
        command = CommandMessage(
            command_id=uuid.uuid4(),
            task_id=task.id,
            task_type=task.type,
            robot_id=robot.id,
            namespace=robot.namespace,
            attempt=attempt,
            timeout_seconds=task.timeout_seconds,
            payload=task.payload or {},
            issued_at=now,
        )

        task.status = ensure_transition(previous, TaskStatus.ASSIGNED).value
        task.attempts = attempt
        task.robot_id = robot.id
        task.command_id = command.command_id
        task.lease_expires_at = now + timedelta(seconds=task.timeout_seconds)
        task.available_at = now
        task.started_at = task.started_at or now
        task.updated_at = now
        task.version += 1

        robot.status = RobotStatus.BUSY.value
        robot.current_task_id = task.id
        robot.updated_at = now

        await uow.events.add(
            _event(
                task,
                TaskEventKind.DISPATCHED,
                from_status=previous.value,
                to_status=task.status,
                robot_id=robot.id,
                message=f"assigned to {robot.name}, attempt {attempt}/{task.max_attempts}",
                payload={"command_id": str(command.command_id), "attempt": attempt},
            )
        )
        await uow.outbox.add(
            _command_outbox_message(command, timeout_seconds=task.timeout_seconds)
        )
        return DispatchOutcome(
            dispatched=True,
            reason="assigned",
            task_id=task.id,
            robot_id=robot.id,
            attempt=attempt,
        )


class LeaseReaper:
    """Owns every "robot went silent" case.

    A task whose lease expired is re-queued with exponential backoff until
    `max_attempts`, then failed. The robot is always released, so a dead robot
    never blocks a capability slot.
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

    async def reap_once(self, *, limit: int = 100) -> int:
        now = self._clock()
        async with self._uow_factory() as uow:
            expired = await uow.tasks.lock_expired_leases(now=now, limit=limit)
            for task in expired:
                await self._recover(uow, task, now)
            await uow.commit()
        if expired:
            logger.warning("expired leases recovered", count=len(expired))
        return len(expired)

    async def _recover(self, uow: UnitOfWork, task: Task, now: datetime) -> None:
        robot = await uow.robots.get(task.robot_id) if task.robot_id else None
        if robot is not None:
            robot.status = RobotStatus.IDLE.value
            robot.current_task_id = None
            robot.updated_at = now

        previous = TaskStatus(task.status)
        task.lease_expires_at = None
        task.updated_at = now

        if previous in {TaskStatus.PENDING, TaskStatus.RETRYING}:
            return

        if should_retry(task.attempts, task.max_attempts):
            delay = self._policy.delay_seconds(task.attempts)
            task.status = ensure_transition(previous, TaskStatus.RETRYING).value
            task.available_at = now + timedelta(seconds=delay)
            task.last_error = "lease expired: robot did not report progress"
            task.version += 1
            await uow.events.add(
                _event(
                    task,
                    TaskEventKind.LEASE_EXPIRED,
                    from_status=previous.value,
                    to_status=task.status,
                    robot_id=task.robot_id,
                    message=f"retry in {delay:.1f}s",
                    payload={"attempt": task.attempts, "retry_in_seconds": round(delay, 3)},
                )
            )
            return

        task.status = ensure_transition(previous, TaskStatus.FAILED).value
        task.last_error = task.last_error or "lease expired: robot did not report progress"
        task.finished_at = now
        task.version += 1
        await uow.events.add(
            _event(
                task,
                TaskEventKind.FAILED,
                from_status=previous.value,
                to_status=task.status,
                robot_id=task.robot_id,
                message="attempts exhausted after lease expiry",
                payload={"attempts": task.attempts},
            )
        )


def _event(task: Task, kind: TaskEventKind, **kwargs):
    from robot_dispatch.db.models import TaskEvent

    return TaskEvent.new(task_id=task.id, kind=kind.value, **kwargs)


def _command_outbox_message(command: CommandMessage, *, timeout_seconds: int):
    from robot_dispatch.db.models import OutboxMessage

    return OutboxMessage.new(
        exchange=COMMANDS_EXCHANGE,
        routing_key=command_routing_key(command.robot_id),
        payload=command.model_dump(mode="json"),
        message_id=str(command.command_id),
        headers={"task_id": str(command.task_id), "attempt": command.attempt},
        expiration_ms=timeout_seconds * 1000,
    )
