export type Role = "operator" | "viewer";

export interface Session {
  role: Role;
  apiKey: string;
}

export const SESSION_KEY = "dispatch.session";

export function parseSession(raw: string | null): Session | null {
  if (!raw) {
    return null;
  }
  try {
    const value = JSON.parse(raw) as { role?: unknown; apiKey?: unknown };
    if (value.role !== "operator" && value.role !== "viewer") {
      return null;
    }
    return {
      role: value.role,
      apiKey: typeof value.apiKey === "string" ? value.apiKey : "",
    };
  } catch {
    return null;
  }
}

function resolveStorage(storage?: Storage): Storage | null {
  if (storage) {
    return storage;
  }
  try {
    return globalThis.sessionStorage ?? null;
  } catch {
    return null;
  }
}

export function loadSession(storage?: Storage): Session | null {
  const target = resolveStorage(storage);
  if (!target) {
    return null;
  }
  try {
    return parseSession(target.getItem(SESSION_KEY));
  } catch {
    return null;
  }
}

export function saveSession(session: Session, storage?: Storage): void {
  const target = resolveStorage(storage);
  if (!target) {
    return;
  }
  try {
    target.setItem(SESSION_KEY, JSON.stringify(session));
  } catch {
    return;
  }
}

export function clearSession(storage?: Storage): void {
  const target = resolveStorage(storage);
  if (!target) {
    return;
  }
  try {
    target.removeItem(SESSION_KEY);
  } catch {
    return;
  }
}

export function roleLabel(role: Role): string {
  return role === "operator" ? "Оператор" : "Наблюдатель";
}
