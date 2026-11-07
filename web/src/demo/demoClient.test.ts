import { describe, expect, it } from "vitest";
import { createDemoClient } from "./demoClient";
import { ApiError } from "../api/client";

describe("demoClient", () => {
  it("отдаёт задачи, роботов и статистику", async () => {
    const api = createDemoClient();

    const tasks = await api.getTasks();
    const robots = await api.getRobots();
    const stats = await api.getStats();

    expect(tasks.items.length).toBeGreaterThan(3);
    expect(robots.length).toBe(3);
    expect(stats.task_total).toBe(tasks.items.length);
    expect(stats.tasks.running).toBe(1);
  });

  it("фильтрует по статусу и типу", async () => {
    const api = createDemoClient();

    const running = await api.getTasks({ statuses: ["running"] });
    const inventory = await api.getTasks({ type: "inventory" });

    expect(running.items).toHaveLength(1);
    expect(inventory.items.every((task) => task.type === "inventory")).toBe(true);
  });

  it("пагинирует", async () => {
    const api = createDemoClient();

    const page = await api.getTasks({}, { limit: 2, offset: 1 });

    expect(page.items).toHaveLength(2);
    expect(page.offset).toBe(1);
  });

  it("отдаёт задачу по id и 404 для неизвестной", async () => {
    const api = createDemoClient();
    const task = (await api.getTasks()).items[0];

    await expect(api.getTask(task!.id)).resolves.toMatchObject({ id: task!.id });
    await expect(api.getTask("nope")).rejects.toBeInstanceOf(ApiError);
  });

  it("отдаёт историю событий", async () => {
    const api = createDemoClient();
    const events = await api.getTaskEvents("demo-running-0001");
    expect(events.map((event) => event.kind)).toEqual(["created", "assigned", "progress"]);
  });

  it("создаёт задачу и добавляет событие", async () => {
    const api = createDemoClient();

    const created = await api.createTask({ type: " Patrol ", priority: 55 }, "demo-key");

    expect(created.type).toBe("patrol");
    expect(created.status).toBe("pending");
    expect(created.priority).toBe(55);
    const events = await api.getTaskEvents(created.id);
    expect(events[0]?.kind).toBe("created");
    const list = await api.getTasks();
    expect(list.items[0]?.id).toBe(created.id);
  });

  it("отклоняет задачу без типа", async () => {
    const api = createDemoClient();
    await expect(api.createTask({ type: "  " })).rejects.toMatchObject({ status: 422 });
  });

  it("отменяет задачу из очереди", async () => {
    const api = createDemoClient();

    const cancelled = await api.cancelTask("demo-pending-0002");

    expect(cancelled.status).toBe("cancelled");
    const events = await api.getTaskEvents("demo-pending-0002");
    expect(events.some((event) => event.kind === "cancelled")).toBe(true);
  });

  it("не отменяет выполняющуюся задачу", async () => {
    const api = createDemoClient();
    await expect(api.cancelTask("demo-running-0001")).rejects.toMatchObject({ status: 409 });
  });

  it("не отменяет завершённую задачу", async () => {
    const api = createDemoClient();
    await expect(api.cancelTask("demo-succeeded-0004")).rejects.toMatchObject({ status: 409 });
  });

  it("возвращает 404 при отмене неизвестной задачи", async () => {
    const api = createDemoClient();
    await expect(api.cancelTask("missing")).rejects.toMatchObject({ status: 404 });
  });

  it("сообщает о здоровье", async () => {
    const api = createDemoClient();

    await expect(api.getHealthLive()).resolves.toEqual({ status: "ok", checks: {} });
    await expect(api.getHealthReady()).resolves.toMatchObject({ status: "ok" });
  });

  it("помечает себя как демо-клиент", () => {
    expect(createDemoClient().baseUrl).toBe("demo://in-memory");
  });
});
