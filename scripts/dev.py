#!/usr/bin/env python
"""Cross-platform task runner for the monorepo.

`make lint` and `python scripts/dev.py lint` run exactly the same command, so the
project is usable on Windows (where GNU make is usually absent) and in CI
without duplicating the task definitions.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINT_TARGETS = ("src", "projects", "tests", "mock_ros2", "scripts")
TEST_TARGETS = ("tests", "projects")
PROJECTS_DIR = ROOT / "projects"

PROJECTS: dict[str, str] = {
    "robot-dispatch": "task dispatch service (FastAPI, RabbitMQ, outbox)",
    "telemetry-hub": "MQTT telemetry ingest with dedup and aggregates",
    "ros2-bridge": "ROS2 topics <-> backend bridge with command dedup",
    "grpc-fleet-api": "gRPC fleet control plane with interceptors",
    "fleet-monitor": "alert rules, lifecycle and Prometheus metrics",
    "wms-integration": "resilient WMS client, order sync, signed webhooks",
}


def run(command: Sequence[str], *, check: bool = True) -> int:
    printable = " ".join(str(part) for part in command)
    print(f"+ {printable}", flush=True)
    code = subprocess.call(list(command), cwd=ROOT)
    if check and code != 0:
        print(f"! command failed with exit code {code}", file=sys.stderr)
    return code


def python(*args: str) -> list[str]:
    return [sys.executable, *args]


def require(tool: str) -> bool:
    if shutil.which(tool) is None:
        print(f"! {tool} is not installed or not on PATH", file=sys.stderr)
        return False
    return True


# --------------------------------------------------------------------- commands


def cmd_help(_args: argparse.Namespace) -> int:
    print(
        """usage: python scripts/dev.py <command>

  install      install the package with dev extras into the current interpreter
  lint         ruff check across every package
  format       ruff format + autofix
  typecheck    mypy
  test [path]  pytest (all projects by default, or the given paths)
  check        lint + typecheck + test
  proto        regenerate gRPC stubs from projects/grpc-fleet-api/proto
  docs         regenerate the scenario GIF and validate the SVG diagrams
  game-gif     re-render docs/game/gameplay.gif with headless Chrome/Edge
  projects     list the projects in this repository
  up / down    docker compose stack for robot-dispatch
  logs         follow api/dispatcher/consumer logs
  migrate      run alembic migrations inside the stack
  sim          run the mock ROS2 fleet locally
"""
    )
    return 0


def cmd_install(_args: argparse.Namespace) -> int:
    return run(python("-m", "pip", "install", "-e", ".[dev]"))


def cmd_lint(_args: argparse.Namespace) -> int:
    return run(python("-m", "ruff", "check", *LINT_TARGETS))


def cmd_format(_args: argparse.Namespace) -> int:
    code = run(python("-m", "ruff", "check", "--fix", *LINT_TARGETS))
    if code != 0:
        return code
    return run(python("-m", "ruff", "format", *LINT_TARGETS))


def cmd_typecheck(_args: argparse.Namespace) -> int:
    return run(python("-m", "mypy"))


def cmd_test(args: argparse.Namespace) -> int:
    targets = list(args.paths or TEST_TARGETS)
    return run(python("-m", "pytest", "-q", *targets))


def cmd_check(_args: argparse.Namespace) -> int:
    for step in (cmd_lint, cmd_typecheck):
        code = step(_args)
        if code != 0:
            return code
    return cmd_test(argparse.Namespace(paths=None))


def cmd_proto(_args: argparse.Namespace) -> int:
    project = PROJECTS_DIR / "grpc-fleet-api"
    output = project / "src" / "grpc_fleet_api"
    protoc = python(
        "-m",
        "grpc_tools.protoc",
        f"-I{project / 'proto'}",
        f"--python_out={output}",
        f"--pyi_out={output}",
        f"--grpc_python_out={output}",
        str(project / "proto" / "fleet.proto"),
    )
    code = run(protoc)
    if code != 0:
        return code

    stubs = output / "fleet_pb2_grpc.py"
    text = stubs.read_text(encoding="utf-8")
    patched = text.replace(
        "import fleet_pb2 as fleet__pb2",
        "from grpc_fleet_api import fleet_pb2 as fleet__pb2",
    )
    if patched != text:
        stubs.write_text(patched, encoding="utf-8")
        print(f"  patched import in {stubs.relative_to(ROOT)}")
    return 0


def cmd_docs(_args: argparse.Namespace) -> int:
    code = run(python(str(ROOT / "scripts" / "make_animation.py")))
    if code != 0:
        return code
    return _validate_diagrams()


def cmd_game_gif(_args: argparse.Namespace) -> int:
    return run(python(str(ROOT / "scripts" / "make_game_gif.py")))


def _validate_diagrams() -> int:
    import xml.etree.ElementTree as ElementTree

    diagrams = sorted((ROOT / "docs" / "diagrams").glob("*.svg"))
    for path in diagrams:
        try:
            ElementTree.parse(path)
        except ElementTree.ParseError as exc:
            print(f"! {path.relative_to(ROOT)} is not valid xml: {exc}", file=sys.stderr)
            return 1
        print(f"  ok {path.relative_to(ROOT)}")
    gif = ROOT / "docs" / "animation" / "dispatch-flow.gif"
    if not gif.exists():
        print(f"! {gif.relative_to(ROOT)} is missing", file=sys.stderr)
        return 1
    print(f"  ok {gif.relative_to(ROOT)} ({gif.stat().st_size / 1024:.0f} KB)")
    return 0


def cmd_projects(_args: argparse.Namespace) -> int:
    width = max(len(name) for name in PROJECTS)
    for name, description in PROJECTS.items():
        has_tests = (PROJECTS_DIR / name / "tests").exists()
        marker = "tests" if has_tests else "     "
        print(f"{name:<{width}}  [{marker}]  {description}")
    return 0


def _compose(*args: str) -> int:
    if not require("docker"):
        return 127
    return run(["docker", "compose", *args])


def cmd_up(_args: argparse.Namespace) -> int:
    return _compose("up", "-d", "--build")


def cmd_down(_args: argparse.Namespace) -> int:
    return _compose("down", "-v")


def cmd_logs(_args: argparse.Namespace) -> int:
    return _compose("logs", "-f", "api", "dispatcher", "consumer")


def cmd_migrate(_args: argparse.Namespace) -> int:
    return _compose("run", "--rm", "migrate")


def cmd_sim(_args: argparse.Namespace) -> int:
    return run(
        python(
            "-m",
            "mock_ros2.robot_sim",
            "--count",
            "2",
            "--work-seconds",
            "6",
            "--failure-rate",
            "0.2",
        )
    )


# ------------------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monorepo task runner", add_help=False)
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("help", add_help=False).set_defaults(func=cmd_help)
    subparsers.add_parser("install", add_help=False).set_defaults(func=cmd_install)
    subparsers.add_parser("lint", add_help=False).set_defaults(func=cmd_lint)
    subparsers.add_parser("format", add_help=False).set_defaults(func=cmd_format)
    subparsers.add_parser("typecheck", add_help=False).set_defaults(func=cmd_typecheck)
    subparsers.add_parser("check", add_help=False).set_defaults(func=cmd_check)
    subparsers.add_parser("proto", add_help=False).set_defaults(func=cmd_proto)
    subparsers.add_parser("docs", add_help=False).set_defaults(func=cmd_docs)
    subparsers.add_parser("game-gif", add_help=False).set_defaults(func=cmd_game_gif)
    subparsers.add_parser("projects", add_help=False).set_defaults(func=cmd_projects)
    subparsers.add_parser("up", add_help=False).set_defaults(func=cmd_up)
    subparsers.add_parser("down", add_help=False).set_defaults(func=cmd_down)
    subparsers.add_parser("logs", add_help=False).set_defaults(func=cmd_logs)
    subparsers.add_parser("migrate", add_help=False).set_defaults(func=cmd_migrate)
    subparsers.add_parser("sim", add_help=False).set_defaults(func=cmd_sim)

    test_parser = subparsers.add_parser("test", add_help=False)
    test_parser.add_argument("paths", nargs="*")
    test_parser.set_defaults(func=cmd_test)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        return cmd_help(args)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
