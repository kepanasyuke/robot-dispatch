"""Alert lifecycle objects: an alert is a state machine, not a log line."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(StrEnum):
    OFFLINE = "offline"
    LOW_BATTERY = "low_battery"
    STUCK_TASK = "stuck_task"
    ERROR_RATE = "error_rate"


class AlertStatus(StrEnum):
    OPEN = "open"
    ACKED = "acked"
    RESOLVED = "resolved"

    @property
    def is_active(self) -> bool:
        return self in {AlertStatus.OPEN, AlertStatus.ACKED}


@dataclass
class RobotHealth:
    """What the monitor needs to know about a robot at one point in time."""

    robot_id: str
    last_seen: datetime | None = None
    battery_percent: float | None = None
    active_task_started: datetime | None = None
    error_rate: float = 0.0


@dataclass
class Alert:
    id: str
    robot_id: str
    type: AlertType
    severity: Severity
    status: AlertStatus
    first_seen: datetime
    last_seen: datetime
    count: int = 1
    message: str = ""
    acknowledged_by: str | None = None
    resolved_at: datetime | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "robot_id": self.robot_id,
            "type": self.type.value,
            "severity": self.severity.value,
            "status": self.status.value,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "count": self.count,
            "message": self.message,
            "acknowledged_by": self.acknowledged_by,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class UnknownAlert(LookupError):
    def __init__(self, alert_id: str) -> None:
        self.alert_id = alert_id
        super().__init__(f"alert {alert_id} is unknown")


class AlertConflict(RuntimeError):
    def __init__(self, alert_id: str, status: AlertStatus) -> None:
        self.alert_id = alert_id
        self.status = status
        super().__init__(f"alert {alert_id} is {status.value}")
