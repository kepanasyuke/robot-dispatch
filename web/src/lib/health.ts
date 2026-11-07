import type { Health, Robot, Stats } from "../api/types";

export type OverallState = "ok" | "degraded" | "down" | "unknown";

export interface HealthSummary {
  state: OverallState;
  label: string;
  detail: string;
}

const STATE_LABELS: Record<OverallState, string> = {
  ok: "Всё в порядке",
  degraded: "Работает с деградацией",
  down: "Недоступно",
  unknown: "Нет данных",
};

export interface CheckEntry {
  name: string;
  status: string;
  ok: boolean;
}

export function checksList(ready: Health | null): CheckEntry[] {
  if (!ready) {
    return [];
  }
  const entries: CheckEntry[] = [];
  for (const [name, value] of Object.entries(ready.checks ?? {})) {
    entries.push({
      name,
      status: value,
      ok: value === "ok" || value === "connected",
    });
  }
  return entries.sort((left, right) => left.name.localeCompare(right.name));
}

export function summarizeHealth(live: Health | null, ready: Health | null): HealthSummary {
  if (!live) {
    return { state: "unknown", label: STATE_LABELS.unknown, detail: "Сервис не отвечает" };
  }
  if (!ready) {
    return {
      state: "degraded",
      label: STATE_LABELS.degraded,
      detail: "Процесс жив, readiness не отвечает",
    };
  }
  if (ready.status === "ok") {
    return { state: "ok", label: STATE_LABELS.ok, detail: "База и брокер доступны" };
  }
  const failing = checksList(ready)
    .filter((entry) => !entry.ok)
    .map((entry) => entry.name);
  return {
    state: "degraded",
    label: STATE_LABELS.degraded,
    detail: failing.length > 0 ? `Проблемы: ${failing.join(", ")}` : "Сервис сообщает о деградации",
  };
}

export interface QueueRow {
  status: string;
  count: number;
  share: number;
}

export function queueRows(stats: Stats | null): QueueRow[] {
  if (!stats) {
    return [];
  }
  const total = stats.task_total || Object.values(stats.tasks ?? {}).reduce((sum, value) => sum + value, 0);
  return Object.entries(stats.tasks ?? {})
    .map(([status, count]) => ({
      status,
      count,
      share: total === 0 ? 0 : Math.round((count / total) * 1000) / 10,
    }))
    .sort((left, right) => right.count - left.count);
}

export function robotAvailability(robots: Robot[]): { online: number; total: number; percent: number } {
  const total = robots.length;
  const online = robots.filter((robot) => robot.status !== "offline").length;
  return { online, total, percent: total === 0 ? 0 : Math.round((online / total) * 1000) / 10 };
}

export function staleRobots(robots: Robot[], now: Date = new Date(), thresholdSeconds = 300): Robot[] {
  return robots.filter((robot) => {
    if (!robot.last_seen_at) {
      return true;
    }
    const seen = new Date(robot.last_seen_at).getTime();
    return (now.getTime() - seen) / 1000 > thresholdSeconds;
  });
}
