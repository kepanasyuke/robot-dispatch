import type { RobotStatus, TaskStatus } from "../api/types";

export type Tone = "neutral" | "info" | "warning" | "success" | "danger";

const TASK_LABELS: Record<TaskStatus, string> = {
  pending: "В очереди",
  assigned: "Назначена",
  running: "Выполняется",
  retrying: "Повтор",
  succeeded: "Успешно",
  failed: "Провалена",
  cancelled: "Отменена",
};

const TASK_TONES: Record<TaskStatus, Tone> = {
  pending: "neutral",
  assigned: "info",
  running: "info",
  retrying: "warning",
  succeeded: "success",
  failed: "danger",
  cancelled: "neutral",
};

const ROBOT_LABELS: Record<RobotStatus, string> = {
  idle: "Свободен",
  busy: "Занят",
  offline: "Не в сети",
};

const ROBOT_TONES: Record<RobotStatus, Tone> = {
  idle: "success",
  busy: "info",
  offline: "danger",
};

export const TERMINAL_STATUSES: readonly TaskStatus[] = ["succeeded", "failed", "cancelled"];

export function taskStatusLabel(status: string): string {
  return TASK_LABELS[status as TaskStatus] ?? status;
}

export function taskStatusTone(status: string): Tone {
  return TASK_TONES[status as TaskStatus] ?? "neutral";
}

export function robotStatusLabel(status: string): string {
  return ROBOT_LABELS[status as RobotStatus] ?? status;
}

export function robotStatusTone(status: string): Tone {
  return ROBOT_TONES[status as RobotStatus] ?? "neutral";
}

export function isTerminalStatus(status: string): boolean {
  return TERMINAL_STATUSES.includes(status as TaskStatus);
}

export function isActiveStatus(status: string): boolean {
  return ["assigned", "running", "retrying"].includes(status);
}
