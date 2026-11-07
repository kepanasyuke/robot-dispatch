import type {
  CreateTaskInput,
  Health,
  Robot,
  Stats,
  Task,
  TaskEvent,
  TaskFilters,
  TaskList,
} from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export interface ApiClientOptions {
  baseUrl: string;
  fetchImpl?: FetchLike;
  apiKey?: string;
}

export interface PageParams {
  limit?: number;
  offset?: number;
}

function describeDetail(detail: unknown): string | null {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (item && typeof item === "object") {
          const entry = item as { msg?: unknown; loc?: unknown };
          const location = Array.isArray(entry.loc) ? entry.loc.join(".") : "";
          const message = typeof entry.msg === "string" ? entry.msg : "";
          return location ? `${location}: ${message}` : message;
        }
        return "";
      })
      .filter(Boolean);
    return parts.length > 0 ? parts.join("; ") : null;
  }
  if (detail && typeof detail === "object") {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string") {
      return message;
    }
  }
  return null;
}

export function buildQuery(params: Record<string, string | number | boolean | undefined | null | string[]>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") {
      continue;
    }
    if (Array.isArray(value)) {
      for (const item of value) {
        search.append(key, item);
      }
      continue;
    }
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

export function createApiClient(options: ApiClientOptions) {
  const baseUrl = options.baseUrl.replace(/\/+$/, "");
  const fetchImpl: FetchLike = options.fetchImpl ?? ((input, init) => fetch(input, init));

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    if (init.body !== undefined) {
      headers.set("Content-Type", "application/json");
    }
    if (options.apiKey) {
      headers.set("X-API-Key", options.apiKey);
    }

    let response: Response;
    try {
      response = await fetchImpl(`${baseUrl}${path}`, { ...init, headers });
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      throw new ApiError(0, `Сервис недоступен: ${reason}`);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    const raw = await response.text();
    let parsed: unknown = null;
    if (raw) {
      try {
        parsed = JSON.parse(raw);
      } catch {
        parsed = raw;
      }
    }

    if (!response.ok) {
      const detail =
        parsed && typeof parsed === "object" ? (parsed as { detail?: unknown }).detail : undefined;
      const message = describeDetail(detail) ?? `Ошибка ${response.status}`;
      throw new ApiError(response.status, message, detail);
    }

    return parsed as T;
  }

  return {
    baseUrl,
    getTasks(filters: TaskFilters = {}, page: PageParams = {}): Promise<TaskList> {
      const query = buildQuery({
        status: filters.statuses ?? [],
        type: filters.type,
        robot_id: filters.robotId,
        limit: page.limit,
        offset: page.offset,
      });
      return request<TaskList>(`/tasks${query}`);
    },
    getTask(taskId: string): Promise<Task> {
      return request<Task>(`/tasks/${encodeURIComponent(taskId)}`);
    },
    async getTaskEvents(taskId: string): Promise<TaskEvent[]> {
      const response = await request<TaskEvent[] | { items?: TaskEvent[] }>(
        `/tasks/${encodeURIComponent(taskId)}/events`,
      );
      return Array.isArray(response) ? response : (response.items ?? []);
    },
    cancelTask(taskId: string): Promise<Task> {
      return request<Task>(`/tasks/${encodeURIComponent(taskId)}/cancel`, { method: "POST" });
    },
    createTask(input: CreateTaskInput, idempotencyKey?: string): Promise<Task> {
      const headers: Record<string, string> = {};
      if (idempotencyKey) {
        headers["Idempotency-Key"] = idempotencyKey;
      }
      return request<Task>("/tasks", {
        method: "POST",
        headers,
        body: JSON.stringify(input),
      });
    },
    async getRobots(): Promise<Robot[]> {
      const response = await request<{ items: Robot[] }>("/robots");
      return response.items;
    },
    getStats(): Promise<Stats> {
      return request<Stats>("/stats");
    },
    getHealthLive(): Promise<Health> {
      return request<Health>("/health/live");
    },
    getHealthReady(): Promise<Health> {
      return request<Health>("/health/ready");
    },
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
