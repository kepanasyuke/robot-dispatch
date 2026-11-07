import type { Task, TaskFilters, TaskStatus } from "../api/types";
import { isTerminalStatus } from "./status";

export type SortKey = "priority" | "created" | "available";
export type SortDirection = "asc" | "desc";

export interface TaskSummary {
  total: number;
  byStatus: Record<string, number>;
  active: number;
  terminal: number;
  retries: number;
  withErrors: number;
  averageAttempts: number;
  oldestWaitingSeconds: number;
}

export function matchesFilters(task: Task, filters: TaskFilters): boolean {
  if (filters.statuses && filters.statuses.length > 0 && !filters.statuses.includes(task.status)) {
    return false;
  }
  if (filters.type && task.type !== filters.type) {
    return false;
  }
  if (filters.robotId && task.robot_id !== filters.robotId) {
    return false;
  }
  if (filters.query) {
    const needle = filters.query.trim().toLowerCase();
    if (needle) {
      const haystack = [
        task.id,
        task.type,
        task.external_id ?? "",
        task.robot_id ?? "",
        task.last_error ?? "",
      ]
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(needle)) {
        return false;
      }
    }
  }
  return true;
}

export function filterTasks(tasks: Task[], filters: TaskFilters): Task[] {
  return tasks.filter((task) => matchesFilters(task, filters));
}

function compareStrings(left: string, right: string): number {
  return left.localeCompare(right);
}

export function sortTasks(tasks: Task[], key: SortKey = "created", direction: SortDirection = "desc"): Task[] {
  const factor = direction === "asc" ? 1 : -1;
  return [...tasks].sort((left, right) => {
    if (key === "priority" && left.priority !== right.priority) {
      return (left.priority - right.priority) * factor;
    }
    if (key === "available" && left.available_at !== right.available_at) {
      return compareStrings(left.available_at, right.available_at) * factor;
    }
    return compareStrings(left.created_at, right.created_at) * factor;
  });
}

export function groupByStatus(tasks: Task[]): Record<string, Task[]> {
  const groups: Record<string, Task[]> = {};
  for (const task of tasks) {
    const bucket = groups[task.status] ?? [];
    bucket.push(task);
    groups[task.status] = bucket;
  }
  return groups;
}

export function nextAvailableTask(tasks: Task[], now: Date = new Date()): Task | null {
  const ready = tasks.filter(
    (task) =>
      (task.status === "pending" || task.status === "retrying") &&
      new Date(task.available_at).getTime() <= now.getTime(),
  );
  if (ready.length === 0) {
    return null;
  }
  return (
    sortTasks(ready, "available", "asc").sort((left, right) => right.priority - left.priority)[0] ?? null
  );
}

export function summarizeTasks(tasks: Task[], now: Date = new Date()): TaskSummary {
  const byStatus: Record<string, number> = {};
  let retries = 0;
  let withErrors = 0;
  let attemptsTotal = 0;
  let oldestWaitingSeconds = 0;

  for (const task of tasks) {
    byStatus[task.status] = (byStatus[task.status] ?? 0) + 1;
    if (task.attempts > 1) {
      retries += 1;
    }
    if (task.last_error) {
      withErrors += 1;
    }
    attemptsTotal += task.attempts;
    if (task.status === "pending" || task.status === "retrying") {
      const waiting = Math.max(0, (now.getTime() - new Date(task.available_at).getTime()) / 1000);
      oldestWaitingSeconds = Math.max(oldestWaitingSeconds, waiting);
    }
  }

  const terminal = tasks.filter((task) => isTerminalStatus(task.status)).length;

  return {
    total: tasks.length,
    byStatus,
    active: tasks.length - terminal,
    terminal,
    retries,
    withErrors,
    averageAttempts: tasks.length === 0 ? 0 : Math.round((attemptsTotal / tasks.length) * 100) / 100,
    oldestWaitingSeconds: Math.round(oldestWaitingSeconds),
  };
}

export function distinctTypes(tasks: Task[]): string[] {
  return [...new Set(tasks.map((task) => task.type))].sort();
}

export function statusCount(summary: TaskSummary, status: TaskStatus): number {
  return summary.byStatus[status] ?? 0;
}

export function successRate(tasks: Task[]): number {
  const finished = tasks.filter((task) => task.status === "succeeded" || task.status === "failed");
  if (finished.length === 0) {
    return 0;
  }
  const succeeded = finished.filter((task) => task.status === "succeeded").length;
  return Math.round((succeeded / finished.length) * 1000) / 10;
}
