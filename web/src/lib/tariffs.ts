/**
 * Tariff catalogue — mirror of the backend `services/tariffs.py`.
 *
 * Keep prices/limits in sync with the Python source of truth. The site renders
 * from this; the real billing API will eventually feed `/api/plans` so this
 * becomes the fallback rather than the source.
 */
export type Tier = "trial" | "standard";

export interface Tariff {
  code: string;
  title: string;
  tier: Tier;
  durationDays: number;
  priceRub: number;
  cryptoAmount: string;
  /** One month's allowance. Paid tariffs refill it every 30 days. */
  trafficGb: number | null;
  /** False only for the trial, whose single bucket never refills. */
  trafficResetsMonthly: boolean;
  deviceLimit: number | null;
  description: string;
  sortOrder: number;
}

const BASE_TARIFFS: Record<string, Tariff> = {
  trial: {
    code: "trial",
    title: "Пробник",
    tier: "trial",
    durationDays: 3,
    priceRub: 0,
    cryptoAmount: "0",
    trafficGb: 10,
    trafficResetsMonthly: false,
    deviceLimit: 2,
    description: "Пробный доступ: 3 дня, 10 ГБ",
    sortOrder: 0,
  },
  standard_1m: {
    code: "standard_1m",
    title: "Standard · 1 месяц",
    tier: "standard",
    durationDays: 30,
    priceRub: 149,
    cryptoAmount: "1.99",
    trafficGb: 150,
    trafficResetsMonthly: true,
    deviceLimit: 3,
    description: "Общий тариф на 30 дней, 150 ГБ в месяц",
    sortOrder: 10,
  },
  standard_3m: {
    code: "standard_3m",
    title: "Standard · 3 месяца",
    tier: "standard",
    durationDays: 90,
    priceRub: 399,
    cryptoAmount: "4.99",
    trafficGb: 200,
    trafficResetsMonthly: true,
    deviceLimit: 3,
    description: "Общий тариф на 90 дней, 200 ГБ в месяц",
    sortOrder: 20,
  },
  standard_6m: {
    code: "standard_6m",
    title: "Standard · 6 месяцев",
    tier: "standard",
    durationDays: 180,
    priceRub: 699,
    cryptoAmount: "7.99",
    trafficGb: 200,
    trafficResetsMonthly: true,
    deviceLimit: 3,
    description: "Общий тариф на 180 дней, 200 ГБ в месяц",
    sortOrder: 30,
  },
  standard_12m: {
    code: "standard_12m",
    title: "Standard · 12 месяцев",
    tier: "standard",
    durationDays: 365,
    priceRub: 1199,
    cryptoAmount: "12.99",
    trafficGb: 200,
    trafficResetsMonthly: true,
    deviceLimit: 3,
    description: "Общий тариф на 12 месяцев, 200 ГБ в месяц",
    sortOrder: 40,
  },
};

/**
 * Повышение цен, объявленное рассылкой 23.09.2026: с 26.09.2026 00:00 по Москве.
 * Как и в боте (services/tariffs.py), цена берётся на момент показа, поэтому
 * в полночь ничего пересобирать не нужно: страницы обновляются сами
 * (revalidate в app/layout.tsx), а в браузере цена считается по его часам.
 */
export const PRICE_RISE_AT = Date.UTC(2026, 8, 25, 21, 0, 0); // 26.09 00:00 МСК

const RISEN_PRICES: Record<string, { priceRub: number; cryptoAmount: string }> = {
  standard_1m: { priceRub: 199, cryptoAmount: "2.49" },
  standard_3m: { priceRub: 549, cryptoAmount: "6.99" },
  standard_6m: { priceRub: 999, cryptoAmount: "11.99" },
  standard_12m: { priceRub: 1799, cryptoAmount: "19.99" },
};

export function priceRiseInEffect(now: number = Date.now()): boolean {
  return now >= PRICE_RISE_AT;
}

function effective(tariff: Tariff, now: number = Date.now()): Tariff {
  const risen = RISEN_PRICES[tariff.code];
  return risen && priceRiseInEffect(now) ? { ...tariff, ...risen } : tariff;
}

/** Каталог с ценой, действующей прямо сейчас. */
export const TARIFFS: Record<string, Tariff> = new Proxy(BASE_TARIFFS, {
  get(target, key, receiver) {
    const value = Reflect.get(target, key, receiver);
    return typeof key === "string" && value && typeof value === "object" && "priceRub" in value
      ? effective(value as Tariff)
      : value;
  },
});



export function tariffsByTier(tier: Tier): Tariff[] {
  return Object.values(TARIFFS)
    .filter((t) => t.tier === tier)
    .sort((a, b) => a.sortOrder - b.sortOrder);
}

/** Monthly-equivalent price for "от N ₽/мес" labels. */
export function pricePerMonth(tariff: Tariff): number {
  const months = Math.max(1, Math.round(tariff.durationDays / 30));
  return Math.round(tariff.priceRub / months);
}


/** How much traffic a tariff grants, worded so the period is unmistakable.
 *
 * A refilling allowance printed bare reads as the whole term — "150 ГБ" on a
 * three-month plan looks like a term-wide pool rather than a monthly allowance.
 */
export function trafficLabel(plan: Pick<Tariff, "trafficGb" | "trafficResetsMonthly">): string | null {
  if (plan.trafficGb === null) return null;
  return plan.trafficResetsMonthly ? `${plan.trafficGb} ГБ трафика в месяц` : `${plan.trafficGb} ГБ трафика`;
}


/** `5 дней`, `2 дня`, `1 день` — so trial copy is never a hand-typed number.
 *
 * The length was spelled out in nine components; moving it from three days to
 * seven meant editing every one. Now it is one field.
 */
export function pluralDays(count: number): string {
  const tail = Math.abs(count) % 100;
  if (tail >= 11 && tail <= 14) return `${count} дней`;
  const last = tail % 10;
  if (last === 1) return `${count} день`;
  if (last >= 2 && last <= 4) return `${count} дня`;
  return `${count} дней`;
}

/** How long the free trial runs, worded for prose. */
export const TRIAL_DAYS_LABEL = pluralDays(TARIFFS.trial.durationDays);
