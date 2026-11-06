from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from robot_dispatch.api.routers import health, robots, stats, tasks
from robot_dispatch.config import Settings, get_settings
from robot_dispatch.db.session import create_engine, create_session_factory
from robot_dispatch.db.uow import make_sql_uow_factory
from robot_dispatch.logging_setup import configure_logging, get_logger
from robot_dispatch.messaging.broker import Broker
from robot_dispatch.services.errors import RobotNotFound, TaskConflict, TaskNotFound

logger = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    configure_logging(settings.log_level, settings.log_json)

    engine = create_engine(settings.database_url)
    app.state.engine = engine
    app.state.uow_factory = make_sql_uow_factory(create_session_factory(engine))

    broker: Broker | None = None
    try:
        broker = Broker(
            settings.rabbitmq_url,
            prefetch=settings.consumer_prefetch,
            connect_retries=3,
            connect_delay=1.0,
        )
        await broker.connect()
        for robot in await _known_robots(app.state.uow_factory):
            await broker.ensure_robot_queue(robot)
    except Exception as exc:  # noqa: BLE001 - API must start even if the broker is down
        logger.warning("rabbitmq is not available for the API process", error=str(exc))
        broker = None
    app.state.broker = broker

    logger.info("api started", environment=settings.environment)
    try:
        yield
    finally:
        if broker is not None:
            await broker.close()
        await engine.dispose()
        logger.info("api stopped")


async def _known_robots(uow_factory) -> list[uuid.UUID]:
    try:
        async with uow_factory() as uow:
            robots = await uow.robots.list()
            return [robot.id for robot in robots]
    except Exception:  # noqa: BLE001 - database may not be migrated yet
        return []


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="Robot Dispatch Service",
        version="0.1.0",
        description=(
            "Fault-tolerant task dispatch for a ROS2 robot fleet: task queue, "
            "assignment to idle robots, lease-based failure recovery, "
            "transactional outbox and RabbitMQ integration."
        ),
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(TaskNotFound)
    async def _task_not_found(_: Request, exc: TaskNotFound) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc), "task_id": str(exc.task_id)},
        )

    @app.exception_handler(RobotNotFound)
    async def _robot_not_found(_: Request, exc: RobotNotFound) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc), "robot_id": str(exc.robot_id)},
        )

    @app.exception_handler(TaskConflict)
    async def _task_conflict(_: Request, exc: TaskConflict) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": exc.reason, "status": exc.status, "task_id": str(exc.task_id)},
        )

    api_prefix = "/api/v1"
    app.include_router(tasks.router, prefix=api_prefix)
    app.include_router(robots.router, prefix=api_prefix)
    app.include_router(stats.router, prefix=api_prefix)
    app.include_router(health.router)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, Any]:
        return {"service": settings.app_name, "docs": "/docs", "api": api_prefix}

    return app


app = create_app()
