import { describe, expect, it } from "vitest";
import { makeRobot } from "../test/fixtures";
import {
  checksList,
  queueRows,
  robotAvailability,
  staleRobots,
  summarizeHealth,
} from "./health";
import type { Health, Stats } from "../api/types";

function health(status: string, checks: Record<string, string>): Health {
  return { status, checks };
}

describe("checksList", () => {
  it("сортирует проверки по имени", () => {
    const list = checksList(health("ok", { rabbitmq: "ok", database: "ok" }));
    expect(list.map((entry) => entry.name)).toEqual(["database", "rabbitmq"]);
  });

  it("помечает недоступные проверки как проблемные", () => {
    const list = checksList(health("degraded", { database: "ok", rabbitmq: "unavailable" }));
    expect(list.find((entry) => entry.name === "rabbitmq")?.ok).toBe(false);
  });

  it("считает connected успехом", () => {
    const list = checksList(health("ok", { broker: "connected" }));
    expect(list[0]?.ok).toBe(true);
  });

  it("возвращает пустой список без данных", () => {
    expect(checksList(null)).toEqual([]);
  });
});

describe("summarizeHealth", () => {
  it("сообщает об отсутствии данных, если live не ответил", () => {
    const summary = summarizeHealth(null, null);
    expect(summary.state).toBe("unknown");
    expect(summary.detail).toContain("не отвечает");
  });

  it("считает деградацией отсутствие readiness", () => {
    const summary = summarizeHealth(health("ok", {}), null);
    expect(summary.state).toBe("degraded");
  });

  it("считает всё в порядке при ok", () => {
    const summary = summarizeHealth(health("ok", {}), health("ok", { database: "ok" }));
    expect(summary.state).toBe("ok");
    expect(summary.label).toBe("Всё в порядке");
  });

  it("перечисляет проблемные зависимости", () => {
    const summary = summarizeHealth(
      health("ok", {}),
      health("degraded", { database: "ok", rabbitmq: "unavailable" }),
    );
    expect(summary.state).toBe("degraded");
    expect(summary.detail).toContain("rabbitmq");
  });

  it("не перечисляет зависимости при базовой ошибке", () => {
    const summary = summarizeHealth(health("ok", {}), health("degraded", { database: "error: timeout" }));
    expect(summary.detail).toContain("database");
  });
});

describe("queueRows", () => {
  const stats: Stats = {
    tasks: { pending: 6, running: 2, failed: 2 },
    task_total: 10,
    robots: { idle: 1 },
    queues: {},
  };

  it("считает доли статусов", () => {
    const rows = queueRows(stats);
    expect(rows[0]).toEqual({ status: "pending", count: 6, share: 60 });
    expect(rows).toHaveLength(3);
  });

  it("сортирует по количеству", () => {
    const rows = queueRows({ ...stats, tasks: { running: 1, failed: 5, pending: 3 } });
    expect(rows.map((row) => row.status)).toEqual(["failed", "pending", "running"]);
  });

  it("возвращает пустой список без статистики", () => {
    expect(queueRows(null)).toEqual([]);
  });

  it("не делит на ноль", () => {
    const rows = queueRows({ tasks: {}, task_total: 0, robots: {}, queues: {} });
    expect(rows).toEqual([]);
  });
});

describe("robotAvailability", () => {
  it("считает роботов на связи", () => {
    const robots = [
      makeRobot({ status: "idle" }),
      makeRobot({ status: "busy" }),
      makeRobot({ status: "offline" }),
    ];
    expect(robotAvailability(robots)).toEqual({ online: 2, total: 3, percent: 66.7 });
  });

  it("не делит на ноль", () => {
    expect(robotAvailability([])).toEqual({ online: 0, total: 0, percent: 0 });
  });
});

describe("staleRobots", () => {
  const now = new Date("2026-11-07T12:00:00+00:00");

  it("находит роботов без heartbeat", () => {
    const robots = [makeRobot({ last_seen_at: null })];
    expect(staleRobots(robots, now)).toHaveLength(1);
  });

  it("находит роботов с давним heartbeat", () => {
    const robots = [makeRobot({ last_seen_at: "2026-11-07T11:00:00+00:00" })];
    expect(staleRobots(robots, now, 300)).toHaveLength(1);
  });

  it("не считает свежих роботов проблемными", () => {
    const robots = [makeRobot({ last_seen_at: "2026-11-07T11:59:00+00:00" })];
    expect(staleRobots(robots, now, 300)).toHaveLength(0);
  });
});
