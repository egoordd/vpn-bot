import "server-only";

import { TARIFFS, type Tariff, type Tier } from "@/lib/tariffs";
import type {
  AccountOverview,
  BillingPlanDto,
  CheckoutResult,
  DiscountResult,
  WebOrderStatus,
} from "./types";
import { mockAccountOverview, mockCheckout, mockOrderStatus, mockPreviewDiscount } from "./mock";

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

/** Like `call`, but resolves null on a 404 instead of throwing. */
async function callOrNull<T>(path: string, init?: RequestInit): Promise<T | null> {
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
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`Billing API ${path} failed: ${res.status}`);
  }
  return (await res.json()) as T;
}

export async function getAccountByTelegram(telegramId: number): Promise<AccountOverview | null> {
  if (!API_URL) return mockAccountOverview();
  return callOrNull<AccountOverview>(`/web/account/by-telegram/${telegramId}`);
}

export class CheckoutError extends Error {
  constructor(public readonly code: string) {
    super(code);
  }
}

export async function createWebCheckout(input: {
  plan: string;
  telegramId?: number;
  email?: string;
}): Promise<CheckoutResult> {
  if (!API_URL) return mockCheckout();
  const res = await fetch(`${API_URL}/web/checkout`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(API_TOKEN ? { authorization: `Bearer ${API_TOKEN}` } : {}),
    },
    body: JSON.stringify(input),
    cache: "no-store",
  });
  if (!res.ok) {
    let code = `checkout_failed_${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (typeof body.detail === "string" && body.detail) code = body.detail;
    } catch {
      // non-JSON error body — keep the status-based code
    }
    throw new CheckoutError(code);
  }
  return (await res.json()) as CheckoutResult;
}

export async function getWebOrder(orderId: string): Promise<WebOrderStatus | null> {
  if (!API_URL) return mockOrderStatus();
  return callOrNull<WebOrderStatus>(`/web/order/${encodeURIComponent(orderId)}`);
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
