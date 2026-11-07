import { describe, expect, it } from "vitest";
import {
  isActiveStatus,
  isTerminalStatus,
  robotStatusLabel,
  robotStatusTone,
  taskStatusLabel,
  taskStatusTone,
} from "./status";

describe("taskStatusLabel", () => {
  it.each([
    ["pending", "В очереди"],
    ["assigned", "Назначена"],
    ["running", "Выполняется"],
    ["retrying", "Повтор"],
    ["succeeded", "Успешно"],
    ["failed", "Провалена"],
    ["cancelled", "Отменена"],
  ])("переводит %s", (status, expected) => {
    expect(taskStatusLabel(status)).toBe(expected);
  });

  it("возвращает неизвестный статус как есть", () => {
    expect(taskStatusLabel("archived")).toBe("archived");
  });
});

describe("taskStatusTone", () => {
  it.each([
    ["pending", "neutral"],
    ["assigned", "info"],
    ["running", "info"],
    ["retrying", "warning"],
    ["succeeded", "success"],
    ["failed", "danger"],
    ["cancelled", "neutral"],
  ])("даёт тон %s для %s", (status, expected) => {
    expect(taskStatusTone(status)).toBe(expected);
  });
});

describe("robotStatusLabel", () => {
  it.each([
    ["idle", "Свободен"],
    ["busy", "Занят"],
    ["offline", "Не в сети"],
  ])("переводит %s", (status, expected) => {
    expect(robotStatusLabel(status)).toBe(expected);
  });
});

describe("robotStatusTone", () => {
  it.each([
    ["idle", "success"],
    ["busy", "info"],
    ["offline", "danger"],
  ])("даёт тон %s для %s", (status, expected) => {
    expect(robotStatusTone(status)).toBe(expected);
  });
});

describe("isTerminalStatus", () => {
  it.each([
    ["succeeded", true],
    ["failed", true],
    ["cancelled", true],
    ["running", false],
    ["pending", false],
  ])("%s → %s", (status, expected) => {
    expect(isTerminalStatus(status)).toBe(expected);
  });
});

describe("isActiveStatus", () => {
  it.each([
    ["assigned", true],
    ["running", true],
    ["retrying", true],
    ["pending", false],
    ["failed", false],
  ])("%s → %s", (status, expected) => {
    expect(isActiveStatus(status)).toBe(expected);
  });
});
