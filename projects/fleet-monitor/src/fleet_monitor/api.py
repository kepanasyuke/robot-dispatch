"""HTTP surface of the fleet monitor: health samples, alert workflow, metrics."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator

from fleet_monitor.metrics import render_prometheus
from fleet_monitor.models import (
    Alert,
    AlertConflict,
    AlertStatus,
    RobotHealth,
    UnknownAlert,
)
from fleet_monitor.monitor import FleetMonitor


class HealthSample(BaseModel):
    robot_id: str = Field(min_length=1, max_length=64)
    last_seen: datetime | None = None
    battery_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    active_task_started: datetime | None = None
    error_rate: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("last_seen", "active_task_started")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return value

    def to_health(self) -> RobotHealth:
        return RobotHealth(
            robot_id=self.robot_id,
            last_seen=self.last_seen,
            battery_percent=self.battery_percent,
            active_task_started=self.active_task_started,
            error_rate=self.error_rate,
        )


class AlertOut(BaseModel):
    id: str
    robot_id: str
    type: str
    severity: str
    status: str
    first_seen: datetime
    last_seen: datetime
    count: int
    message: str
    acknowledged_by: str | None
    resolved_at: datetime | None

    @classmethod
    def from_alert(cls, alert: Alert) -> AlertOut:
        return cls(**alert.as_dict())  # type: ignore[arg-type]


class HealthReport(BaseModel):
    alerts: list[AlertOut]
    evaluated: int


class AckRequest(BaseModel):
    by: str = Field(min_length=1, max_length=128)


def create_app(monitor: FleetMonitor | None = None) -> FastAPI:
    app = FastAPI(
        title="Fleet Monitor",
        version="0.1.0",
        description="Heartbeat SLA, alert lifecycle with hysteresis, Prometheus metrics.",
    )
    app.state.monitor = monitor or FleetMonitor()

    def get_monitor(request: Request) -> FleetMonitor:
        return request.app.state.monitor  # type: ignore[no-any-return]

    @app.post("/api/v1/health", response_model=HealthReport)
    async def submit_health(sample: HealthSample, request: Request) -> HealthReport:
        service = get_monitor(request)
        touched = service.observe(sample.to_health())
        return HealthReport(
            alerts=[AlertOut.from_alert(alert) for alert in touched],
            evaluated=len(service.health()),
        )

    @app.get("/api/v1/alerts", response_model=list[AlertOut])
    async def list_alerts(
        request: Request,
        alert_status: Annotated[AlertStatus | None, Query(alias="status")] = None,
        robot_id: str | None = None,
    ) -> list[AlertOut]:
        service = get_monitor(request)
        return [
            AlertOut.from_alert(alert)
            for alert in service.alerts(status=alert_status, robot_id=robot_id)
        ]

    @app.post("/api/v1/alerts/{alert_id}/ack", response_model=AlertOut)
    async def ack_alert(alert_id: str, body: AckRequest, request: Request) -> AlertOut:
        service = get_monitor(request)
        try:
            return AlertOut.from_alert(service.ack(alert_id, by=body.by))
        except UnknownAlert as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except AlertConflict as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @app.post("/api/v1/alerts/{alert_id}/resolve", response_model=AlertOut)
    async def resolve_alert(alert_id: str, request: Request) -> AlertOut:
        service = get_monitor(request)
        try:
            return AlertOut.from_alert(service.resolve(alert_id))
        except UnknownAlert as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except AlertConflict as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @app.get("/api/v1/robots")
    async def list_robots(request: Request) -> list[dict[str, Any]]:
        return [
            {
                "robot_id": health.robot_id,
                "last_seen": health.last_seen.isoformat() if health.last_seen else None,
                "battery_percent": health.battery_percent,
                "error_rate": health.error_rate,
            }
            for health in get_monitor(request).health()
        ]

    @app.get("/metrics", response_class=PlainTextResponse)
    async def metrics(request: Request) -> str:
        return render_prometheus(get_monitor(request))

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
