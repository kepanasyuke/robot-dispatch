import { describe, expect, it } from "vitest";
import { makeTask } from "../test/fixtures";
import {
  distinctTypes,
  filterTasks,
  groupByStatus,
  matchesFilters,
  nextAvailableTask,
  sortTasks,
  statusCount,
  successRate,
  summarizeTasks,
} from "./tasks";

const now = new Date("2026-11-07T12:00:00+00:00");

describe("matchesFilters", () => {
  it("пропускает задачу без фильтров", () => {
    expect(matchesFilters(makeTask(), {})).toBe(true);
  });

  it.each([
    ["pending", true],
    ["failed", false],
  ])("фильтрует по статусу %s", (status, expected) => {
    const task = makeTask({ status: "pending" });
    expect(matchesFilters(task, { statuses: [status as never] })).toBe(expected);
  });

  it("принимает несколько статусов", () => {
    const task = makeTask({ status: "retrying" });
    expect(matchesFilters(task, { statuses: ["pending", "retrying"] })).toBe(true);
  });

  it("сравнивает тип точно", () => {
    const task = makeTask({ type: "delivery" });
    expect(matchesFilters(task, { type: "delivery" })).toBe(true);
    expect(matchesFilters(task, { type: "deliv" })).toBe(false);
  });

  it("сравнивает робота", () => {
    const task = makeTask({ robot_id: "robot-1" });
    expect(matchesFilters(task, { robotId: "robot-1" })).toBe(true);
    expect(matchesFilters(task, { robotId: "robot-2" })).toBe(false);
  });

  it.each([
    ["DELIVERY", true],
    ["11111111", true],
    ["wms-1001", true],
    ["battery", true],
    ["robot-7", false],
  ])("ищет по подстроке «%s»", (query, expected) => {
    const task = makeTask({
      external_id: "wms-1001",
      last_error: "battery critical",
      robot_id: "robot-9-search",
    });
    const result = matchesFilters({ ...task, robot_id: "robot-9-search" }, { query });
    expect(result).toBe(expected);
  });

  it("игнорирует пустой поисковый запрос", () => {
    expect(matchesFilters(makeTask(), { query: "   " })).toBe(true);
  });
});

describe("filterTasks", () => {
  it("оставляет только подходящие задачи", () => {
    const tasks = [
      makeTask({ id: "a", status: "pending" }),
      makeTask({ id: "b", status: "failed" }),
      makeTask({ id: "c", status: "pending" }),
    ];

    const filtered = filterTasks(tasks, { statuses: ["pending"] });

    expect(filtered.map((task) => task.id)).toEqual(["a", "c"]);
  });

  it("не мутирует исходный массив", () => {
    const tasks = [makeTask({ id: "a" })];
    filterTasks(tasks, { statuses: ["failed"] });
    expect(tasks).toHaveLength(1);
  });
});

describe("sortTasks", () => {
  const tasks = [
    makeTask({ id: "low", priority: 10, created_at: "2026-11-07T10:00:00+00:00" }),
    makeTask({ id: "high", priority: 900, created_at: "2026-11-07T09:00:00+00:00" }),
    makeTask({ id: "mid", priority: 100, created_at: "2026-11-07T11:00:00+00:00" }),
  ];

  it("сортирует по приоритету по убыванию", () => {
    expect(sortTasks(tasks, "priority", "desc").map((task) => task.id)).toEqual(["high", "mid", "low"]);
  });

  it("сортирует по приоритету по возрастанию", () => {
    expect(sortTasks(tasks, "priority", "asc").map((task) => task.id)).toEqual(["low", "mid", "high"]);
  });

  it("сортирует по дате создания", () => {
    expect(sortTasks(tasks, "created", "desc").map((task) => task.id)).toEqual(["mid", "low", "high"]);
  });

  it("сортирует по доступности", () => {
    const withAvailability = [
      makeTask({ id: "later", available_at: "2026-11-07T12:00:00+00:00" }),
      makeTask({ id: "earlier", available_at: "2026-11-07T10:00:00+00:00" }),
    ];
    expect(sortTasks(withAvailability, "available", "asc").map((task) => task.id)).toEqual([
      "earlier",
      "later",
    ]);
  });

  it("возвращает новый массив", () => {
    const sorted = sortTasks(tasks, "created", "asc");
    expect(sorted).not.toBe(tasks);
  });
});

describe("groupByStatus", () => {
  it("группирует задачи по статусам", () => {
    const groups = groupByStatus([
      makeTask({ id: "a", status: "pending" }),
      makeTask({ id: "b", status: "pending" }),
      makeTask({ id: "c", status: "failed" }),
    ]);

    expect(groups.pending).toHaveLength(2);
    expect(groups.failed).toHaveLength(1);
    expect(groups.succeeded).toBeUndefined();
  });
});

describe("nextAvailableTask", () => {
  it("выбирает задачу с наибольшим приоритетом среди готовых", () => {
    const tasks = [
      makeTask({ id: "low", priority: 10, available_at: "2026-11-07T10:00:00+00:00" }),
      makeTask({ id: "high", priority: 500, available_at: "2026-11-07T11:00:00+00:00" }),
      makeTask({ id: "running", priority: 999, status: "running" }),
    ];

    expect(nextAvailableTask(tasks, now)?.id).toBe("high");
  });

  it("не берёт задачу, доступную в будущем", () => {
    const tasks = [makeTask({ id: "future", available_at: "2026-11-07T13:00:00+00:00" })];
    expect(nextAvailableTask(tasks, now)).toBeNull();
  });

  it("возвращает null на пустом списке", () => {
    expect(nextAvailableTask([], now)).toBeNull();
  });
});

describe("summarizeTasks", () => {
  it("считает показатели по смешанному набору", () => {
    const tasks = [
      makeTask({ status: "pending", available_at: "2026-11-07T10:00:00+00:00" }),
      makeTask({ status: "retrying", attempts: 2, available_at: "2026-11-07T11:00:00+00:00" }),
      makeTask({ status: "succeeded", attempts: 1 }),
      makeTask({ status: "failed", attempts: 3, last_error: "boom" }),
    ];

    const summary = summarizeTasks(tasks, now);

    expect(summary.total).toBe(4);
    expect(summary.byStatus).toEqual({ pending: 1, retrying: 1, succeeded: 1, failed: 1 });
    expect(summary.terminal).toBe(2);
    expect(summary.active).toBe(2);
    expect(summary.retries).toBe(2);
    expect(summary.withErrors).toBe(1);
    expect(summary.averageAttempts).toBe(1.5);
    expect(summary.oldestWaitingSeconds).toBe(7200);
  });

  it("возвращает нули на пустом списке", () => {
    const summary = summarizeTasks([], now);
    expect(summary.total).toBe(0);
    expect(summary.averageAttempts).toBe(0);
    expect(summary.oldestWaitingSeconds).toBe(0);
  });

  it("не считает отрицательное ожидание", () => {
    const summary = summarizeTasks([makeTask({ available_at: "2026-11-07T15:00:00+00:00" })], now);
    expect(summary.oldestWaitingSeconds).toBe(0);
  });
});

describe("statusCount", () => {
  it("читает счётчик из сводки", () => {
    const summary = summarizeTasks([makeTask({ status: "pending" }), makeTask({ status: "pending" })], now);
    expect(statusCount(summary, "pending")).toBe(2);
    expect(statusCount(summary, "failed")).toBe(0);
  });
});

describe("successRate", () => {
  it("считает долю успешных среди завершённых", () => {
    const tasks = [
      makeTask({ status: "succeeded" }),
      makeTask({ status: "succeeded" }),
      makeTask({ status: "failed" }),
      makeTask({ status: "pending" }),
    ];
    expect(successRate(tasks)).toBe(66.7);
  });

  it("возвращает ноль без завершённых", () => {
    expect(successRate([makeTask({ status: "pending" })])).toBe(0);
  });
});

describe("distinctTypes", () => {
  it("возвращает уникальные типы по алфавиту", () => {
    const tasks = [makeTask({ type: "patrol" }), makeTask({ type: "delivery" }), makeTask({ type: "patrol" })];
    expect(distinctTypes(tasks)).toEqual(["delivery", "patrol"]);
  });
});
