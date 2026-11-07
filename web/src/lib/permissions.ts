import type { Role } from "../auth/session";

export function canCreateTasks(role: Role): boolean {
  return role === "operator";
}

export function canCancelTasks(role: Role): boolean {
  return role === "operator";
}

export function denyReason(role: Role): string {
  return role === "viewer"
    ? "Роль «Наблюдатель»: действия недоступны, только просмотр"
    : "";
}
