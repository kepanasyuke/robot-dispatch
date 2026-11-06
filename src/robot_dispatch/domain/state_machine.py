from __future__ import annotations

from robot_dispatch.domain.enums import QUEUED_TASK_STATUSES, TaskStatus

ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.PENDING, TaskStatus.ASSIGNED, TaskStatus.CANCELLED}),
    TaskStatus.RETRYING: frozenset({TaskStatus.RETRYING, TaskStatus.ASSIGNED, TaskStatus.CANCELLED}),
    TaskStatus.ASSIGNED: frozenset(
        {
            TaskStatus.ASSIGNED,
            TaskStatus.RUNNING,
            TaskStatus.SUCCEEDED,
            TaskStatus.FAILED,
            TaskStatus.RETRYING,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.RUNNING: frozenset(
        {
            TaskStatus.RUNNING,
            TaskStatus.SUCCEEDED,
            TaskStatus.FAILED,
            TaskStatus.RETRYING,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.SUCCEEDED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}

CANCELLABLE_STATUSES = frozenset(
    {TaskStatus.PENDING, TaskStatus.RETRYING, TaskStatus.ASSIGNED}
)


class InvalidTransition(Exception):
    def __init__(self, current: TaskStatus | str, target: TaskStatus | str) -> None:
        self.current = TaskStatus(current)
        self.target = TaskStatus(target)
        super().__init__(f"illegal task transition {self.current} -> {self.target}")


def can_transition(current: TaskStatus | str, target: TaskStatus | str) -> bool:
    return TaskStatus(target) in ALLOWED_TRANSITIONS[TaskStatus(current)]


def ensure_transition(current: TaskStatus | str, target: TaskStatus | str) -> TaskStatus:
    """Validate the transition and return the target status.

    Every status change in the service goes through this guard, so an illegal
    transition fails loudly instead of silently corrupting the task lifecycle.
    """
    if not can_transition(current, target):
        raise InvalidTransition(current, target)
    return TaskStatus(target)


def is_queued(status: TaskStatus | str) -> bool:
    return TaskStatus(status) in QUEUED_TASK_STATUSES


def is_cancellable(status: TaskStatus | str) -> bool:
    return TaskStatus(status) in CANCELLABLE_STATUSES
