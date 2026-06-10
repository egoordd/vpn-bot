/** Presentation helpers for the cabinet (traffic, dates, relative time). */

export function formatGb(bytes: number | null): string {
  if (bytes === null) return "∞";
  const gb = bytes / 1024 ** 3;
  if (gb >= 100) return `${Math.round(gb)} ГБ`;
  return `${gb.toFixed(1).replace(/\.0$/, "")} ГБ`;
}

export function trafficPercent(used: number | null, limit: number | null): number {
  if (!limit || used === null) return 0;
  return Math.min(100, Math.round((used / limit) * 100));
}

const DATE_FMT = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "long",
  year: "numeric",
});

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return DATE_FMT.format(new Date(iso));
}

export function daysLeft(iso: string | null): number | null {
  if (!iso) return null;
  const diff = new Date(iso).getTime() - Date.now();
  return Math.max(0, Math.ceil(diff / 86_400_000));
}

export function formatRelative(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60_000);
  if (mins < 1) return "только что";
  if (mins < 60) return `${mins} мин назад`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} ч назад`;
  const days = Math.round(hours / 24);
  return `${days} дн назад`;
}
