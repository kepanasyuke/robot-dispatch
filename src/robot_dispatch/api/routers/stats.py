from __future__ import annotations

from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends

from robot_dispatch.api.deps import ApiKeyGuard, get_broker, get_robot_service, get_task_service
from robot_dispatch.api.schemas import StatsResponse
from robot_dispatch.domain.enums import TaskStatus
from robot_dispatch.messaging.broker import Broker
from robot_dispatch.messaging.messages import DLQ_QUEUE, RESULTS_QUEUE
from robot_dispatch.services.task_service import RobotService, TaskService

router = APIRouter(prefix="/stats", tags=["stats"], dependencies=[ApiKeyGuard])


@router.get("", response_model=StatsResponse)
async def get_stats(
    tasks: Annotated[TaskService, Depends(get_task_service)],
    robots: Annotated[RobotService, Depends(get_robot_service)],
    broker: Annotated[Broker | None, Depends(get_broker)] = None,
) -> StatsResponse:
    task_counts = await tasks.stats()
    for item in TaskStatus:
        task_counts.setdefault(item.value, 0)

    robot_counts = Counter(robot.status for robot in await robots.list())

    queues: dict[str, int | None] = {}
    if broker is not None and broker.connected:
        queues[RESULTS_QUEUE] = await broker.queue_depth(RESULTS_QUEUE)
        queues[DLQ_QUEUE] = await broker.queue_depth(DLQ_QUEUE)

    return StatsResponse(
        tasks=dict(sorted(task_counts.items())),
        task_total=sum(task_counts.values()),
        robots=dict(sorted(robot_counts.items())),
        queues=queues,
    )
