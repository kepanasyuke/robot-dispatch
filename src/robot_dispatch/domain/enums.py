from __future__ import annotations

from enum import StrEnum


class TaskStatus(StrEnum):
    PENDING = "pending"
    RETRYING = "retrying"
    ASSIGNED = "assigned"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in TERMINAL_TASK_STATUSES

    @property
    def is_active(self) -> bool:
        return self in ACTIVE_TASK_STATUSES


class RobotStatus(StrEnum):
    IDLE = "idle"
    BUSY = "busy"
    OFFLINE = "offline"


TERMINAL_TASK_STATUSES = frozenset({TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED})
ACTIVE_TASK_STATUSES = frozenset({TaskStatus.RETRYING, TaskStatus.ASSIGNED, TaskStatus.RUNNING})
QUEUED_TASK_STATUSES = frozenset({TaskStatus.PENDING, TaskStatus.RETRYING})


class TaskEventKind(StrEnum):
    CREATED = "created"
    DISPATCHED = "dispatched"
    PROGRESS = "progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRY_SCHEDULED = "retry_scheduled"
    LEASE_EXPIRED = "lease_expired"
    CANCELLED = "cancelled"
    RESULT_IGNORED = "result_ignored"
