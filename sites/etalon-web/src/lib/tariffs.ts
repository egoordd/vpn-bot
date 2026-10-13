/**
 * Тарифы Etalon VPN — те же, что показывает бот (MARAT_PLANS в marat_bot/core.py).
 * Оплата пока в боте не подключена: кнопки тарифов ведут в бот.
 */
export interface Tariff {
  code: string;
  durationDays: number;
  priceRub: number;
  deviceLimit: number;
}

export const TRIAL = { durationDays: 3, trafficGb: 10, deviceLimit: 2 } as const;

export const PLANS: readonly Tariff[] = [
  { code: "1m", durationDays: 30, priceRub: 199, deviceLimit: 5 },
  { code: "3m", durationDays: 90, priceRub: 549, deviceLimit: 5 },
  { code: "6m", durationDays: 180, priceRub: 999, deviceLimit: 5 },
  { code: "12m", durationDays: 365, priceRub: 1799, deviceLimit: 5 },
];

/** Цена за месяц для подписи «≈ N ₽/мес» — так же считает бот. */
export function pricePerMonth(tariff: Tariff): number {
  return Math.round((tariff.priceRub * 30) / tariff.durationDays);
}

/** Выгода относительно помесячной оплаты, в процентах (0 для месячного тарифа). */
export function savingPercent(tariff: Tariff): number {
  const base = PLANS[0];
  const monthly = (base.priceRub * 30) / base.durationDays;
  const actual = (tariff.priceRub * 30) / tariff.durationDays;
  return Math.max(0, Math.round((1 - actual / monthly) * 100));
}

/** `5 дней`, `2 дня`, `1 день`. */
export function pluralDays(count: number): string {
  const tail = Math.abs(count) % 100;
  if (tail >= 11 && tail <= 14) return `${count} дней`;
  const last = tail % 10;
  if (last === 1) return `${count} день`;
  if (last >= 2 && last <= 4) return `${count} дня`;
  return `${count} дней`;
}

export const TRIAL_DAYS_LABEL = pluralDays(TRIAL.durationDays);
