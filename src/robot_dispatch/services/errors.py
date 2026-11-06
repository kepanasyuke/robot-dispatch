from __future__ import annotations


class DomainError(Exception):
    """Base class for errors that map to a 4xx API response."""


class TaskNotFound(DomainError):
    def __init__(self, task_id: object) -> None:
        self.task_id = task_id
        super().__init__(f"task {task_id} not found")


class RobotNotFound(DomainError):
    def __init__(self, robot_id: object) -> None:
        self.robot_id = robot_id
        super().__init__(f"robot {robot_id} not found")


class TaskConflict(DomainError):
    """The task exists but its current state forbids the operation."""

    def __init__(self, task_id: object, status: str, reason: str) -> None:
        self.task_id = task_id
        self.status = status
        self.reason = reason
        super().__init__(f"task {task_id} in status {status}: {reason}")
