export function pluralRu(count: number, forms: [string, string, string]): string {
  const absolute = Math.abs(count) % 100;
  const last = absolute % 10;
  if (absolute > 10 && absolute < 20) {
    return forms[2];
  }
  if (last > 1 && last < 5) {
    return forms[1];
  }
  if (last === 1) {
    return forms[0];
  }
  return forms[2];
}

export function formatDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.round(totalSeconds));
  if (seconds < 60) {
    return `${seconds} с`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes} ${pluralRu(minutes, ["минута", "минуты", "минут"])}`;
  }
  const hours = Math.floor(minutes / 60);
  const restMinutes = minutes % 60;
  if (hours < 24) {
    const hourText = `${hours} ${pluralRu(hours, ["час", "часа", "часов"])}`;
    return restMinutes > 0 ? `${hourText} ${restMinutes} мин` : hourText;
  }
  const days = Math.floor(hours / 24);
  const restHours = hours % 24;
  const dayText = `${days} ${pluralRu(days, ["день", "дня", "дней"])}`;
  return restHours > 0 ? `${dayText} ${restHours} ч` : dayText;
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat("ru-RU").format(value);
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) {
    return "—";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatRelative(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) {
    return "—";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  const deltaSeconds = Math.round((now.getTime() - date.getTime()) / 1000);
  if (Math.abs(deltaSeconds) < 10) {
    return "только что";
  }
  const future = deltaSeconds < 0;
  const text = formatDuration(Math.abs(deltaSeconds));
  return future ? `через ${text}` : `${text} назад`;
}

export function formatLease(leaseExpiresAt: string | null, now: Date = new Date()): string {
  if (!leaseExpiresAt) {
    return "аренда не выдана";
  }
  const date = new Date(leaseExpiresAt);
  if (Number.isNaN(date.getTime())) {
    return "аренда не выдана";
  }
  const deltaSeconds = Math.round((date.getTime() - now.getTime()) / 1000);
  if (deltaSeconds <= 0) {
    return `просрочена на ${formatDuration(Math.abs(deltaSeconds))}`;
  }
  return `истекает через ${formatDuration(deltaSeconds)}`;
}

export function percent(part: number, total: number): number {
  if (total <= 0) {
    return 0;
  }
  return Math.round((part / total) * 1000) / 10;
}

export function formatPercent(part: number, total: number): string {
  return `${percent(part, total).toFixed(1)} %`;
}
