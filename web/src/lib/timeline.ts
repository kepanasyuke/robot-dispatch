import type { TaskEvent } from "../api/types";
import type { Tone } from "./status";

const EVENT_LABELS: Record<string, string> = {
  created: "Задача создана",
  assigned: "Назначена роботу",
  started: "Робот приступил",
  progress: "Прогресс",
  retry_scheduled: "Запланирован повтор",
  lease_expired: "Аренда истекла",
  succeeded: "Выполнена",
  failed: "Провалена",
  cancelled: "Отменена",
  result_ignored: "Результат проигнорирован",
};

const EVENT_TONES: Record<string, Tone> = {
  created: "neutral",
  assigned: "info",
  started: "info",
  progress: "info",
  retry_scheduled: "warning",
  lease_expired: "danger",
  succeeded: "success",
  failed: "danger",
  cancelled: "neutral",
  result_ignored: "warning",
};

export interface TimelineEntry {
  id: string;
  kind: string;
  label: string;
  tone: Tone;
  message: string;
  fromStatus: string | null;
  toStatus: string | null;
  robotId: string | null;
  createdAt: string;
}

export function eventLabel(kind: string): string {
  return EVENT_LABELS[kind] ?? kind;
}

export function eventTone(kind: string): Tone {
  return EVENT_TONES[kind] ?? "neutral";
}

export function buildTimeline(events: TaskEvent[]): TimelineEntry[] {
  return [...events]
    .sort((left, right) => left.created_at.localeCompare(right.created_at))
    .map((event) => ({
      id: event.id,
      kind: event.kind,
      label: eventLabel(event.kind),
      tone: eventTone(event.kind),
      message: event.message ?? "",
      fromStatus: event.from_status,
      toStatus: event.to_status,
      robotId: event.robot_id,
      createdAt: event.created_at,
    }));
}

export function countRetries(events: TaskEvent[]): number {
  return events.filter((event) => event.kind === "retry_scheduled" || event.kind === "lease_expired").length;
}

export function countIgnoredResults(events: TaskEvent[]): number {
  return events.filter((event) => event.kind === "result_ignored").length;
}

export function transitionPath(events: TaskEvent[]): string {
  const path: string[] = [];
  for (const event of buildTimeline(events)) {
    if (event.toStatus && path[path.length - 1] !== event.toStatus) {
      path.push(event.toStatus);
    }
  }
  return path.join(" → ");
}

export function executionSeconds(events: TaskEvent[]): number | null {
  const ordered = buildTimeline(events);
  const start = ordered.find((event) => event.kind === "assigned" || event.kind === "started");
  const finish = [...ordered]
    .reverse()
    .find((event) => event.kind === "succeeded" || event.kind === "failed" || event.kind === "cancelled");
  if (!start || !finish) {
    return null;
  }
  const delta = (new Date(finish.createdAt).getTime() - new Date(start.createdAt).getTime()) / 1000;
  return delta >= 0 ? Math.round(delta) : null;
}
