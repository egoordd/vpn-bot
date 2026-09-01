import { TARIFFS } from "@/lib/tariffs";
import type { AccountOverview, CheckoutResult, DiscountResult, WebOrderStatus } from "./types";

const GB = 1024 ** 3;

function daysFromNow(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString();
}

function hoursAgo(hours: number): string {
  const d = new Date();
  d.setHours(d.getHours() - hours);
  return d.toISOString();
}

/**
 * Deterministic demo account so the cabinet renders standalone (no backend).
 * Replaced by the real billing API once BILLING_API_URL is set.
 */
export function mockAccountOverview(): AccountOverview {
  const plan = TARIFFS.standard_3m;
  return {
    userId: 1,
    telegramId: 100200300,
    subscription: {
      exists: true,
      isActive: true,
      plan: plan.code,
      planTitle: plan.title,
      tier: plan.tier,
      subscriptionUrl: "https://144.172.101.217.sslip.io:8443/sub/demo-token",
      trafficLimitBytes: (plan.trafficGb ?? 0) * GB,
      trafficUsedBytes: Math.round(148 * GB),
      deviceLimit: plan.deviceLimit,
      status: "active",
      expiresAt: daysFromNow(54),
    },
    referral: {
      refCode: "tg100200300",
      referralsCount: 3,
    },
    email: "demo@example.com",
  };
}

export function mockCheckout(): CheckoutResult {
  return { orderId: "mock-order-1", payUrl: "/pay/success" };
}

export function mockOrderStatus(): WebOrderStatus {
  return {
    status: "succeeded",
    subscription: {
      subscriptionUrl: "https://144.172.101.217.sslip.io:8443/sub/demo-token",
      planTitle: TARIFFS.standard_1m.title,
      expiresAt: daysFromNow(30),
      isActive: true,
    },
  };
}

const MOCK_PROMOS: Record<string, { kind: "percent" | "fixed"; value: number }> = {
  WELCOME: { kind: "percent", value: 20 },
  UNLOCK10: { kind: "percent", value: 10 },
};

export function mockPreviewDiscount(code: string, amountKopecks: number): DiscountResult | null {
  const promo = MOCK_PROMOS[code.trim().toUpperCase()];
  if (!promo) return null;
  const raw = promo.kind === "percent" ? Math.round((amountKopecks * promo.value) / 100) : promo.value;
  const discount = Math.min(Math.max(raw, 0), amountKopecks);
  return {
    code: code.trim().toUpperCase(),
    originalKopecks: amountKopecks,
    discountKopecks: discount,
    finalKopecks: amountKopecks - discount,
  };
}
