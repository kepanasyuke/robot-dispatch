from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from robot_dispatch.api.deps import ApiKeyGuard, get_broker, get_robot_service
from robot_dispatch.api.schemas import RobotListResponse, RobotRegisterRequest, RobotResponse
from robot_dispatch.messaging.broker import Broker
from robot_dispatch.services.task_service import RobotService

router = APIRouter(prefix="/robots", tags=["robots"], dependencies=[ApiKeyGuard])


@router.post("", response_model=RobotResponse, status_code=status.HTTP_201_CREATED)
async def register_robot(
    body: RobotRegisterRequest,
    response: Response,
    service: Annotated[RobotService, Depends(get_robot_service)],
    broker: Annotated[Broker | None, Depends(get_broker)] = None,
) -> RobotResponse:
    robot, created = await service.register(
        name=body.name,
        namespace=body.namespace,
        capabilities=body.capabilities,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    if broker is not None and broker.connected:
        await broker.ensure_robot_queue(robot.id)
    return RobotResponse.from_robot(robot)


@router.get("", response_model=RobotListResponse)
async def list_robots(
    service: Annotated[RobotService, Depends(get_robot_service)],
) -> RobotListResponse:
    robots = await service.list()
    return RobotListResponse(items=[RobotResponse.from_robot(robot) for robot in robots])


@router.get("/{robot_id}", response_model=RobotResponse)
async def get_robot(
    robot_id: uuid.UUID,
    service: Annotated[RobotService, Depends(get_robot_service)],
) -> RobotResponse:
    return RobotResponse.from_robot(await service.get(robot_id))
