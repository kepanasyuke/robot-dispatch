"""gRPC server wiring: worker pool, interceptors, port binding."""

from __future__ import annotations

import logging
from concurrent import futures
from dataclasses import dataclass

import grpc

from grpc_fleet_api.interceptors import MetricsRegistry, ObservabilityInterceptor
from grpc_fleet_api.service import FleetService, register

logger = logging.getLogger("grpc_fleet_api.server")


@dataclass
class FleetGrpcServer:
    server: grpc.Server
    host: str
    port: int
    metrics: MetricsRegistry

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    def start(self) -> FleetGrpcServer:
        self.server.start()
        logger.info("gRPC fleet API listening on %s", self.address)
        return self

    def stop(self, grace: float | None = 0.5) -> None:
        self.server.stop(grace)
        logger.info("gRPC fleet API stopped")


def create_server(
    service: FleetService,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    max_workers: int = 10,
    metrics: MetricsRegistry | None = None,
) -> FleetGrpcServer:
    """Bind the server. Port 0 asks the OS for a free port, which tests rely on."""
    registry = metrics or MetricsRegistry()
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="fleet-rpc"),
        interceptors=(ObservabilityInterceptor(registry),),
        maximum_concurrent_rpcs=64,
    )
    register(service, server)
    bound_port = server.add_insecure_port(f"{host}:{port}")
    if bound_port == 0:
        raise RuntimeError(f"cannot bind gRPC server to {host}:{port}")
    return FleetGrpcServer(server=server, host=host, port=bound_port, metrics=registry)


def serve(*, host: str = "0.0.0.0", port: int = 50051) -> None:  # pragma: no cover - entrypoint
    from grpc_fleet_api.registry import FleetRegistry

    logging.basicConfig(level=logging.INFO)
    server = create_server(FleetService(FleetRegistry()), host=host, port=port).start()
    try:
        server.server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(grace=0.5)


if __name__ == "__main__":  # pragma: no cover
    serve()
