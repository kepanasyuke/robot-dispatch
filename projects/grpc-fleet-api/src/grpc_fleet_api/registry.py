"""In-memory fleet registry behind the gRPC service.

Kept separate from the transport so the same logic can be reused by the REST
dispatch service. Liveness is derived, not stored: a robot whose last heartbeat
is older than `offline_after` is reported offline even if its own status said
"idle", which is exactly the bug that makes a scheduler wait for a dead robot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


@dataclass
class RobotRecord:
    id: str
    name: str
    status: str = "offline"
    capabilities: set[str] = field(default_factory=set)
    battery_percent: float = 0.0
    last_seen: datetime | None = None

    def supports(self, task_type: str) -> bool:
        return task_type in self.capabilities


class FleetRegistry:
    def __init__(
        self,
        *,
        offline_after: timedelta = timedelta(seconds=30),
        clock=utcnow,
    ) -> None:
        self._robots: dict[str, RobotRecord] = {}
        self._offline_after = offline_after
        self._clock = clock

    def upsert_robot(
        self,
        robot_id: str,
        *,
        name: str | None = None,
        capabilities: set[str] | None = None,
        status: str = "idle",
    ) -> RobotRecord:
        record = self._robots.get(robot_id)
        if record is None:
            record = RobotRecord(id=robot_id, name=name or robot_id)
            self._robots[robot_id] = record
        if capabilities is not None:
            record.capabilities = set(capabilities)
        record.status = status
        record.last_seen = self._clock()
        return record

    def get(self, robot_id: str) -> RobotRecord | None:
        return self._robots.get(robot_id)

    def list(self, *, status: str | None = None, limit: int = 100) -> list[RobotRecord]:
        robots = sorted(self._robots.values(), key=lambda item: item.id)
        if status:
            robots = [robot for robot in robots if self.effective_status(robot) == status]
        return robots[:limit]

    def effective_status(self, robot: RobotRecord) -> str:
        if robot.last_seen is None or self._clock() - robot.last_seen > self._offline_after:
            return "offline"
        return robot.status

    def heartbeat(
        self,
        robot_id: str,
        *,
        status: str | None = None,
        battery_percent: float | None = None,
    ) -> RobotRecord | None:
        record = self._robots.get(robot_id)
        if record is None:
            return None
        record.last_seen = self._clock()
        if status in {"idle", "busy", "offline"}:
            record.status = status
        if battery_percent is not None:
            record.battery_percent = battery_percent
        return record

    def find_idle(self, task_type: str, *, preferred: str | None = None) -> RobotRecord | None:
        if preferred:
            record = self._robots.get(preferred)
            if record and self.effective_status(record) == "idle" and record.supports(task_type):
                return record
            return None
        candidates = [
            robot
            for robot in self._robots.values()
            if self.effective_status(robot) == "idle" and robot.supports(task_type)
        ]
        candidates.sort(key=lambda robot: (robot.battery_percent, robot.id), reverse=True)
        return candidates[0] if candidates else None

    def mark_busy(self, robot_id: str) -> None:
        record = self._robots.get(robot_id)
        if record is not None:
            record.status = "busy"
