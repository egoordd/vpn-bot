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
    trafficResetsMonthly: plan.tier !== "trial",
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
  /** The buyer's existing subscription link, when they are topping that up. */
  subscription?: string;
  clientIp?: string;
}): Promise<CheckoutResult> {
  if (!API_URL) return mockCheckout();
  const { clientIp, ...payload } = input;
  const res = await fetch(`${API_URL}/web/checkout`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(API_TOKEN ? { authorization: `Bearer ${API_TOKEN}` } : {}),
      // Forward the browser IP so the billing API can rate-limit the real
      // client, not the single Vercel egress address.
      ...(clientIp ? { "x-client-ip": clientIp } : {}),
    },
    body: JSON.stringify(payload),
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

export class WebAuthError extends Error {
  constructor(public readonly code: string) {
    super(code);
  }
}

/** Register/login return the account's telegram_id (negative for email accounts). */
async function authCall(path: string, email: string, password: string): Promise<number> {
  if (!API_URL) {
    // Mock mode: pretend a deterministic email account exists.
    return -1;
  }
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(API_TOKEN ? { authorization: `Bearer ${API_TOKEN}` } : {}),
    },
    body: JSON.stringify({ email, password }),
    cache: "no-store",
  });
  if (!res.ok) {
    let code = `auth_failed_${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (typeof body.detail === "string" && body.detail) code = body.detail;
    } catch {
      // keep status-based code
    }
    throw new WebAuthError(code);
  }
  const body = (await res.json()) as { telegramId: number };
  return body.telegramId;
}

export async function registerWebAccount(email: string, password: string): Promise<number> {
  return authCall("/web/auth/register", email, password);
}

export async function loginWebAccount(email: string, password: string): Promise<number> {
  return authCall("/web/auth/login", email, password);
}

export async function updateAccountEmail(telegramId: number, email: string): Promise<boolean> {
  if (!API_URL) return true;
  const result = await callOrNull<{ ok: boolean }>(`/web/account/email`, {
    method: "POST",
    body: JSON.stringify({ telegramId, email }),
  });
  return result?.ok ?? false;
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

export type TrialActivationResult =
  | { ok: true; subscriptionUrl: string | null }
  | { ok: false; error: "has_active_subscription" | "trial_already_used" | "unavailable" };

export async function activateWebTrial(telegramId: number): Promise<TrialActivationResult> {
  // Standalone preview: pretend the trial activated so the UI flow is testable.
  if (!API_URL) {
    return { ok: true, subscriptionUrl: "https://sub.unlockvpn.site/sub/demo" };
  }
  const res = await fetch(`${API_URL}/web/trial/activate`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(API_TOKEN ? { authorization: `Bearer ${API_TOKEN}` } : {}),
    },
    body: JSON.stringify({ telegramId }),
    cache: "no-store",
  });
  if (res.ok) {
    const body = (await res.json()) as { subscriptionUrl?: string | null };
    return { ok: true, subscriptionUrl: body.subscriptionUrl ?? null };
  }
  let detail = "";
  try {
    detail = ((await res.json()) as { detail?: string }).detail ?? "";
  } catch {
    // non-JSON error body — treat as unavailable
  }
  if (detail === "has_active_subscription" || detail === "trial_already_used") {
    return { ok: false, error: detail };
  }
  return { ok: false, error: "unavailable" };
}

/** Count a tap on a /go/<campaign> tracking link. Best-effort: a tracking
 *  failure must never block the visitor's redirect, so this swallows errors. */
export async function recordLinkClick(campaign: string, target: "bot" | "site"): Promise<void> {
  if (!API_URL) return;
  try {
    await fetch(`${API_URL}/web/track/click`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(API_TOKEN ? { authorization: `Bearer ${API_TOKEN}` } : {}),
      },
      body: JSON.stringify({ campaign, target }),
      cache: "no-store",
    });
  } catch {
    // tracking is not worth a failed redirect
  }
}
