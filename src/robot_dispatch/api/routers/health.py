from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from robot_dispatch.api.deps import get_broker, get_settings_dep, get_uow_factory
from robot_dispatch.api.schemas import HealthResponse
from robot_dispatch.config import Settings
from robot_dispatch.messaging.broker import Broker
from robot_dispatch.repositories.protocols import UnitOfWorkFactory

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(status="ok", checks={})


@router.get("/ready", response_model=HealthResponse)
async def readiness(
    response: Response,
    uow_factory: Annotated[UnitOfWorkFactory, Depends(get_uow_factory)],
    broker: Annotated[Broker | None, Depends(get_broker)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> HealthResponse:
    checks: dict[str, str] = {}

    try:
        async with uow_factory() as uow:
            await uow.tasks.count_by_status()
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - readiness must report, not raise
        checks["database"] = f"error: {exc}"

    if settings.database_url:  # broker is optional for the API process
        checks["rabbitmq"] = "ok" if broker is not None and broker.connected else "unavailable"

    healthy = checks.get("database") == "ok"
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="ok" if healthy else "degraded", checks=checks)
