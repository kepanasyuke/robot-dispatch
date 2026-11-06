"""Alert lifecycle management.

One alert per `(robot_id, type)`: reopening is an update, recovery is an
automatic resolve (an operator should not have to close offline alerts by hand),
and a repeated observation inside the debounce window does not inflate `count`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TypedDict

from fleet_monitor.models import (
    Alert,
    AlertConflict,
    AlertStatus,
    AlertType,
    RobotHealth,
    Severity,
    UnknownAlert,
)
from fleet_monitor.rules import RuleConfig, RuleEngine


class MonitorStats(TypedDict):
    robots_known: int
    robots_online: int
    alerts_active: int
    alerts_open: int
    alerts_acked: int
    alerts_total_created: int
    by_severity: dict[str, int]
    by_type: dict[str, int]


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


class FleetMonitor:
    def __init__(
        self,
        engine: RuleEngine | None = None,
        *,
        clock=utcnow,
        config: RuleConfig | None = None,
    ) -> None:
        self._config = config or (engine.config if engine else RuleConfig())
        self._engine = engine or RuleEngine(self._config)
        self._clock = clock
        self._health: dict[str, RobotHealth] = {}
        self._alerts: dict[str, Alert] = {}
        self._active: dict[tuple[str, AlertType], str] = {}
        self._last_bump: dict[tuple[str, AlertType], datetime] = {}
        self._total_created = 0

    # ------------------------------------------------------------------ input

    def observe(self, health: RobotHealth) -> list[Alert]:
        now = self._clock()
        self._health[health.robot_id] = health
        touched: list[Alert] = []
        for finding in self._engine.evaluate(health, now=now):
            key = (health.robot_id, finding.type)
            alert_id = self._active.get(key)

            if finding.active and alert_id is None:
                alert = Alert(
                    id=f"alert-{uuid.uuid4().hex[:12]}",
                    robot_id=health.robot_id,
                    type=finding.type,
                    severity=finding.severity,
                    status=AlertStatus.OPEN,
                    first_seen=now,
                    last_seen=now,
                    count=1,
                    message=finding.message,
                )
                self._alerts[alert.id] = alert
                self._active[key] = alert.id
                self._last_bump[key] = now
                self._total_created += 1
                touched.append(alert)
                continue

            if finding.active and alert_id is not None:
                alert = self._alerts[alert_id]
                alert.last_seen = now
                alert.message = finding.message
                alert.severity = max(finding.severity, alert.severity, key=_severity_rank)
                if self._should_bump(key, now):
                    alert.count += 1
                    self._last_bump[key] = now
                touched.append(alert)
                continue

            if not finding.active and alert_id is not None:
                alert = self._alerts[alert_id]
                alert.status = AlertStatus.RESOLVED
                alert.resolved_at = now
                alert.last_seen = now
                alert.message = finding.message
                self._active.pop(key, None)
                touched.append(alert)

        return touched

    def _should_bump(self, key: tuple[str, AlertType], now: datetime) -> bool:
        last = self._last_bump.get(key)
        return last is None or now - last >= timedelta(seconds=self._config.min_repeat_seconds)

    # ----------------------------------------------------------------- output

    def alerts(
        self,
        *,
        status: AlertStatus | None = None,
        robot_id: str | None = None,
    ) -> list[Alert]:
        items = list(self._alerts.values())
        if status is not None:
            items = [alert for alert in items if alert.status is status]
        if robot_id is not None:
            items = [alert for alert in items if alert.robot_id == robot_id]
        items.sort(key=lambda alert: (alert.status is AlertStatus.RESOLVED, alert.last_seen), reverse=False)
        items.sort(key=lambda alert: alert.first_seen, reverse=True)
        return items

    def get(self, alert_id: str) -> Alert:
        alert = self._alerts.get(alert_id)
        if alert is None:
            raise UnknownAlert(alert_id)
        return alert

    def ack(self, alert_id: str, *, by: str) -> Alert:
        alert = self.get(alert_id)
        if alert.status is AlertStatus.RESOLVED:
            raise AlertConflict(alert_id, alert.status)
        if not by.strip():
            raise ValueError("acknowledged_by must not be empty")
        alert.status = AlertStatus.ACKED
        alert.acknowledged_by = by
        alert.last_seen = self._clock()
        return alert

    def resolve(self, alert_id: str) -> Alert:
        alert = self.get(alert_id)
        if alert.status is AlertStatus.RESOLVED:
            raise AlertConflict(alert_id, alert.status)
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = self._clock()
        self._active.pop((alert.robot_id, alert.type), None)
        return alert

    def health(self) -> list[RobotHealth]:
        return [self._health[robot_id] for robot_id in sorted(self._health)]

    def stats(self) -> MonitorStats:
        now = self._clock()
        active = [alert for alert in self._alerts.values() if alert.status.is_active]
        by_severity: dict[str, int] = {severity.value: 0 for severity in Severity}
        by_type: dict[str, int] = {alert_type.value: 0 for alert_type in AlertType}
        for alert in active:
            by_severity[alert.severity.value] += 1
            by_type[alert.type.value] += 1

        offline_after = self._config.offline_after
        online = sum(
            1
            for health in self._health.values()
            if health.last_seen is not None and now - health.last_seen <= offline_after
        )
        return {
            "robots_known": len(self._health),
            "robots_online": online,
            "alerts_active": len(active),
            "alerts_open": sum(1 for alert in active if alert.status is AlertStatus.OPEN),
            "alerts_acked": sum(1 for alert in active if alert.status is AlertStatus.ACKED),
            "alerts_total_created": self._total_created,
            "by_severity": by_severity,
            "by_type": by_type,
        }


def _severity_rank(severity: Severity) -> int:
    return {Severity.INFO: 0, Severity.WARNING: 1, Severity.CRITICAL: 2}[severity]
