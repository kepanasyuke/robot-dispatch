"""Alert rules with hysteresis.

Rules answer two questions: is the condition active, and is it safe to clear it.
Without hysteresis a battery hovering around the threshold produces a new alert
every poll, and operators stop trusting the feed. `None` means "not enough data,
leave the alert as is".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from fleet_monitor.models import AlertType, RobotHealth, Severity


@dataclass(frozen=True)
class RuleConfig:
    offline_after: timedelta = timedelta(seconds=30)
    low_battery_percent: float = 20.0
    battery_hysteresis: float = 5.0
    stuck_task_after: timedelta = timedelta(minutes=15)
    error_rate_threshold: float = 0.2
    error_rate_hysteresis: float = 0.05
    min_repeat_seconds: int = 60


@dataclass(frozen=True)
class Finding:
    type: AlertType
    severity: Severity
    active: bool
    message: str


class RuleEngine:
    def __init__(self, config: RuleConfig | None = None) -> None:
        self.config = config or RuleConfig()

    def evaluate(self, health: RobotHealth, *, now: datetime) -> list[Finding]:
        findings = [
            self._offline(health, now),
            self._low_battery(health),
            self._stuck_task(health, now),
            self._error_rate(health),
        ]
        return [finding for finding in findings if finding is not None]

    def _offline(self, health: RobotHealth, now: datetime) -> Finding:
        stale = health.last_seen is None or now - health.last_seen > self.config.offline_after
        if health.last_seen is None:
            message = "robot has never reported"
        elif stale:
            silence = int((now - health.last_seen).total_seconds())
            message = f"no heartbeat for {silence}s"
        else:
            message = "heartbeat is fresh"
        return Finding(AlertType.OFFLINE, Severity.CRITICAL, stale, message)

    def _low_battery(self, health: RobotHealth) -> Finding | None:
        battery = health.battery_percent
        if battery is None:
            return None
        threshold = self.config.low_battery_percent
        if battery < threshold:
            return Finding(
                AlertType.LOW_BATTERY,
                Severity.WARNING,
                True,
                f"battery is {battery:.1f}% (threshold {threshold:.0f}%)",
            )
        if battery >= threshold + self.config.battery_hysteresis:
            return Finding(
                AlertType.LOW_BATTERY, Severity.WARNING, False, f"battery recovered to {battery:.1f}%"
            )
        return None

    def _stuck_task(self, health: RobotHealth, now: datetime) -> Finding:
        started = health.active_task_started
        if started is None:
            return Finding(AlertType.STUCK_TASK, Severity.WARNING, False, "no active task")
        running = now - started
        if running > self.config.stuck_task_after:
            return Finding(
                AlertType.STUCK_TASK,
                Severity.WARNING,
                True,
                f"task runs for {int(running.total_seconds())}s",
            )
        return Finding(AlertType.STUCK_TASK, Severity.WARNING, False, "task is within SLA")

    def _error_rate(self, health: RobotHealth) -> Finding | None:
        rate = health.error_rate
        threshold = self.config.error_rate_threshold
        if rate > threshold:
            return Finding(
                AlertType.ERROR_RATE,
                Severity.CRITICAL,
                True,
                f"error rate {rate:.0%} is above {threshold:.0%}",
            )
        if rate <= threshold - self.config.error_rate_hysteresis:
            return Finding(
                AlertType.ERROR_RATE, Severity.CRITICAL, False, f"error rate recovered to {rate:.0%}"
            )
        return None
