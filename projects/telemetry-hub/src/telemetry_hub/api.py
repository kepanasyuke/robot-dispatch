"""HTTP surface of the telemetry hub."""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from telemetry_hub.ingest import IngestOutcome, TelemetryIngestor
from telemetry_hub.models import RobotSnapshot, TelemetrySample


class TelemetryBatch(BaseModel):
    samples: list[TelemetrySample] = Field(min_length=1, max_length=500)


class IngestReport(BaseModel):
    accepted: int
    duplicate: int
    out_of_order: int
    invalid: int
    results: list[dict]


def create_app(ingestor: TelemetryIngestor | None = None) -> FastAPI:
    app = FastAPI(
        title="Telemetry Hub",
        version="0.1.0",
        description="MQTT telemetry ingest with dedup, ordering and rolling aggregates.",
    )
    app.state.ingestor = ingestor or TelemetryIngestor()

    def get_ingestor(request: Request) -> TelemetryIngestor:
        return request.app.state.ingestor  # type: ignore[no-any-return]

    @app.post("/api/v1/telemetry", response_model=IngestReport)
    async def ingest(batch: TelemetryBatch, request: Request) -> IngestReport:
        service = get_ingestor(request)
        counts = {outcome.value: 0 for outcome in IngestOutcome}
        results: list[dict] = []
        for sample in batch.samples:
            result = service.apply(sample)
            counts[result.outcome.value] += 1
            results.append(
                {
                    "robot_id": result.robot_id,
                    "seq": result.seq,
                    "outcome": result.outcome.value,
                    "detail": result.detail,
                }
            )
        return IngestReport(**counts, results=results)

    @app.get("/api/v1/robots", response_model=list[RobotSnapshot])
    async def list_robots(request: Request) -> list[RobotSnapshot]:
        return get_ingestor(request).snapshots()

    @app.get("/api/v1/robots/{robot_id}", response_model=RobotSnapshot)
    async def get_robot(robot_id: str, request: Request) -> RobotSnapshot:
        snapshot = get_ingestor(request).snapshot(robot_id)
        if snapshot is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"robot {robot_id} is unknown"
            )
        return snapshot

    @app.get("/api/v1/robots/{robot_id}/samples", response_model=list[TelemetrySample])
    async def get_samples(
        robot_id: str,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> list[TelemetrySample]:
        service = get_ingestor(request)
        if service.snapshot(robot_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"robot {robot_id} is unknown"
            )
        return service.history(robot_id, limit=limit)

    @app.get("/api/v1/stats")
    async def get_stats(request: Request) -> dict:
        return get_ingestor(request).stats()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
