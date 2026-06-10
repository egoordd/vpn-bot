import "server-only";

import type { AccountOverview, DiscountResult } from "./types";
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
