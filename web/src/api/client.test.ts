import { describe, expect, it } from "vitest";
import { ApiError, buildQuery, createApiClient, type FetchLike } from "./client";

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

function recordingFetch(response: Response, calls: Array<{ url: string; init?: RequestInit }> = []): FetchLike {
  return async (url, init) => {
    calls.push({ url, init });
    return response;
  };
}

describe("buildQuery", () => {
  it("собирает параметры", () => {
    expect(buildQuery({ type: "delivery", limit: 10 })).toBe("?type=delivery&limit=10");
  });

  it("пропускает пустые значения", () => {
    expect(buildQuery({ type: undefined, robot_id: null, limit: "" })).toBe("");
  });

  it("повторяет массивы", () => {
    expect(buildQuery({ status: ["pending", "retrying"] })).toBe("?status=pending&status=retrying");
  });

  it("кодирует спецсимволы", () => {
    expect(buildQuery({ type: "a b&c" })).toBe("?type=a+b%26c");
  });
});

describe("createApiClient: успешные вызовы", () => {
  it("отдаёт список задач", async () => {
    const client = createApiClient({
      baseUrl: "http://api.test/api/v1/",
      fetchImpl: recordingFetch(jsonResponse({ items: [], limit: 50, offset: 0 })),
    });

    const result = await client.getTasks();

    expect(result).toEqual({ items: [], limit: 50, offset: 0 });
  });

  it("формирует query из фильтров и страницы", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    const client = createApiClient({
      baseUrl: "http://api.test/api/v1",
      fetchImpl: recordingFetch(jsonResponse({ items: [], limit: 5, offset: 10 }), calls),
    });

    await client.getTasks({ statuses: ["pending", "running"], type: "delivery" }, { limit: 5, offset: 10 });

    expect(calls[0]?.url).toBe(
      "http://api.test/api/v1/tasks?status=pending&status=running&type=delivery&limit=5&offset=10",
    );
  });

  it("отдаёт роботов из обёртки items", async () => {
    const client = createApiClient({
      baseUrl: "http://api.test/api/v1",
      fetchImpl: recordingFetch(jsonResponse({ items: [{ id: "r1" }] })),
    });

    await expect(client.getRobots()).resolves.toEqual([{ id: "r1" }]);
  });

  it("нормализует события из обёртки items", async () => {
    const client = createApiClient({
      baseUrl: "http://api.test/api/v1",
      fetchImpl: recordingFetch(jsonResponse({ items: [{ id: "e1" }] })),
    });

    await expect(client.getTaskEvents("t1")).resolves.toEqual([{ id: "e1" }]);
  });

  it("прокидывает X-API-Key", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    const client = createApiClient({
      baseUrl: "http://api.test/api/v1",
      apiKey: "secret",
      fetchImpl: recordingFetch(jsonResponse({}), calls),
    });

    await client.getStats();

    const headers = new Headers(calls[0]?.init?.headers);
    expect(headers.get("X-API-Key")).toBe("secret");
  });

  it("прокидывает Idempotency-Key при создании", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    const client = createApiClient({
      baseUrl: "http://api.test/api/v1",
      fetchImpl: recordingFetch(jsonResponse({ id: "t1" }, 201), calls),
    });

    await client.createTask({ type: "delivery" }, "key-1");

    const headers = new Headers(calls[0]?.init?.headers);
    expect(headers.get("Idempotency-Key")).toBe("key-1");
    expect(calls[0]?.init?.method).toBe("POST");
    expect(calls[0]?.init?.body).toBe('{"type":"delivery"}');
  });

  it("отправляет POST на cancel", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    const client = createApiClient({
      baseUrl: "http://api.test/api/v1",
      fetchImpl: recordingFetch(jsonResponse({ id: "t1", status: "cancelled" }), calls),
    });

    const result = await client.cancelTask("t1");

    expect(calls[0]?.url).toBe("http://api.test/api/v1/tasks/t1/cancel");
    expect(calls[0]?.init?.method).toBe("POST");
    expect(result.status).toBe("cancelled");
  });

  it("кодирует идентификатор в пути", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    const client = createApiClient({
      baseUrl: "http://api.test/api/v1",
      fetchImpl: recordingFetch(jsonResponse({}), calls),
    });

    await client.getTask("a b/c");

    expect(calls[0]?.url).toBe("http://api.test/api/v1/tasks/a%20b%2Fc");
  });

  it("возвращает undefined для 204", async () => {
    const client = createApiClient({
      baseUrl: "http://api.test/api/v1",
      fetchImpl: async () => new Response(null, { status: 204 }),
    });

    await expect(client.getHealthLive()).resolves.toBeUndefined();
  });
});

describe("createApiClient: ошибки", () => {
  it("превращает detail-строку в сообщение", async () => {
    const client = createApiClient({
      baseUrl: "http://api.test/api/v1",
      fetchImpl: recordingFetch(jsonResponse({ detail: "task not found" }, 404)),
    });

    await expect(client.getTask("t1")).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      message: "task not found",
    });
  });

  it("разбирает список ошибок валидации", async () => {
    const client = createApiClient({
      baseUrl: "http://api.test/api/v1",
      fetchImpl: recordingFetch(
        jsonResponse(
          {
            detail: [
              { loc: ["body", "type"], msg: "Field required" },
              { loc: ["body", "priority"], msg: "Input should be >= 0" },
            ],
          },
          422,
        ),
      ),
    });

    await expect(client.createTask({ type: "" })).rejects.toThrow(
      "body.type: Field required; body.priority: Input should be >= 0",
    );
  });

  it("подставляет текст по умолчанию без detail", async () => {
    const client = createApiClient({
      baseUrl: "http://api.test/api/v1",
      fetchImpl: recordingFetch(jsonResponse({}, 500)),
    });

    await expect(client.getStats()).rejects.toMatchObject({ status: 500, message: "Ошибка 500" });
  });

  it("понимает detail как объект с message", async () => {
    const client = createApiClient({
      baseUrl: "http://api.test/api/v1",
      fetchImpl: recordingFetch(jsonResponse({ detail: { message: "boom" } }, 409)),
    });

    await expect(client.cancelTask("t1")).rejects.toMatchObject({ message: "boom" });
  });

  it("оборачивает сетевую ошибку", async () => {
    const client = createApiClient({
      baseUrl: "http://api.test/api/v1",
      fetchImpl: async () => {
        throw new Error("connection refused");
      },
    });

    await expect(client.getTasks()).rejects.toThrow(/Сервис недоступен: connection refused/);
    await expect(client.getTasks()).rejects.toMatchObject({ status: 0 });
  });

  it("не падает на невалидном JSON в ответе об ошибке", async () => {
    const client = createApiClient({
      baseUrl: "http://api.test/api/v1",
      fetchImpl: async () => new Response("<html>gateway</html>", { status: 502 }),
    });

    await expect(client.getStats()).rejects.toMatchObject({ status: 502, message: "Ошибка 502" });
  });

  it("кладёт detail в поле ошибки", async () => {
    const client = createApiClient({
      baseUrl: "http://api.test/api/v1",
      fetchImpl: recordingFetch(jsonResponse({ detail: "conflict" }, 409)),
    });

    await expect(client.cancelTask("t1")).rejects.toSatisfy(
      (error: unknown) => error instanceof ApiError && error.detail === "conflict",
    );
  });
});
