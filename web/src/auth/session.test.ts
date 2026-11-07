import { beforeEach, describe, expect, it } from "vitest";
import {
  SESSION_KEY,
  clearSession,
  loadSession,
  parseSession,
  roleLabel,
  saveSession,
} from "./session";

class MemoryStorage implements Storage {
  private data = new Map<string, string>();

  get length(): number {
    return this.data.size;
  }

  clear(): void {
    this.data.clear();
  }

  getItem(key: string): string | null {
    return this.data.get(key) ?? null;
  }

  key(index: number): string | null {
    return [...this.data.keys()][index] ?? null;
  }

  removeItem(key: string): void {
    this.data.delete(key);
  }

  setItem(key: string, value: string): void {
    this.data.set(key, value);
  }
}

describe("parseSession", () => {
  it.each([
    ['{"role":"operator","apiKey":"k"}', "operator", "k"],
    ['{"role":"viewer","apiKey":""}', "viewer", ""],
  ])("читает валидную сессию %s", (raw, role, apiKey) => {
    expect(parseSession(raw)).toEqual({ role, apiKey });
  });

  it("возвращает null без данных", () => {
    expect(parseSession(null)).toBeNull();
    expect(parseSession("")).toBeNull();
  });

  it("отклоняет неизвестную роль", () => {
    expect(parseSession('{"role":"admin"}')).toBeNull();
  });

  it("отклоняет битый JSON", () => {
    expect(parseSession("{oops")).toBeNull();
  });

  it("подставляет пустой ключ", () => {
    expect(parseSession('{"role":"operator"}')).toEqual({ role: "operator", apiKey: "" });
  });
});

describe("saveSession / loadSession / clearSession", () => {
  let storage: MemoryStorage;

  beforeEach(() => {
    storage = new MemoryStorage();
  });

  it("сохраняет и читает сессию", () => {
    saveSession({ role: "operator", apiKey: "secret" }, storage);

    expect(storage.getItem(SESSION_KEY)).toContain("operator");
    expect(loadSession(storage)).toEqual({ role: "operator", apiKey: "secret" });
  });

  it("очищает сессию", () => {
    saveSession({ role: "viewer", apiKey: "" }, storage);
    clearSession(storage);

    expect(loadSession(storage)).toBeNull();
  });

  it("возвращает null для пустого хранилища", () => {
    expect(loadSession(storage)).toBeNull();
  });

  it("не падает при сломанном хранилище", () => {
    const broken = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
      removeItem: () => {
        throw new Error("blocked");
      },
      clear: () => undefined,
      key: () => null,
      length: 0,
    } as unknown as Storage;

    expect(() => saveSession({ role: "operator", apiKey: "" }, broken)).not.toThrow();
    expect(loadSession(broken)).toBeNull();
    expect(() => clearSession(broken)).not.toThrow();
  });

  it("работает с sessionStorage по умолчанию", () => {
    saveSession({ role: "viewer", apiKey: "k" });
    expect(loadSession()).toEqual({ role: "viewer", apiKey: "k" });
    clearSession();
    expect(loadSession()).toBeNull();
  });
});

describe("roleLabel", () => {
  it.each([
    ["operator", "Оператор"],
    ["viewer", "Наблюдатель"],
  ] as const)("переводит %s", (role, expected) => {
    expect(roleLabel(role)).toBe(expected);
  });
});
