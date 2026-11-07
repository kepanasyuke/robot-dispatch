import type { ApiClient } from "../api/client";
import { ApiError } from "../api/client";
import type { CreateTaskInput, Robot, Task, TaskEvent } from "../api/types";

const NOW = Date.now();

function iso(offsetSeconds: number): string {
  return new Date(NOW + offsetSeconds * 1000).toISOString();
}

function seedTasks(): Task[] {
  return [
    {
      id: "demo-running-0001",
      type: "delivery",
      status: "running",
      priority: 200,
      payload: { from: "A-12", to: "B-04", weight_kg: 12 },
      external_id: "wms-1001",
      robot_id: "demo-robot-0001",
      command_id: "demo-command-0001",
      attempts: 1,
      max_attempts: 3,
      timeout_seconds: 120,
      available_at: iso(-600),
      lease_expires_at: iso(300),
      started_at: iso(-480),
      finished_at: null,
      last_error: null,
      result: null,
      created_at: iso(-600),
      updated_at: iso(-480),
      version: 3,
    },
    {
      id: "demo-pending-0002",
      type: "delivery",
      status: "pending",
      priority: 150,
      payload: { from: "A-01", to: "C-07" },
      external_id: null,
      robot_id: null,
      command_id: null,
      attempts: 0,
      max_attempts: 3,
      timeout_seconds: 120,
      available_at: iso(-120),
      lease_expires_at: null,
      started_at: null,
      finished_at: null,
      last_error: null,
      result: null,
      created_at: iso(-120),
      updated_at: iso(-120),
      version: 1,
    },
    {
      id: "demo-retrying-0003",
      type: "inventory",
      status: "retrying",
      priority: 90,
      payload: { zone: "D" },
      external_id: null,
      robot_id: null,
      command_id: null,
      attempts: 2,
      max_attempts: 3,
      timeout_seconds: 90,
      available_at: iso(-30),
      lease_expires_at: null,
      started_at: iso(-400),
      finished_at: null,
      last_error: "lease expired: robot did not report progress",
      result: null,
      created_at: iso(-900),
      updated_at: iso(-60),
      version: 4,
    },
    {
      id: "demo-succeeded-0004",
      type: "delivery",
      status: "succeeded",
      priority: 100,
      payload: { from: "B-02", to: "B-11" },
      external_id: "wms-0998",
      robot_id: "demo-robot-0002",
      command_id: "demo-command-0004",
      attempts: 1,
      max_attempts: 3,
      timeout_seconds: 120,
      available_at: iso(-3000),
      lease_expires_at: null,
      started_at: iso(-2900),
      finished_at: iso(-2500),
      last_error: null,
      result: { delivered: true },
      created_at: iso(-3000),
      updated_at: iso(-2500),
      version: 5,
    },
    {
      id: "demo-failed-0005",
      type: "inventory",
      status: "failed",
      priority: 80,
      payload: { zone: "A" },
      external_id: null,
      robot_id: "demo-robot-0003",
      command_id: "demo-command-0005",
      attempts: 3,
      max_attempts: 3,
      timeout_seconds: 90,
      available_at: iso(-5000),
      lease_expires_at: null,
      started_at: iso(-4900),
      finished_at: iso(-4500),
      last_error: "robot reported failure: battery critical",
      result: null,
      created_at: iso(-5100),
      updated_at: iso(-4500),
      version: 7,
    },
  ];
}

function seedEvents(): TaskEvent[] {
  const base = (id: string, taskId: string) => ({
    id,
    task_id: taskId,
    from_status: null,
    to_status: null,
    robot_id: null,
    message: null,
    payload: {},
    created_at: iso(-600),
  });
  return [
    {
      ...base("demo-event-0001", "demo-running-0001"),
      kind: "created",
      to_status: "pending",
      message: "task delivery queued",
      created_at: iso(-600),
    },
    {
      ...base("demo-event-0002", "demo-running-0001"),
      kind: "assigned",
      from_status: "pending",
      to_status: "assigned",
      robot_id: "demo-robot-0001",
      message: "assigned to robot-1",
      created_at: iso(-540),
    },
    {
      ...base("demo-event-0003", "demo-running-0001"),
      kind: "progress",
      from_status: "assigned",
      to_status: "running",
      robot_id: "demo-robot-0001",
      message: "robot reached aisle B",
      created_at: iso(-480),
    },
    {
      ...base("demo-event-0004", "demo-retrying-0003"),
      kind: "lease_expired",
      from_status: "running",
      to_status: "retrying",
      message: "retry in 30.0s",
      created_at: iso(-400),
    },
  ];
}

function seedRobots(): Robot[] {
  return [
    {
      id: "demo-robot-0001",
      name: "robot-1",
      namespace: "/robot1",
      status: "busy",
      capabilities: ["delivery", "inspection"],
      last_seen_at: iso(-15),
      current_task_id: "demo-running-0001",
      created_at: iso(-86_400 * 30),
      updated_at: iso(-15),
    },
    {
      id: "demo-robot-0002",
      name: "robot-2",
      namespace: "/robot2",
      status: "idle",
      capabilities: ["delivery"],
      last_seen_at: iso(-5),
      current_task_id: null,
      created_at: iso(-86_400 * 20),
      updated_at: iso(-5),
    },
    {
      id: "demo-robot-0003",
      name: "robot-3",
      namespace: "/robot3",
      status: "offline",
      capabilities: ["delivery", "heavy-lift"],
      last_seen_at: iso(-7200),
      current_task_id: null,
      created_at: iso(-86_400 * 40),
      updated_at: iso(-7000),
    },
  ];
}

export function createDemoClient(): ApiClient {
  let tasks = seedTasks();
  let events = seedEvents();
  const robots = seedRobots();
  let counter = 0;

  function event(task: Task, kind: string, toStatus: string, message: string): TaskEvent {
    counter += 1;
    return {
      id: `demo-event-new-${counter}`,
      task_id: task.id,
      kind,
      from_status: task.status,
      to_status: toStatus,
      robot_id: task.robot_id,
      message,
      payload: {},
      created_at: new Date().toISOString(),
    };
  }

  const client: ApiClient = {
    baseUrl: "demo://in-memory",
    async getTasks(filters = {}, page = {}) {
      const filtered = tasks.filter((task) => {
        if (filters.statuses?.length && !filters.statuses.includes(task.status)) return false;
        if (filters.type && task.type !== filters.type) return false;
        if (filters.robotId && task.robot_id !== filters.robotId) return false;
        return true;
      });
      const offset = page.offset ?? 0;
      const limit = page.limit ?? 50;
      return { items: filtered.slice(offset, offset + limit), limit, offset };
    },
    async getTask(taskId) {
      const task = tasks.find((item) => item.id === taskId);
      if (!task) {
        throw new ApiError(404, `task ${taskId} not found`);
      }
      return task;
    },
    async getTaskEvents(taskId) {
      return events.filter((event) => event.task_id === taskId);
    },
    async cancelTask(taskId) {
      const task = tasks.find((item) => item.id === taskId);
      if (!task) {
        throw new ApiError(404, `task ${taskId} not found`);
      }
      if (["succeeded", "failed", "cancelled"].includes(task.status)) {
        throw new ApiError(409, "task already finished");
      }
      if (task.status === "running") {
        throw new ApiError(
          409,
          "running tasks cannot be cancelled from the API: the robot owns the execution",
        );
      }
      task.status = "cancelled";
      task.finished_at = new Date().toISOString();
      task.updated_at = task.finished_at;
      task.version += 1;
      events = [...events, event(task, "cancelled", "cancelled", "cancelled by API request")];
      return task;
    },
    async createTask(input: CreateTaskInput) {
      if (!input.type.trim()) {
        throw new ApiError(422, "body.type: Field required");
      }
      const now = new Date().toISOString();
      const task: Task = {
        id: `demo-new-${++counter}`,
        type: input.type.trim().toLowerCase(),
        status: "pending",
        priority: input.priority ?? 100,
        payload: input.payload ?? {},
        external_id: null,
        robot_id: null,
        command_id: null,
        attempts: 0,
        max_attempts: input.max_attempts ?? 3,
        timeout_seconds: input.timeout_seconds ?? 120,
        available_at: now,
        lease_expires_at: null,
        started_at: null,
        finished_at: null,
        last_error: null,
        result: null,
        created_at: now,
        updated_at: now,
        version: 1,
      };
      tasks = [task, ...tasks];
      events = [...events, event(task, "created", "pending", `task ${task.type} queued`)];
      return task;
    },
    async getRobots() {
      return robots;
    },
    async getStats() {
      const byStatus: Record<string, number> = {};
      for (const task of tasks) {
        byStatus[task.status] = (byStatus[task.status] ?? 0) + 1;
      }
      const byRobot: Record<string, number> = {};
      for (const robot of robots) {
        byRobot[robot.status] = (byRobot[robot.status] ?? 0) + 1;
      }
      return { tasks: byStatus, task_total: tasks.length, robots: byRobot, queues: {} };
    },
    async getHealthLive() {
      return { status: "ok", checks: {} };
    },
    async getHealthReady() {
      return { status: "ok", checks: { database: "ok", rabbitmq: "ok" } };
    },
  };

  return client;
}
