from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status

from robot_dispatch.api.deps import ApiKeyGuard, get_task_service
from robot_dispatch.api.schemas import (
    TaskCreateRequest,
    TaskEventResponse,
    TaskListResponse,
    TaskResponse,
)
from robot_dispatch.domain.enums import TaskStatus
from robot_dispatch.services.task_service import CreateTaskCommand, TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[ApiKeyGuard])


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Idempotent replay: the task already exists"}},
)
async def create_task(
    body: TaskCreateRequest,
    response: Response,
    service: Annotated[TaskService, Depends(get_task_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> TaskResponse:
    external_id = body.external_id or (idempotency_key.strip() if idempotency_key else None)
    result = await service.create(
        CreateTaskCommand(
            type=body.type,
            payload=body.payload,
            priority=body.priority,
            external_id=external_id,
            max_attempts=body.max_attempts,
            timeout_seconds=body.timeout_seconds,
        )
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replay"] = "true"
    else:
        response.headers["Location"] = f"/api/v1/tasks/{result.task.id}"
    return TaskResponse.model_validate(result.task)


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    service: Annotated[TaskService, Depends(get_task_service)],
    task_status: Annotated[list[TaskStatus] | None, Query(alias="status")] = None,
    robot_id: uuid.UUID | None = None,
    task_type: Annotated[str | None, Query(alias="type")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TaskListResponse:
    items = await service.list(
        statuses=[item.value for item in task_status] if task_status else None,
        robot_id=robot_id,
        task_type=task_type,
        limit=limit,
        offset=offset,
    )
    return TaskListResponse(
        items=[TaskResponse.model_validate(item) for item in items],
        limit=limit,
        offset=offset,
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: uuid.UUID,
    service: Annotated[TaskService, Depends(get_task_service)],
) -> TaskResponse:
    return TaskResponse.model_validate(await service.get(task_id))


@router.get("/{task_id}/events", response_model=list[TaskEventResponse])
async def get_task_events(
    task_id: uuid.UUID,
    service: Annotated[TaskService, Depends(get_task_service)],
) -> list[TaskEventResponse]:
    await service.get(task_id)
    events = await service.events(task_id)
    return [TaskEventResponse.model_validate(event) for event in events]


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(
    task_id: uuid.UUID,
    service: Annotated[TaskService, Depends(get_task_service)],
) -> TaskResponse:
    return TaskResponse.model_validate(await service.cancel(task_id))
