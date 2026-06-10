/**
 * Tariff catalogue — mirror of the backend `services/tariffs.py`.
 *
 * Keep prices/limits in sync with the Python source of truth. The site renders
 * from this; the real billing API will eventually feed `/api/plans` so this
 * becomes the fallback rather than the source.
 */
export type Tier = "trial" | "standard" | "premium";

export interface Tariff {
  code: string;
  title: string;
  tier: Tier;
  durationDays: number;
  priceRub: number;
  cryptoAmount: string;
  trafficGb: number | null;
  deviceLimit: number | null;
  description: string;
  sortOrder: number;
}

export const TARIFFS: Record<string, Tariff> = {
  trial: {
    code: "trial",
    title: "Пробник",
    tier: "trial",
    durationDays: 7,
    priceRub: 0,
    cryptoAmount: "0",
    trafficGb: 10,
    deviceLimit: 1,
    description: "Пробный доступ на 10 ГБ",
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
    deviceLimit: 3,
    description: "Общий тариф на 30 дней",
    sortOrder: 10,
  },
  standard_3m: {
    code: "standard_3m",
    title: "Standard · 3 месяца",
    tier: "standard",
    durationDays: 90,
    priceRub: 399,
    cryptoAmount: "4.99",
    trafficGb: 450,
    deviceLimit: 3,
    description: "Общий тариф на 90 дней",
    sortOrder: 20,
  },
  standard_6m: {
    code: "standard_6m",
    title: "Standard · 6 месяцев",
    tier: "standard",
    durationDays: 180,
    priceRub: 699,
    cryptoAmount: "7.99",
    trafficGb: 900,
    deviceLimit: 5,
    description: "Общий тариф на 180 дней",
    sortOrder: 30,
  },
  standard_12m: {
    code: "standard_12m",
    title: "Standard · 12 месяцев",
    tier: "standard",
    durationDays: 365,
    priceRub: 1199,
    cryptoAmount: "12.99",
    trafficGb: 1800,
    deviceLimit: 5,
    description: "Общий тариф на 12 месяцев",
    sortOrder: 40,
  },
  premium_1m: {
    code: "premium_1m",
    title: "Premium · 1 месяц",
    tier: "premium",
    durationDays: 30,
    priceRub: 399,
    cryptoAmount: "4.99",
    trafficGb: 300,
    deviceLimit: 5,
    description: "Premium-тариф на 30 дней",
    sortOrder: 50,
  },
  premium_3m: {
    code: "premium_3m",
    title: "Premium · 3 месяца",
    tier: "premium",
    durationDays: 90,
    priceRub: 999,
    cryptoAmount: "11.99",
    trafficGb: 900,
    deviceLimit: 5,
    description: "Premium-тариф на 90 дней",
    sortOrder: 60,
  },
  premium_6m: {
    code: "premium_6m",
    title: "Premium · 6 месяцев",
    tier: "premium",
    durationDays: 180,
    priceRub: 1799,
    cryptoAmount: "19.99",
    trafficGb: 1800,
    deviceLimit: 8,
    description: "Premium-тариф на 180 дней",
    sortOrder: 70,
  },
  premium_12m: {
    code: "premium_12m",
    title: "Premium · 12 месяцев",
    tier: "premium",
    durationDays: 365,
    priceRub: 2999,
    cryptoAmount: "34.99",
    trafficGb: 3600,
    deviceLimit: 8,
    description: "Premium-тариф на 12 месяцев",
    sortOrder: 80,
  },
};

export interface RegionOption {
  code: string;
  title: string;
  city: string;
  countryCode: string;
  isOnDemand: boolean;
}

export const PREMIUM_REGIONS: RegionOption[] = [
  { code: "ams", title: "Нидерланды, Амстердам", city: "Amsterdam", countryCode: "NL", isOnDemand: false },
  { code: "fra", title: "Германия, Франкфурт", city: "Frankfurt", countryCode: "DE", isOnDemand: false },
  { code: "waw", title: "Польша, Варшава", city: "Warsaw", countryCode: "PL", isOnDemand: true },
];

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
