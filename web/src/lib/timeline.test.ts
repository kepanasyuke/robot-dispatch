import { describe, expect, it } from "vitest";
import { makeEvent } from "../test/fixtures";
import { buildTimeline, countIgnoredResults, countRetries, eventLabel, eventTone, executionSeconds, transitionPath } from "./timeline";

describe("eventLabel", () => {
  it.each([
    ["created", "Задача создана"],
    ["assigned", "Назначена роботу"],
    ["progress", "Прогресс"],
    ["retry_scheduled", "Запланирован повтор"],
    ["lease_expired", "Аренда истекла"],
    ["succeeded", "Выполнена"],
    ["failed", "Провалена"],
    ["cancelled", "Отменена"],
    ["result_ignored", "Результат проигнорирован"],
  ])("переводит %s", (kind, expected) => {
    expect(eventLabel(kind)).toBe(expected);
  });

  it("возвращает незнакомый вид как есть", () => {
    expect(eventLabel("custom_event")).toBe("custom_event");
  });
});

describe("eventTone", () => {
  it.each([
    ["succeeded", "success"],
    ["failed", "danger"],
    ["lease_expired", "danger"],
    ["retry_scheduled", "warning"],
    ["result_ignored", "warning"],
    ["created", "neutral"],
    ["assigned", "info"],
  ])("даёт тон %s для %s", (kind, expected) => {
    expect(eventTone(kind)).toBe(expected);
  });
});

describe("buildTimeline", () => {
  it("сортирует события по времени", () => {
    const events = [
      makeEvent({ id: "3", kind: "succeeded", created_at: "2026-11-07T10:03:00+00:00" }),
      makeEvent({ id: "1", kind: "created", created_at: "2026-11-07T10:01:00+00:00" }),
      makeEvent({ id: "2", kind: "assigned", created_at: "2026-11-07T10:02:00+00:00" }),
    ];

    expect(buildTimeline(events).map((entry) => entry.id)).toEqual(["1", "2", "3"]);
  });

  it("переносит поля события", () => {
    const entry = buildTimeline([
      makeEvent({
        kind: "progress",
        from_status: "assigned",
        to_status: "running",
        robot_id: "robot-1",
        message: "50 %",
      }),
    ])[0];

    expect(entry?.label).toBe("Прогресс");
    expect(entry?.tone).toBe("info");
    expect(entry?.fromStatus).toBe("assigned");
    expect(entry?.toStatus).toBe("running");
    expect(entry?.robotId).toBe("robot-1");
    expect(entry?.message).toBe("50 %");
  });

  it("подставляет пустую строку вместо отсутствующего сообщения", () => {
    const entry = buildTimeline([makeEvent({ message: null })])[0];
    expect(entry?.message).toBe("");
  });

  it("возвращает пустой список для пустого входа", () => {
    expect(buildTimeline([])).toEqual([]);
  });
});

describe("countRetries", () => {
  it("считает повторы и истёкшие аренды", () => {
    const events = [
      makeEvent({ kind: "created" }),
      makeEvent({ kind: "retry_scheduled" }),
      makeEvent({ kind: "lease_expired" }),
    ];
    expect(countRetries(events)).toBe(2);
  });
});

describe("countIgnoredResults", () => {
  it("считает проигнорированные результаты", () => {
    const events = [
      makeEvent({ kind: "result_ignored" }),
      makeEvent({ kind: "result_ignored" }),
      makeEvent({ kind: "created" }),
    ];
    expect(countIgnoredResults(events)).toBe(2);
  });
});

describe("transitionPath", () => {
  it("склеивает путь переходов", () => {
    const events = [
      makeEvent({ kind: "created", to_status: "pending", created_at: "2026-11-07T10:00:00+00:00" }),
      makeEvent({ kind: "assigned", to_status: "assigned", created_at: "2026-11-07T10:01:00+00:00" }),
      makeEvent({ kind: "progress", to_status: "running", created_at: "2026-11-07T10:02:00+00:00" }),
      makeEvent({ kind: "succeeded", to_status: "succeeded", created_at: "2026-11-07T10:03:00+00:00" }),
    ];

    expect(transitionPath(events)).toBe("pending → assigned → running → succeeded");
  });

  it("не дублирует повторяющийся статус", () => {
    const events = [
      makeEvent({ kind: "created", to_status: "pending" }),
      makeEvent({ kind: "created", to_status: "pending" }),
    ];
    expect(transitionPath(events)).toBe("pending");
  });

  it("возвращает пустую строку без статусов", () => {
    expect(transitionPath([makeEvent({ to_status: null })])).toBe("");
  });
});

describe("executionSeconds", () => {
  it("считает время от назначения до финала", () => {
    const events = [
      makeEvent({ kind: "created", created_at: "2026-11-07T10:00:00+00:00" }),
      makeEvent({ kind: "assigned", created_at: "2026-11-07T10:01:00+00:00" }),
      makeEvent({ kind: "succeeded", created_at: "2026-11-07T10:04:00+00:00" }),
    ];

    expect(executionSeconds(events)).toBe(180);
  });

  it("возвращает null без старта", () => {
    expect(executionSeconds([makeEvent({ kind: "created" })])).toBeNull();
  });

  it("возвращает null без финала", () => {
    const events = [makeEvent({ kind: "assigned", created_at: "2026-11-07T10:01:00+00:00" })];
    expect(executionSeconds(events)).toBeNull();
  });
});
