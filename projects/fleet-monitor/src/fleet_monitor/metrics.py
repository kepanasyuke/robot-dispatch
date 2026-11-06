"""Prometheus text exposition of the monitor state.

Hand-rolled to keep the dependency list honest: the format is a few lines of
text, and a scrape endpoint that returns 200 with correct labels is enough for a
Prometheus/Grafana setup.
"""

from __future__ import annotations

from fleet_monitor.monitor import FleetMonitor


def _gauge(lines: list[str], name: str, help_text: str, value: int) -> None:
    lines.append(f"# HELP {name} {help_text}")
    lines.append(f"# TYPE {name} gauge")
    lines.append(f"{name} {value}")


def _labelled(lines: list[str], name: str, help_text: str, label: str, values: dict[str, int]) -> None:
    lines.append(f"# HELP {name} {help_text}")
    lines.append(f"# TYPE {name} gauge")
    for key, value in sorted(values.items()):
        lines.append(f'{name}{{{label}="{key}"}} {value}')


def render_prometheus(monitor: FleetMonitor) -> str:
    stats = monitor.stats()
    lines: list[str] = []
    _gauge(lines, "fleet_robots_known", "Robots the monitor has seen", stats["robots_known"])
    _gauge(lines, "fleet_robots_online", "Robots with a fresh heartbeat", stats["robots_online"])
    _gauge(
        lines,
        "fleet_alerts_active",
        "Alerts currently open or acknowledged",
        stats["alerts_active"],
    )
    _labelled(
        lines,
        "fleet_alerts_active_by_severity",
        "Active alerts split by severity",
        "severity",
        stats["by_severity"],
    )
    _labelled(
        lines,
        "fleet_alerts_active_by_type",
        "Active alerts split by rule",
        "type",
        stats["by_type"],
    )
    lines.append("# HELP fleet_alert_instances_total Alerts created since process start")
    lines.append("# TYPE fleet_alert_instances_total counter")
    lines.append(f"fleet_alert_instances_total {stats['alerts_total_created']}")
    return "\n".join(lines) + "\n"
