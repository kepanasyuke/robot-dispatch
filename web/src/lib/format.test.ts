import { describe, expect, it } from "vitest";
import {
  formatDateTime,
  formatDuration,
  formatLease,
  formatNumber,
  formatPercent,
  formatRelative,
  percent,
  pluralRu,
} from "./format";

describe("pluralRu", () => {
  it.each([
    [1, "минута"],
    [2, "минуты"],
    [4, "минуты"],
    [5, "минут"],
    [11, "минут"],
    [12, "минут"],
    [21, "минута"],
    [22, "минуты"],
    [25, "минут"],
    [101, "минута"],
    [111, "минут"],
    [0, "минут"],
  ])("склоняет %i как %s", (count, expected) => {
    expect(pluralRu(count, ["минута", "минуты", "минут"])).toBe(expected);
  });
});

describe("formatDuration", () => {
  it.each([
    [0, "0 с"],
    [1, "1 с"],
    [45, "45 с"],
    [59, "59 с"],
    [60, "1 минута"],
    [120, "2 минуты"],
    [300, "5 минут"],
    [3599, "59 минут"],
    [3600, "1 час"],
    [3660, "1 час 1 мин"],
    [7200, "2 часа"],
    [86_399, "23 часа 59 мин"],
    [86_400, "1 день"],
    [90_000, "1 день 1 ч"],
    [172_800, "2 дня"],
  ])("переводит %i секунд в «%s»", (seconds, expected) => {
    expect(formatDuration(seconds)).toBe(expected);
  });

  it("не показывает отрицательные значения", () => {
    expect(formatDuration(-50)).toBe("0 с");
  });
});

describe("formatRelative", () => {
  const now = new Date("2026-11-07T12:00:00+00:00");

  it.each([
    ["2026-11-07T11:59:55+00:00", "только что"],
    ["2026-11-07T11:58:00+00:00", "2 минуты назад"],
    ["2026-11-07T09:00:00+00:00", "3 часа назад"],
    ["2026-11-05T12:00:00+00:00", "2 дня назад"],
    ["2026-11-07T12:05:00+00:00", "через 5 минут"],
  ])("описывает %s как «%s»", (iso, expected) => {
    expect(formatRelative(iso, now)).toBe(expected);
  });

  it("возвращает прочерк для пустого значения", () => {
    expect(formatRelative(null, now)).toBe("—");
    expect(formatRelative(undefined, now)).toBe("—");
  });

  it("возвращает прочерк для невалидной даты", () => {
    expect(formatRelative("not-a-date", now)).toBe("—");
  });
});

describe("formatLease", () => {
  const now = new Date("2026-11-07T12:00:00+00:00");

  it("сообщает, что аренда не выдана", () => {
    expect(formatLease(null, now)).toBe("аренда не выдана");
  });

  it("считает время до истечения", () => {
    expect(formatLease("2026-11-07T12:02:00+00:00", now)).toBe("истекает через 2 минуты");
  });

  it("показывает просрочку", () => {
    expect(formatLease("2026-11-07T11:59:30+00:00", now)).toBe("просрочена на 30 с");
  });
});

describe("formatDateTime", () => {
  it("форматирует дату в московском времени", () => {
    expect(formatDateTime("2026-11-07T12:05:00+00:00", "Europe/Moscow")).toBe("07.11.2026, 15:05");
  });

  it("уважает явно заданный часовой пояс", () => {
    expect(formatDateTime("2026-11-07T12:05:00+00:00", "UTC")).toBe("07.11.2026, 12:05");
  });

  it("возвращает прочерк для пустого значения", () => {
    expect(formatDateTime(null)).toBe("—");
  });
});

describe("formatNumber", () => {
  it.each([
    [0, "0"],
    [1000, "1 000"],
    [1_234_567, "1 234 567"],
  ])("группирует %i как «%s»", (value, expected) => {
    expect(formatNumber(value).replace(/\u00a0/g, " ")).toBe(expected);
  });
});

describe("percent", () => {
  it.each([
    [1, 4, 25],
    [1, 3, 33.3],
    [0, 10, 0],
    [5, 5, 100],
  ])("считает %i из %i как %f", (part, total, expected) => {
    expect(percent(part, total)).toBe(expected);
  });

  it("не делит на ноль", () => {
    expect(percent(3, 0)).toBe(0);
  });

  it("форматирует проценты с одним знаком", () => {
    expect(formatPercent(1, 3)).toBe("33.3 %");
  });
});
