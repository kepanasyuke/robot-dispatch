from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fleet_monitor.models import (
    AlertConflict,
    AlertStatus,
    AlertType,
    RobotHealth,
    Severity,
    UnknownAlert,
)
from fleet_monitor.monitor import FleetMonitor

BASE_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, moment: datetime = BASE_TIME) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, seconds: float) -> datetime:
        self.moment += timedelta(seconds=seconds)
        return self.moment


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def monitor(clock) -> FleetMonitor:
    return FleetMonitor(clock=clock)


def health(
    clock: FakeClock,
    *,
    robot_id: str = "robot-1",
    silence: float = 0.0,
    battery: float | None = None,
    task_started: datetime | None = None,
    error_rate: float = 0.0,
) -> RobotHealth:
    return RobotHealth(
        robot_id=robot_id,
        last_seen=clock.moment - timedelta(seconds=silence),
        battery_percent=battery,
        active_task_started=task_started,
        error_rate=error_rate,
    )


def test_offline_alert_is_created_for_silent_robot(monitor, clock) -> None:
    alerts = monitor.observe(health(clock, silence=120))

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.type is AlertType.OFFLINE
    assert alert.severity is Severity.CRITICAL
    assert alert.status is AlertStatus.OPEN
    assert "no heartbeat" in alert.message


def test_fresh_heartbeat_resolves_offline_alert(monitor, clock) -> None:
    monitor.observe(health(clock, silence=120))

    alerts = monitor.observe(health(clock, silence=0))

    assert len(alerts) == 1
    assert alerts[0].status is AlertStatus.RESOLVED
    assert alerts[0].resolved_at is not None
    assert monitor.alerts(status=AlertStatus.OPEN) == []


def test_repeated_observation_does_not_duplicate_alert(monitor, clock) -> None:
    monitor.observe(health(clock, silence=120))
    monitor.observe(health(clock, silence=130))

    alerts = monitor.alerts()

    assert len(alerts) == 1
    assert alerts[0].count == 1  # debounce window is 60s

    clock.advance(61)
    monitor.observe(health(clock, silence=200))

    assert monitor.alerts()[0].count == 2


def test_low_battery_uses_hysteresis(monitor, clock) -> None:
    monitor.observe(health(clock, battery=12.0))
    alert = monitor.alerts()[0]
    assert alert.type is AlertType.LOW_BATTERY
    assert alert.severity is Severity.WARNING

    # 22% sits between the threshold (20) and threshold + hysteresis (25): no change.
    monitor.observe(health(clock, battery=22.0))
    assert monitor.alerts()[0].status is AlertStatus.OPEN

    monitor.observe(health(clock, battery=30.0))
    assert monitor.alerts()[0].status is AlertStatus.RESOLVED


def test_stuck_task_alert_lifecycle(monitor, clock) -> None:
    recent = clock.moment - timedelta(minutes=5)
    assert monitor.observe(health(clock, task_started=recent)) == []

    long_running = clock.moment - timedelta(minutes=20)
    alerts = monitor.observe(health(clock, task_started=long_running))
    assert alerts[0].type is AlertType.STUCK_TASK
    assert "task runs" in alerts[0].message

    resolved = monitor.observe(health(clock, task_started=None))
    assert resolved[0].status is AlertStatus.RESOLVED


def test_error_rate_alert(monitor, clock) -> None:
    alerts = monitor.observe(health(clock, error_rate=0.5))
    assert alerts[0].type is AlertType.ERROR_RATE
    assert alerts[0].severity is Severity.CRITICAL

    resolved = monitor.observe(health(clock, error_rate=0.1))
    assert resolved[0].status is AlertStatus.RESOLVED


def test_acknowledge_alert(monitor, clock) -> None:
    alert = monitor.observe(health(clock, silence=120))[0]

    acked = monitor.ack(alert.id, by="oncall")

    assert acked.status is AlertStatus.ACKED
    assert acked.acknowledged_by == "oncall"
    assert monitor.stats()["alerts_acked"] == 1


def test_ack_requires_author(monitor, clock) -> None:
    alert = monitor.observe(health(clock, silence=120))[0]

    with pytest.raises(ValueError):
        monitor.ack(alert.id, by="  ")


def test_ack_unknown_alert(monitor) -> None:
    with pytest.raises(UnknownAlert):
        monitor.ack("alert-missing", by="oncall")


def test_resolved_alert_cannot_be_acked_or_resolved_again(monitor, clock) -> None:
    alert = monitor.observe(health(clock, silence=120))[0]
    monitor.resolve(alert.id)

    with pytest.raises(AlertConflict):
        monitor.ack(alert.id, by="oncall")
    with pytest.raises(AlertConflict):
        monitor.resolve(alert.id)


def test_stats_breakdown(monitor, clock) -> None:
    monitor.observe(health(clock, silence=120))
    monitor.observe(health(clock, robot_id="robot-2", battery=5.0))

    stats = monitor.stats()

    assert stats["robots_known"] == 2
    assert stats["alerts_active"] == 2
    assert stats["alerts_total_created"] == 2
    assert stats["by_severity"] == {"info": 0, "warning": 1, "critical": 1}
    assert stats["by_type"]["offline"] == 1
    assert stats["by_type"]["low_battery"] == 1


def test_filters_by_robot_and_status(monitor, clock) -> None:
    monitor.observe(health(clock, silence=120))
    monitor.observe(health(clock, robot_id="robot-2", battery=5.0))

    robot_two = monitor.alerts(robot_id="robot-2")
    assert len(robot_two) == 1
    assert robot_two[0].robot_id == "robot-2"
    assert monitor.alerts(status=AlertStatus.RESOLVED) == []
