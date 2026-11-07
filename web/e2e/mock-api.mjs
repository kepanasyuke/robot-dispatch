import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { randomUUID } from "node:crypto";

const here = dirname(fileURLToPath(import.meta.url));
const fixtures = JSON.parse(readFileSync(join(here, "fixtures.json"), "utf8"));

const PORT = Number(process.env.MOCK_API_PORT ?? 8787);
const API = "/api/v1";

const state = {
  robots: fixtures.robots.map((robot) => ({ ...robot })),
  tasks: fixtures.tasks.map((task) => ({ ...task })),
  events: Object.fromEntries(
    Object.entries(fixtures.events).map(([taskId, list]) => [taskId, list.map((event) => ({ ...event }))]),
  ),
  counter: 100,
};

function resetState() {
  state.robots = fixtures.robots.map((robot) => ({ ...robot }));
  state.tasks = fixtures.tasks.map((task) => ({ ...task }));
  state.events = Object.fromEntries(
    Object.entries(fixtures.events).map(([taskId, list]) => [taskId, list.map((event) => ({ ...event }))]),
  );
  state.counter = 100;
}

function json(response, status, payload) {
  const body = JSON.stringify(payload);
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type, X-API-Key, Idempotency-Key",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Content-Length": Buffer.byteLength(body),
  });
  response.end(body);
}

function notFound(response, detail) {
  json(response, 404, { detail });
}

function findTask(id) {
  return state.tasks.find((task) => task.id === id);
}

function eventsFor(id) {
  if (!state.events[id]) {
    state.events[id] = [];
  }
  return state.events[id];
}

function recordEvent(task, kind, fromStatus, toStatus, message) {
  const event = {
    id: randomUUID(),
    task_id: task.id,
    kind,
    from_status: fromStatus,
    to_status: toStatus,
    robot_id: task.robot_id,
    message,
    payload: {},
    created_at: new Date().toISOString(),
  };
  eventsFor(task.id).push(event);
  return event;
}

function listTasks(url, response) {
  const statuses = url.searchParams.getAll("status");
  const type = url.searchParams.get("type");
  const robotId = url.searchParams.get("robot_id");
  const limit = Number(url.searchParams.get("limit") ?? 50);
  const offset = Number(url.searchParams.get("offset") ?? 0);

  let items = state.tasks.filter((task) => {
    if (statuses.length > 0 && !statuses.includes(task.status)) return false;
    if (type && task.type !== type) return false;
    if (robotId && task.robot_id !== robotId) return false;
    return true;
  });
  items = items.sort((left, right) => right.created_at.localeCompare(left.created_at));

  json(response, 200, { items: items.slice(offset, offset + limit), limit, offset });
}

function createTask(body, idempotencyKey, response) {
  const externalId = body.external_id ?? idempotencyKey ?? null;
  if (externalId) {
    const existing = state.tasks.find((task) => task.external_id === externalId);
    if (existing) {
      return json(response, 200, existing);
    }
  }
  if (typeof body.type !== "string" || body.type.trim() === "") {
    return json(response, 422, { detail: [{ loc: ["body", "type"], msg: "Field required" }] });
  }

  const now = new Date().toISOString();
  state.counter += 1;
  const task = {
    id: randomUUID(),
    type: body.type.trim().toLowerCase(),
    status: "pending",
    priority: body.priority ?? 100,
    payload: body.payload ?? {},
    external_id: externalId,
    robot_id: null,
    command_id: null,
    attempts: 0,
    max_attempts: body.max_attempts ?? 3,
    timeout_seconds: body.timeout_seconds ?? 120,
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
  state.tasks.push(task);
  recordEvent(task, "created", null, "pending", `task ${task.type} queued`);
  json(response, 201, task);
}

function cancelTask(id, response) {
  const task = findTask(id);
  if (!task) {
    return notFound(response, `task ${id} not found`);
  }
  if (["succeeded", "failed", "cancelled"].includes(task.status)) {
    return json(response, 409, {
      detail: "task already finished",
      status: task.status,
      task_id: task.id,
    });
  }
  if (task.status === "running") {
    return json(response, 409, {
      detail: "running tasks cannot be cancelled from the API: the robot owns the execution",
      status: task.status,
      task_id: task.id,
    });
  }
  const previous = task.status;
  task.status = "cancelled";
  task.finished_at = new Date().toISOString();
  task.updated_at = task.finished_at;
  task.version += 1;
  recordEvent(task, "cancelled", previous, "cancelled", "cancelled by API request");
  json(response, 200, task);
}

function stats(response) {
  const tasks = {};
  for (const task of state.tasks) {
    tasks[task.status] = (tasks[task.status] ?? 0) + 1;
  }
  const robots = {};
  for (const robot of state.robots) {
    robots[robot.status] = (robots[robot.status] ?? 0) + 1;
  }
  json(response, 200, {
    tasks,
    task_total: state.tasks.length,
    robots,
    queues: { "dispatch.tasks": state.tasks.filter((task) => task.status === "pending").length },
  });
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", `http://127.0.0.1:${PORT}`);
  const path = url.pathname;

  if (request.method === "OPTIONS") {
    response.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "Content-Type, X-API-Key, Idempotency-Key",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    });
    return response.end();
  }

  if (path === "/healthz") {
    return json(response, 200, { status: "ok" });
  }

  if (path === "/__reset" && request.method === "POST") {
    resetState();
    return json(response, 200, { status: "reset" });
  }

  if (path === `${API}/health/live`) {
    return json(response, 200, { status: "ok", checks: {} });
  }

  if (path === `${API}/health/ready`) {
    return json(response, 200, {
      status: "ok",
      checks: { database: "ok", rabbitmq: "ok" },
    });
  }

  if (path === `${API}/tasks` && request.method === "GET") {
    return listTasks(url, response);
  }

  if (path === `${API}/tasks` && request.method === "POST") {
    const chunks = [];
    for await (const chunk of request) {
      chunks.push(chunk);
    }
    let body = {};
    try {
      body = chunks.length > 0 ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : {};
    } catch {
      return json(response, 400, { detail: "invalid JSON body" });
    }
    return createTask(body, request.headers["idempotency-key"], response);
  }

  const eventsMatch = path.match(new RegExp(`^${API}/tasks/([^/]+)/events$`));
  if (eventsMatch && request.method === "GET") {
    const id = eventsMatch[1];
    if (!findTask(id)) {
      return notFound(response, `task ${id} not found`);
    }
    return json(response, 200, eventsFor(id));
  }

  const cancelMatch = path.match(new RegExp(`^${API}/tasks/([^/]+)/cancel$`));
  if (cancelMatch && request.method === "POST") {
    return cancelTask(cancelMatch[1], response);
  }

  const taskMatch = path.match(new RegExp(`^${API}/tasks/([^/]+)$`));
  if (taskMatch && request.method === "GET") {
    const task = findTask(taskMatch[1]);
    return task ? json(response, 200, task) : notFound(response, `task ${taskMatch[1]} not found`);
  }

  if (path === `${API}/robots` && request.method === "GET") {
    return json(response, 200, { items: state.robots });
  }

  const robotMatch = path.match(new RegExp(`^${API}/robots/([^/]+)$`));
  if (robotMatch && request.method === "GET") {
    const robot = state.robots.find((item) => item.id === robotMatch[1]);
    return robot ? json(response, 200, robot) : notFound(response, `robot ${robotMatch[1]} not found`);
  }

  if (path === `${API}/stats` && request.method === "GET") {
    return stats(response);
  }

  return notFound(response, `route ${path} not found`);
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`mock api on http://127.0.0.1:${PORT}${API}`);
});
