import { vi } from "vitest";
import type { ApiClient } from "../api/client";
import type { Health, Robot, Stats, Task, TaskEvent } from "../api/types";
import { makeEvent, makeRobot, makeTask } from "./fixtures";

export interface FakeApiOptions {
  tasks?: Task[];
  events?: TaskEvent[];
  robots?: Robot[];
  stats?: Stats;
  live?: Health;
  ready?: Health;
  failTasks?: string;
  failTask?: string;
  failEvents?: string;
  failRobots?: string;
  failHealth?: string;
  failCancel?: string;
}

export function makeStats(tasks: Record<string, number>): Stats {
  return {
    tasks,
    task_total: Object.values(tasks).reduce((sum, value) => sum + value, 0),
    robots: { idle: 1 },
    queues: {},
  };
}

export function makeFakeApi(options: FakeApiOptions = {}) {
  const tasks = options.tasks ?? [makeTask()];
  const robots = options.robots ?? [makeRobot()];

  const client = {
    baseUrl: "http://fake/api/v1",
    getTasks: vi.fn(async (filters: { type?: string } = {}, page: { limit?: number; offset?: number } = {}) => {
      if (options.failTasks) {
        throw new Error(options.failTasks);
      }
      const filtered = filters.type ? tasks.filter((task) => task.type === filters.type) : tasks;
      const offset = page.offset ?? 0;
      const limit = page.limit ?? 200;
      return { items: filtered.slice(offset, offset + limit), limit, offset };
    }),
    getTask: vi.fn(async (id: string) => {
      if (options.failTask) {
        throw new Error(options.failTask);
      }
      const found = tasks.find((task) => task.id === id);
      if (!found) {
        throw new Error(`task ${id} not found`);
      }
      return found;
    }),
    getTaskEvents: vi.fn(async () => {
      if (options.failEvents) {
        throw new Error(options.failEvents);
      }
      return options.events ?? [makeEvent()];
    }),
    cancelTask: vi.fn(async (id: string) => {
      if (options.failCancel) {
        throw new Error(options.failCancel);
      }
      const found = tasks.find((task) => task.id === id) ?? makeTask({ id });
      return { ...found, status: "cancelled" as const };
    }),
    createTask: vi.fn(async () => tasks[0] as Task),
    getRobots: vi.fn(async () => {
      if (options.failRobots) {
        throw new Error(options.failRobots);
      }
      return robots;
    }),
    getStats: vi.fn(async () => options.stats ?? makeStats({ pending: 1, running: 1 })),
    getHealthLive: vi.fn(async () => {
      if (options.failHealth) {
        throw new Error(options.failHealth);
      }
      return options.live ?? { status: "ok", checks: {} };
    }),
    getHealthReady: vi.fn(async () => {
      if (options.failHealth) {
        throw new Error(options.failHealth);
      }
      return options.ready ?? { status: "ok", checks: { database: "ok" } };
    }),
  };

  return client as unknown as ApiClient & { [K in keyof ApiClient]: ReturnType<typeof vi.fn> };
}
