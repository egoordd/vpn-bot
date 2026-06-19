import "server-only";

import { TARIFFS, type Tariff, type Tier } from "@/lib/tariffs";
import type { AccountOverview, BillingPlanDto, DiscountResult } from "./types";
import { mockAccountOverview, mockPreviewDiscount } from "./mock";

/**
 * Server-side billing client. The single seam between the site and the shared
 * Python billing API (services/billing_api.py exposed over HTTP). When
 * BILLING_API_URL is unset it falls back to deterministic mock data so the UI
 * runs standalone during design/preview.
 */
const API_URL = process.env.BILLING_API_URL?.replace(/\/$/, "");
const API_TOKEN = process.env.BILLING_API_TOKEN;

export const isBillingLive = Boolean(API_URL);

const GB = 1024 ** 3;

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_URL) {
    throw new Error("BILLING_API_URL is not configured");
  }
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(API_TOKEN ? { authorization: `Bearer ${API_TOKEN}` } : {}),
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Billing API ${path} failed: ${res.status}`);
  }
  return (await res.json()) as T;
}

export async function getAccountOverview(userId: number): Promise<AccountOverview> {
  if (!API_URL) return mockAccountOverview();
  return call<AccountOverview>(`/account/${userId}`);
}

function fallbackPlans(tier?: Tier): Tariff[] {
  return Object.values(TARIFFS)
    .filter((plan) => (tier ? plan.tier === tier : true))
    .filter((plan) => plan.code !== "trial")
    .sort((a, b) => a.sortOrder - b.sortOrder);
}

function planFromBillingDto(plan: BillingPlanDto, sortOrder: number): Tariff {
  return {
    code: plan.code,
    title: plan.title,
    tier: plan.tier,
    durationDays: plan.durationDays,
    priceRub: plan.priceRub,
    cryptoAmount: plan.cryptoAmount,
    trafficGb: plan.trafficLimitBytes === null ? null : Math.round(plan.trafficLimitBytes / GB),
    deviceLimit: plan.deviceLimit,
    description: plan.description,
    sortOrder,
  };
}

export async function getBillingPlans(tier?: Tier): Promise<Tariff[]> {
  if (!API_URL) return fallbackPlans(tier);
  const query = tier ? `?tier=${encodeURIComponent(tier)}` : "";
  const response = await call<{ plans: BillingPlanDto[] }>(`/plans${query}`);
  return response.plans.map((plan, index) => planFromBillingDto(plan, (index + 1) * 10));
}

export async function previewDiscount(
  userId: number,
  code: string,
  amountKopecks: number,
): Promise<DiscountResult | null> {
  if (!API_URL) return mockPreviewDiscount(code, amountKopecks);
  try {
    return await call<DiscountResult>(`/promo/preview`, {
      method: "POST",
      body: JSON.stringify({ userId, code, amountKopecks }),
    });
  } catch {
    return null;
  }
}
