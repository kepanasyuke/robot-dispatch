from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from robot_dispatch.config import Settings, get_settings
from robot_dispatch.messaging.broker import Broker
from robot_dispatch.repositories.protocols import UnitOfWorkFactory
from robot_dispatch.services.task_service import RobotService, TaskService


def get_settings_dep(request: Request) -> Settings:
    """Settings are per-app (tests and multi-tenant runs override them)."""
    settings = getattr(request.app.state, "settings", None)
    return settings or get_settings()


def get_uow_factory(request: Request) -> UnitOfWorkFactory:
    return request.app.state.uow_factory


def get_broker(request: Request) -> Broker | None:
    return getattr(request.app.state, "broker", None)


def get_task_service(
    uow_factory: Annotated[UnitOfWorkFactory, Depends(get_uow_factory)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> TaskService:
    return TaskService(uow_factory, settings)


def get_robot_service(
    uow_factory: Annotated[UnitOfWorkFactory, Depends(get_uow_factory)],
) -> RobotService:
    return RobotService(uow_factory)


async def verify_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    settings: Annotated[Settings | None, Depends(get_settings_dep)] = None,
) -> None:
    """Optional API key: enforced only when DISPATCH_API_KEY is configured."""
    if settings and settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-API-Key",
        )


ApiKeyGuard = Depends(verify_api_key)
