import type { Robot, Task, TaskEvent } from "../api/types";

export function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    type: "delivery",
    status: "pending",
    priority: 100,
    payload: { target: "a" },
    external_id: null,
    robot_id: null,
    command_id: null,
    attempts: 0,
    max_attempts: 3,
    timeout_seconds: 120,
    available_at: "2026-11-07T10:00:00+00:00",
    lease_expires_at: null,
    started_at: null,
    finished_at: null,
    last_error: null,
    result: null,
    created_at: "2026-11-07T10:00:00+00:00",
    updated_at: "2026-11-07T10:00:00+00:00",
    version: 1,
    ...overrides,
  };
}

export function makeEvent(overrides: Partial<TaskEvent> = {}): TaskEvent {
  return {
    id: "eeee0001-0001-4001-8001-000000000001",
    task_id: "11111111-1111-4111-8111-111111111111",
    kind: "created",
    from_status: null,
    to_status: "pending",
    robot_id: null,
    message: "task delivery queued",
    payload: {},
    created_at: "2026-11-07T10:00:00+00:00",
    ...overrides,
  };
}

export function makeRobot(overrides: Partial<Robot> = {}): Robot {
  return {
    id: "22222222-2222-4222-8222-222222222222",
    name: "robot-1",
    namespace: "/robot1",
    status: "idle",
    capabilities: ["delivery"],
    last_seen_at: "2026-11-07T10:00:00+00:00",
    current_task_id: null,
    created_at: "2026-10-01T08:00:00+00:00",
    updated_at: "2026-11-07T10:00:00+00:00",
    ...overrides,
  };
}
