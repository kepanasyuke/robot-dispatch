export const TASK_STATUSES = [
  "pending",
  "assigned",
  "running",
  "retrying",
  "succeeded",
  "failed",
  "cancelled",
] as const;

export type TaskStatus = (typeof TASK_STATUSES)[number];

export const ROBOT_STATUSES = ["idle", "busy", "offline"] as const;

export type RobotStatus = (typeof ROBOT_STATUSES)[number];

export interface Task {
  id: string;
  type: string;
  status: TaskStatus;
  priority: number;
  payload: Record<string, unknown>;
  external_id: string | null;
  robot_id: string | null;
  command_id: string | null;
  attempts: number;
  max_attempts: number;
  timeout_seconds: number;
  available_at: string;
  lease_expires_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  last_error: string | null;
  result: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  version: number;
}

export interface TaskList {
  items: Task[];
  limit: number;
  offset: number;
}

export interface TaskEvent {
  id: string;
  task_id: string;
  kind: string;
  from_status: string | null;
  to_status: string | null;
  robot_id: string | null;
  message: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface Robot {
  id: string;
  name: string;
  namespace: string;
  status: RobotStatus;
  capabilities: string[];
  last_seen_at: string | null;
  current_task_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Stats {
  tasks: Record<string, number>;
  task_total: number;
  robots: Record<string, number>;
  queues: Record<string, number | null>;
}

export interface Health {
  status: string;
  checks: Record<string, string>;
}

export interface TaskFilters {
  statuses?: TaskStatus[];
  type?: string;
  robotId?: string;
  query?: string;
}

export interface CreateTaskInput {
  type: string;
  payload?: Record<string, unknown>;
  priority?: number;
  max_attempts?: number;
  timeout_seconds?: number;
}
